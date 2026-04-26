import { spawnSync } from "node:child_process";
import path from "node:path";
import { loadConfig } from "../config";
import { generateShotPlan } from "../planner/generate-shot-plan";
import { searchYoutubeAndSelect } from "../search/search-youtube";
import { buildFcpxmlFromMediaManifest } from "../timeline/build-fcpxml";

type Stage = "plan" | "search" | "media" | "transcribe" | "subtitles" | "timeline" | "render" | "upload";

function stageIndex(s: Stage): number {
  return ["plan", "search", "media", "transcribe", "subtitles", "timeline", "render", "upload"].indexOf(s);
}

function parseArg(flag: string): string | undefined {
  const i = process.argv.indexOf(flag);
  if (i < 0 || i + 1 >= process.argv.length) {
    return undefined;
  }
  return process.argv[i + 1];
}

function hasFlag(flag: string): boolean {
  return process.argv.includes(flag);
}

function runPython(script: string, args: string[]): void {
  const proc = spawnSync("python3", [script, ...args], { stdio: "inherit" });
  if (proc.status !== 0) {
    throw new Error(`Python step failed: ${script}`);
  }
}

async function main(): Promise<void> {
  const configPath = parseArg("--config") ?? path.resolve(process.cwd(), "config/pipeline.config.json");
  const fromStage = (parseArg("--from-stage") as Stage | undefined) ?? "plan";
  const toStage = (parseArg("--to-stage") as Stage | undefined) ?? "upload";
  const dryRun = hasFlag("--dry-run");
  const skipUpload = hasFlag("--skip-upload");

  const { config, repoRoot, configPath: absConfigPath } = loadConfig(configPath);
  const pyArgsBase = ["--config", absConfigPath, "--repo-root", repoRoot, ...(dryRun ? ["--dry-run"] : [])];
  const start = stageIndex(fromStage);
  const end = stageIndex(toStage);

  if (start < 0 || end < 0 || start > end) {
    throw new Error("Invalid --from-stage/--to-stage range");
  }

  if (start <= stageIndex("plan") && end >= stageIndex("plan")) {
    console.log("Stage: plan");
    generateShotPlan(config, repoRoot);
  }
  if (start <= stageIndex("search") && end >= stageIndex("search")) {
    console.log("Stage: search");
    await searchYoutubeAndSelect(config, repoRoot);
  }
  if (start <= stageIndex("media") && end >= stageIndex("media")) {
    console.log("Stage: media");
    runPython(path.resolve(repoRoot, "src-py/media/download_and_normalize.py"), pyArgsBase);
    runPython(path.resolve(repoRoot, "src-py/media/validate_media.py"), pyArgsBase);
  }
  if (start <= stageIndex("transcribe") && end >= stageIndex("transcribe")) {
    console.log("Stage: transcribe");
    runPython(path.resolve(repoRoot, "src-py/transcribe/transcribe_local.py"), pyArgsBase);
  }
  if (start <= stageIndex("subtitles") && end >= stageIndex("subtitles")) {
    console.log("Stage: subtitles");
    runPython(path.resolve(repoRoot, "src-py/transcribe/build_subtitles.py"), pyArgsBase);
  }
  if (start <= stageIndex("timeline") && end >= stageIndex("timeline")) {
    console.log("Stage: timeline");
    const out = buildFcpxmlFromMediaManifest(config, repoRoot);
    console.log(`FCPXML generated: ${out}`);
  }
  if (start <= stageIndex("render") && end >= stageIndex("render")) {
    console.log("Stage: render");
    runPython(path.resolve(repoRoot, "src-py/render/render_timeline.py"), pyArgsBase);
  }
  if (start <= stageIndex("upload") && end >= stageIndex("upload")) {
    console.log("Stage: upload");
    runPython(path.resolve(repoRoot, "src-py/upload/upload_youtube.py"), [
      ...pyArgsBase,
      ...(skipUpload ? ["--skip-upload"] : []),
    ]);
  }

  console.log("Pipeline finished.");
  console.log("Artifacts:");
  console.log(`- ${path.resolve(repoRoot, "data/shot-plan.json")}`);
  console.log(`- ${path.resolve(repoRoot, "data/candidates.json")}`);
  console.log(`- ${path.resolve(repoRoot, "data/selected-clips.json")}`);
  console.log(`- ${path.resolve(repoRoot, "data/media-manifest.json")}`);
  console.log(`- ${path.resolve(repoRoot, "data/transcript.json")}`);
  console.log(`- ${path.resolve(repoRoot, "data/subtitles.srt")}`);
  console.log(`- ${path.resolve(repoRoot, "data/transcript.txt")}`);
  console.log(`- ${config.timeline.output_fcpxml}`);
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : String(err));
  process.exit(1);
});
