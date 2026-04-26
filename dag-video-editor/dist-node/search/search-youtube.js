"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.searchYoutubeAndSelect = searchYoutubeAndSelect;
const node_path_1 = __importDefault(require("node:path"));
const fs_1 = require("../utils/fs");
const discovery_1 = require("./discovery");
async function searchYoutubeAndSelect(config, repoRoot) {
    const shotPlanPath = node_path_1.default.resolve(repoRoot, "data/shot-plan.json");
    const shotPlan = (0, fs_1.readJsonFile)(shotPlanPath);
    const allCandidates = [];
    const selections = [];
    for (const seg of shotPlan.segments) {
        const filtered = (0, discovery_1.discoverCandidates)(seg, config);
        const selected = filtered
            .sort((a, b) => b.score - a.score)
            .slice(0, config.youtube.selected_per_segment);
        allCandidates.push(...filtered);
        selections.push({
            segment_id: seg.segment_id,
            concept: seg.concept,
            query: seg.query,
            selected,
        });
    }
    (0, fs_1.writeJsonFile)(node_path_1.default.resolve(repoRoot, "data/candidates.json"), {
        generated_at: new Date().toISOString(),
        candidates: allCandidates,
    });
    (0, fs_1.writeJsonFile)(node_path_1.default.resolve(repoRoot, "data/selected-clips.json"), {
        generated_at: new Date().toISOString(),
        segments: selections,
    });
    return selections;
}
