"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.generateShotPlan = generateShotPlan;
const node_path_1 = __importDefault(require("node:path"));
const adapter_1 = require("../dag/adapter");
const fs_1 = require("../utils/fs");
function generateShotPlan(config, repoRoot) {
    const adapter = new adapter_1.DagAdapter(config);
    const concepts = adapter.listNarrativeOrder(config.dag.max_segments);
    const count = Math.max(1, concepts.length);
    const perSegment = Math.max(6, Math.floor(config.planner.target_total_runtime_sec / count) || config.planner.default_segment_duration_sec);
    const segments = concepts.map((c, idx) => {
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
    const plan = {
        generated_at: new Date().toISOString(),
        target_total_runtime_sec: config.planner.target_total_runtime_sec,
        segments,
    };
    (0, fs_1.writeJsonFile)(node_path_1.default.resolve(repoRoot, "data/shot-plan.json"), plan);
    return plan;
}
