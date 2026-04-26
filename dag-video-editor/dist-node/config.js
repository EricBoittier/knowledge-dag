"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.loadConfig = loadConfig;
const node_path_1 = __importDefault(require("node:path"));
const fs_1 = require("./utils/fs");
function loadConfig(configPath) {
    const absConfigPath = node_path_1.default.resolve(configPath);
    const repoRoot = node_path_1.default.resolve(node_path_1.default.dirname(absConfigPath), "..");
    const config = (0, fs_1.readJsonFile)(absConfigPath);
    config.dag.snapshot_path = (0, fs_1.resolveFromRepoRoot)(repoRoot, config.dag.snapshot_path);
    config.media.download_dir = (0, fs_1.resolveFromRepoRoot)(repoRoot, config.media.download_dir);
    config.media.normalized_dir = (0, fs_1.resolveFromRepoRoot)(repoRoot, config.media.normalized_dir);
    config.transcription.output_transcript_json = (0, fs_1.resolveFromRepoRoot)(repoRoot, config.transcription.output_transcript_json);
    config.subtitles.output_srt = (0, fs_1.resolveFromRepoRoot)(repoRoot, config.subtitles.output_srt);
    config.subtitles.output_text = (0, fs_1.resolveFromRepoRoot)(repoRoot, config.subtitles.output_text);
    config.timeline.output_fcpxml = (0, fs_1.resolveFromRepoRoot)(repoRoot, config.timeline.output_fcpxml);
    config.render.output_video = (0, fs_1.resolveFromRepoRoot)(repoRoot, config.render.output_video);
    return { config, repoRoot, configPath: absConfigPath };
}
