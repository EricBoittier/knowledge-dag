"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const node_child_process_1 = require("node:child_process");
const node_path_1 = __importDefault(require("node:path"));
const config_1 = require("../config");
const generate_shot_plan_1 = require("../planner/generate-shot-plan");
const search_youtube_1 = require("../search/search-youtube");
const build_fcpxml_1 = require("../timeline/build-fcpxml");
function stageIndex(s) {
    return ["plan", "search", "media", "transcribe", "subtitles", "timeline", "render", "upload"].indexOf(s);
}
function parseArg(flag) {
    const i = process.argv.indexOf(flag);
    if (i < 0 || i + 1 >= process.argv.length) {
        return undefined;
    }
    return process.argv[i + 1];
}
function hasFlag(flag) {
    return process.argv.includes(flag);
}
function runPython(script, args) {
    const proc = (0, node_child_process_1.spawnSync)("python3", [script, ...args], { stdio: "inherit" });
    if (proc.status !== 0) {
        throw new Error(`Python step failed: ${script}`);
    }
}
async function main() {
    const configPath = parseArg("--config") ?? node_path_1.default.resolve(process.cwd(), "config/pipeline.config.json");
    const fromStage = parseArg("--from-stage") ?? "plan";
    const toStage = parseArg("--to-stage") ?? "upload";
    const dryRun = hasFlag("--dry-run");
    const skipUpload = hasFlag("--skip-upload");
    const { config, repoRoot, configPath: absConfigPath } = (0, config_1.loadConfig)(configPath);
    const pyArgsBase = ["--config", absConfigPath, "--repo-root", repoRoot, ...(dryRun ? ["--dry-run"] : [])];
    const start = stageIndex(fromStage);
    const end = stageIndex(toStage);
    if (start < 0 || end < 0 || start > end) {
        throw new Error("Invalid --from-stage/--to-stage range");
    }
    if (start <= stageIndex("plan") && end >= stageIndex("plan")) {
        console.log("Stage: plan");
        (0, generate_shot_plan_1.generateShotPlan)(config, repoRoot);
    }
    if (start <= stageIndex("search") && end >= stageIndex("search")) {
        console.log("Stage: search");
        await (0, search_youtube_1.searchYoutubeAndSelect)(config, repoRoot);
    }
    if (start <= stageIndex("media") && end >= stageIndex("media")) {
        console.log("Stage: media");
        runPython(node_path_1.default.resolve(repoRoot, "src-py/media/download_and_normalize.py"), pyArgsBase);
        runPython(node_path_1.default.resolve(repoRoot, "src-py/media/validate_media.py"), pyArgsBase);
    }
    if (start <= stageIndex("transcribe") && end >= stageIndex("transcribe")) {
        console.log("Stage: transcribe");
        runPython(node_path_1.default.resolve(repoRoot, "src-py/transcribe/transcribe_local.py"), pyArgsBase);
    }
    if (start <= stageIndex("subtitles") && end >= stageIndex("subtitles")) {
        console.log("Stage: subtitles");
        runPython(node_path_1.default.resolve(repoRoot, "src-py/transcribe/build_subtitles.py"), pyArgsBase);
    }
    if (start <= stageIndex("timeline") && end >= stageIndex("timeline")) {
        console.log("Stage: timeline");
        const out = (0, build_fcpxml_1.buildFcpxmlFromMediaManifest)(config, repoRoot);
        console.log(`FCPXML generated: ${out}`);
    }
    if (start <= stageIndex("render") && end >= stageIndex("render")) {
        console.log("Stage: render");
        runPython(node_path_1.default.resolve(repoRoot, "src-py/render/render_timeline.py"), pyArgsBase);
    }
    if (start <= stageIndex("upload") && end >= stageIndex("upload")) {
        console.log("Stage: upload");
        runPython(node_path_1.default.resolve(repoRoot, "src-py/upload/upload_youtube.py"), [
            ...pyArgsBase,
            ...(skipUpload ? ["--skip-upload"] : []),
        ]);
    }
    console.log("Pipeline finished.");
    console.log("Artifacts:");
    console.log(`- ${node_path_1.default.resolve(repoRoot, "data/shot-plan.json")}`);
    console.log(`- ${node_path_1.default.resolve(repoRoot, "data/candidates.json")}`);
    console.log(`- ${node_path_1.default.resolve(repoRoot, "data/selected-clips.json")}`);
    console.log(`- ${node_path_1.default.resolve(repoRoot, "data/media-manifest.json")}`);
    console.log(`- ${node_path_1.default.resolve(repoRoot, "data/transcript.json")}`);
    console.log(`- ${node_path_1.default.resolve(repoRoot, "data/subtitles.srt")}`);
    console.log(`- ${node_path_1.default.resolve(repoRoot, "data/transcript.txt")}`);
    console.log(`- ${config.timeline.output_fcpxml}`);
}
main().catch((err) => {
    console.error(err instanceof Error ? err.message : String(err));
    process.exit(1);
});
