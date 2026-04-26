import path from "node:path";
import { DagNode, DagProject, EditAnnotation, ScriptDraftLine, SegmentPlan } from "../../core/src/types";
import { readJson, writeJson, writeText } from "../../core/src/fs";

function rootNodes(project: DagProject): DagNode[] {
  const incoming = new Set(project.edges.map((e) => e.to));
  return project.nodes
    .filter((n) => !incoming.has(n.id))
    .sort((a, b) => (b.importance ?? 0) - (a.importance ?? 0));
}

function children(project: DagProject, id: string): DagNode[] {
  const childIds = project.edges.filter((e) => e.from === id).map((e) => e.to);
  const set = new Set(childIds);
  return project.nodes
    .filter((n) => set.has(n.id))
    .sort((a, b) => (b.importance ?? 0) - (a.importance ?? 0));
}

function dfs(project: DagProject): DagNode[] {
  const out: DagNode[] = [];
  const seen = new Set<string>();
  const walk = (n: DagNode) => {
    if (seen.has(n.id)) return;
    seen.add(n.id);
    out.push(n);
    for (const c of children(project, n.id)) walk(c);
  };
  for (const r of rootNodes(project)) walk(r);
  return out;
}

function hashSeed(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function pickFromPool(pool: string[], index: number, concept: string): string {
  const seed = hashSeed(`${concept}:${index}`);
  return pool[(index + (seed % pool.length)) % pool.length];
}

function pickTransition(index: number): string {
  const pool = [
    "cross_dissolve_8f",
    "dip_to_color_10f",
    "directional_wipe_12f",
    "film_flash_6f",
    "push_right_10f",
    "blur_dissolve_8f",
    "fade_through_white_8f",
    "luma_fade_12f",
  ];
  return index === 0 ? "fade_in_12f" : pool[index % pool.length];
}

function pickLut(index: number, total: number, concept: string): string {
  if (index === total - 1) return "cold_arctic_finish";
  const pool = [
    "neutral_doc_rec709",
    "soft_contrast_teal",
    "cool_blue_lift",
    "warm_film_stock",
    "natural_green_lift",
    "high_clarity_newsreel",
  ];
  return pickFromPool(pool, index, concept);
}

function buildSubtitleText(concept: string, index: number, total: number): string {
  const fallback = [
    "This segment introduces a core idea that supports the overall storyline.",
    "This step narrows the focus and adds important context.",
    "This level highlights details that make the topic easier to understand.",
  ];
  const hint = fallback[(index + hashSeed(concept)) % fallback.length];
  const progress = `Step ${index + 1} of ${total}.`;
  return `${concept}: ${hint} ${progress}`;
}

export function buildPlannerOutputs(projectDir: string): { segments: SegmentPlan[] } {
  const dagPath = path.resolve(projectDir, "dag.project.json");
  const project = readJson<DagProject>(dagPath);
  const ordered = dfs(project);

  const segments: SegmentPlan[] = ordered.map((n, idx) => {
    const keywords = [n.title, ...(n.tags ?? [])].slice(0, 6);
    return {
      segment_id: `seg_${String(idx + 1).padStart(3, "0")}`,
      concept: n.title,
      keywords,
      target_duration_sec: n.duration_intent_sec ?? 10,
      priority: Number((n.importance ?? 0.5).toFixed(3)),
      query: keywords.join(" "),
    };
  });

  const script: ScriptDraftLine[] = segments.map((s, i) => {
    const subtitle_text = buildSubtitleText(s.concept, i, segments.length);
    // Same body for narration + subtitles (no duplicate “Concept.” prefix for TTS).
    return { segment_id: s.segment_id, text: subtitle_text, subtitle_text };
  });

  const effectVariants: string[][] = [
    ["slow_zoom_in_105", "title_lower_third", "taxonomy_rank_label", "denoise_light"],
    ["slow_zoom_out_103", "vignette_soft", "taxonomy_rank_label", "contrast_pop"],
    ["ken_burns_right", "title_lower_third", "warmth_minus_5", "clarity_soft"],
    ["ken_burns_left", "film_grain_subtle", "taxonomy_rank_label", "saturation_plus_8"],
    ["push_in_center", "clarity_soft", "taxonomy_rank_label", "highlight_rolloff"],
    ["parallax_mild", "title_lower_third", "denoise_light", "cool_tint_6"],
    ["micro_shake_stabilized", "contrast_pop", "taxonomy_rank_label", "shadow_lift_8"],
    ["slow_zoom_in_108", "vignette_soft", "title_lower_third", "warmth_plus_4"],
    ["pan_up_soft", "edge_soften", "taxonomy_rank_label", "desaturate_10"],
    ["pan_down_soft", "clarity_medium", "title_lower_third", "black_point_plus_3"],
  ];
  const annotations: EditAnnotation[] = segments.map((s, i) => {
    const variant = effectVariants[(i + (hashSeed(s.concept) % effectVariants.length)) % effectVariants.length];
    return {
      segment_id: s.segment_id,
      transition: pickTransition(i + (hashSeed(s.concept) % 3)),
      effects: variant,
      lut_hint: pickLut(i, segments.length, s.concept),
      audio_note: "mute_source_audio_narration_only",
    };
  });

  writeJson(path.resolve(projectDir, "shot-plan.json"), {
    generated_at: new Date().toISOString(),
    traversal: "depth_first",
    segments,
  });
  writeJson(path.resolve(projectDir, "edit-annotations.json"), {
    generated_at: new Date().toISOString(),
    annotations,
  });

  const scriptMd = ["# Walrus DFS Script", ""]
    .concat(script.map((s) => `## ${s.segment_id}\n${s.text}\n`))
    .join("\n");
  writeText(path.resolve(projectDir, "script.md"), scriptMd);

  writeJson(path.resolve(projectDir, "script-lines.json"), {
    generated_at: new Date().toISOString(),
    lines: script,
  });

  return { segments };
}
