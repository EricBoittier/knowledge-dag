import path from "node:path";
import fs from "node:fs";
import { readJson, writeJson } from "../../core/src/fs";
import { DagProject, MediaCandidate, SegmentPlan } from "../../core/src/types";
import { discoverForSegment, discoverForSegmentWithContext, DiscoveryConfig, DiscoveryContext } from "./discovery";

function tokenize(text: string): string[] {
  return String(text || "")
    .toLowerCase()
    .replace(/[^a-z0-9\s]+/g, " ")
    .split(/\s+/)
    .map((t) => t.trim())
    .filter((t) => t.length >= 3);
}

function buildDiscoveryContext(projectDir: string, segments: SegmentPlan[]): DiscoveryContext {
  const dagPath = path.resolve(projectDir, "dag.project.json");
  let dag: DagProject = { nodes: [], edges: [] };
  if (fs.existsSync(dagPath)) {
    try {
      dag = readJson<DagProject>(dagPath);
    } catch {
      dag = { nodes: [], edges: [] };
    }
  }

  const allTermsSet = new Set<string>();
  for (const n of dag.nodes || []) {
    tokenize(n.title || "").forEach((t) => allTermsSet.add(t));
    for (const tag of n.tags || []) tokenize(tag).forEach((t) => allTermsSet.add(t));
  }

  const segmentTermsById: Record<string, string[]> = {};
  const conceptToNode = new Map((dag.nodes || []).map((n) => [String(n.title || "").toLowerCase(), n]));
  const childrenById = new Map<string, string[]>();
  for (const e of dag.edges || []) {
    const arr = childrenById.get(e.from) || [];
    arr.push(e.to);
    childrenById.set(e.from, arr);
  }

  for (const seg of segments) {
    const segTermsSet = new Set<string>();
    tokenize(seg.concept).forEach((t) => segTermsSet.add(t));
    for (const k of seg.keywords || []) tokenize(k).forEach((t) => segTermsSet.add(t));
    const node = conceptToNode.get(String(seg.concept || "").toLowerCase());
    if (node) {
      tokenize(node.title || "").forEach((t) => segTermsSet.add(t));
      for (const tag of node.tags || []) tokenize(tag).forEach((t) => segTermsSet.add(t));
      const children = childrenById.get(node.id) || [];
      for (const childId of children) {
        const child = (dag.nodes || []).find((n) => n.id === childId);
        if (!child) continue;
        tokenize(child.title || "").forEach((t) => segTermsSet.add(t));
      }
    }
    segmentTermsById[seg.segment_id] = Array.from(segTermsSet).slice(0, 20);
  }

  return {
    projectTerms: Array.from(allTermsSet).slice(0, 40),
    segmentTermsById,
  };
}

export function runDiscovery(projectDir: string, cfg: DiscoveryConfig): void {
  const shotPlan = readJson<{ segments: SegmentPlan[] }>(path.resolve(projectDir, "shot-plan.json"));
  const segments = shotPlan.segments || [];
  const context = buildDiscoveryContext(projectDir, segments);
  const all: MediaCandidate[] = [];
  const selected: Array<{ segment_id: string; concept: string; selected: MediaCandidate[] }> = [];

  const total = Math.max(1, segments.length);
  for (let si = 0; si < segments.length; si++) {
    const seg = segments[si];
    console.log(`[discovery] segment ${si + 1}/${total}: ${seg.concept} (${seg.segment_id})`);
    const candidates = context.projectTerms.length
      ? discoverForSegmentWithContext(seg, cfg, context)
      : discoverForSegment(seg, cfg);
    all.push(...candidates);
    const fallbackCount = Math.max(cfg.selected_per_segment, 3);
    const ytFirst = candidates.find((c) => c.source === "youtube");
    const selectedCandidates =
      ytFirst && fallbackCount > 0
        ? [ytFirst, ...candidates.filter((c) => c !== ytFirst)].slice(0, fallbackCount)
        : candidates.slice(0, fallbackCount);
    selected.push({
      segment_id: seg.segment_id,
      concept: seg.concept,
      selected: selectedCandidates,
    });
  }

  writeJson(path.resolve(projectDir, "candidates.json"), {
    generated_at: new Date().toISOString(),
    candidates: all,
  });
  writeJson(path.resolve(projectDir, "selected-clips.json"), {
    generated_at: new Date().toISOString(),
    segments: selected,
  });
}
