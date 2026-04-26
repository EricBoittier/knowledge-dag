import path from "node:path";
import { PipelineConfig } from "../config";
import { DagAdapter } from "../dag/adapter";
import { ShotPlan, ShotSegment } from "../types";
import { writeJsonFile } from "../utils/fs";

export function generateShotPlan(config: PipelineConfig, repoRoot: string): ShotPlan {
  const adapter = new DagAdapter(config);
  const concepts = adapter.listNarrativeOrder(config.dag.max_segments);
  const count = Math.max(1, concepts.length);
  const perSegment = Math.max(
    6,
    Math.floor(config.planner.target_total_runtime_sec / count) || config.planner.default_segment_duration_sec
  );

  const segments: ShotSegment[] = concepts.map((c, idx) => {
    const keywords = [c.title, ...(c.tags ?? [])]
      .map((k) => k.trim())
      .filter((k) => k.length > 0)
      .slice(0, 6);
    return {
      segment_id: `seg_${String(idx + 1).padStart(3, "0")}`,
      concept: c.title,
      keywords,
      target_duration_sec: perSegment,
      priority: Number((c.importance ?? 0.5).toFixed(3)),
      query: keywords.join(" "),
    };
  });

  const plan: ShotPlan = {
    generated_at: new Date().toISOString(),
    target_total_runtime_sec: config.planner.target_total_runtime_sec,
    segments,
  };

  writeJsonFile(path.resolve(repoRoot, "data/shot-plan.json"), plan);
  return plan;
}
