import path from "node:path";
import { PipelineConfig } from "../config";
import { SegmentSelection, ShotPlan } from "../types";
import { readJsonFile, writeJsonFile } from "../utils/fs";
import { discoverCandidates } from "./discovery";

export async function searchYoutubeAndSelect(config: PipelineConfig, repoRoot: string): Promise<SegmentSelection[]> {
  const shotPlanPath = path.resolve(repoRoot, "data/shot-plan.json");
  const shotPlan = readJsonFile<ShotPlan>(shotPlanPath);

  const allCandidates = [];
  const selections: SegmentSelection[] = [];

  for (const seg of shotPlan.segments) {
    const filtered = discoverCandidates(seg, config);
    const ranked = filtered.sort((a, b) => b.score - a.score);
    const ytFirst = ranked.find((c) => c.source === "youtube");
    const selected =
      ytFirst && config.youtube.selected_per_segment > 0
        ? [ytFirst, ...ranked.filter((c) => c !== ytFirst)].slice(0, config.youtube.selected_per_segment)
        : ranked.slice(0, config.youtube.selected_per_segment);
    allCandidates.push(...filtered);
    selections.push({
      segment_id: seg.segment_id,
      concept: seg.concept,
      query: seg.query,
      selected,
    });
  }

  writeJsonFile(path.resolve(repoRoot, "data/candidates.json"), {
    generated_at: new Date().toISOString(),
    candidates: allCandidates,
  });
  writeJsonFile(path.resolve(repoRoot, "data/selected-clips.json"), {
    generated_at: new Date().toISOString(),
    segments: selections,
  });

  return selections;
}
