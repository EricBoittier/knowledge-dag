import { spawnSync } from "node:child_process";
import path from "node:path";
import fs from "node:fs";
import { readJson } from "../fs";
import { ensureVariantsBootstrapped, mirrorVariantTimelineOutputsToProjectRoot, resolveActiveVariantWorkDir } from "../variants";
import { buildPlannerOutputs } from "../../../planner/src/plan";
import { runDiscovery } from "../../../media/src/select";
import { buildEditableSrt } from "../../../subtitles/src/build-srt";
import { exportDaVinciBundle } from "../../../timeline-davinci/src/export";
import { validateCropCoverage } from "../../../timeline-davinci/src/validate-crop";

type Stage =
  | "source"
  | "planner"
  | "discovery"
  | "select"
  | "normalize"
  | "annotations"
  | "subtitles"
  | "export"
  | "validate"
  | "render"
  | "upload";
const stages: Stage[] = [
  "source",
  "planner",
  "discovery",
  "select",
  "normalize",
  "annotations",
  "subtitles",
  "export",
  "validate",
  "render",
  "upload",
];

function arg(flag: string): string | undefined {
  const i = process.argv.indexOf(flag);
  if (i < 0 || i + 1 >= process.argv.length) return undefined;
  return process.argv[i + 1];
}
function has(flag: string): boolean {
  return process.argv.includes(flag);
}
function normalizeStage(input: string | undefined, fallback: Stage): Stage {
  const raw = String(input || "").trim().toLowerCase();
  if (!raw) return fallback;
  if (raw === "media") return "normalize";
  if (raw === "subtitle") return "subtitles";
  if (raw === "timeline") return "export";
  if (raw === "plan") return "planner";
  if (raw === "search") return "discovery";
  if (raw === "transcribe") return "subtitles";
  if (raw === "source") return "source";
  if (raw === "planner") return "planner";
  if (raw === "discovery") return "discovery";
  if (raw === "select") return "select";
  if (raw === "normalize") return "normalize";
  if (raw === "annotations") return "annotations";
  if (raw === "subtitles") return "subtitles";
  if (raw === "export") return "export";
  if (raw === "validate") return "validate";
  if (raw === "render") return "render";
  if (raw === "upload") return "upload";
  throw new Error(`Invalid stage: ${raw}`);
}
function runPy(script: string, args: string[]): void {
  const proc = spawnSync("python3", [script, ...args], { stdio: "inherit" });
  if (proc.status !== 0) throw new Error(`Python step failed: ${script}`);
}

function adaptLegacyDagVideoEditorLayout(projectDir: string): void {
  const legacyDataDir = path.resolve(projectDir, "data");
  if (!fs.existsSync(legacyDataDir) || !fs.statSync(legacyDataDir).isDirectory()) return;
  const mappings: Array<[string, string]> = [
    ["shot-plan.json", "shot-plan.json"],
    ["candidates.json", "candidates.json"],
    ["selected-clips.json", "selected-clips.json"],
    ["media-manifest.json", "media-manifest.json"],
    ["subtitles.srt", "subtitles.srt"],
    ["transcript.txt", "transcript.txt"],
  ];
  for (const [legacyName, canonicalName] of mappings) {
    const src = path.resolve(legacyDataDir, legacyName);
    const dst = path.resolve(projectDir, canonicalName);
    if (!fs.existsSync(src) || fs.existsSync(dst)) continue;
    fs.copyFileSync(src, dst);
  }
}

async function main() {
  const projectDir = path.resolve(arg("--project") || "./projects/walrus-dfs");
  adaptLegacyDagVideoEditorLayout(projectDir);
  ensureVariantsBootstrapped(projectDir);
  const variantFlag = String(arg("--variant") || "").trim();
  const { variantId, workDir: variantWorkDir } = resolveActiveVariantWorkDir(projectDir, variantFlag || undefined);
  const configPath = path.resolve("./config/pipeline.config.json");
  const cfg = readJson<any>(configPath);
  const dryRun = has("--dry-run");
  const skipUpload = has("--skip-upload");
  const from = normalizeStage(arg("--from-stage"), "source");
  const to = normalizeStage(arg("--to-stage"), "upload");
  const si = stages.indexOf(from);
  const ei = stages.indexOf(to);
  if (si < 0 || ei < 0 || si > ei) throw new Error("Invalid stage range");

  const should = (s: Stage) => stages.indexOf(s) >= si && stages.indexOf(s) <= ei;
  const pyProjectArgs = ["--project-dir", projectDir, ...(dryRun ? ["--dry-run"] : [])];
  const pyProjectConfigArgs = ["--project-dir", projectDir, "--config", configPath, ...(dryRun ? ["--dry-run"] : [])];
  const voiceoverProjectArgs = ["--project-dir", variantWorkDir, "--config", configPath, ...(dryRun ? ["--dry-run"] : [])];

  if (should("source")) {
    console.log("Stage 1/11: source");
  }
  if (should("planner")) {
    console.log("Stage 2/11: planner");
    buildPlannerOutputs(projectDir);
  }
  if (should("discovery")) {
    console.log("Stage 3/11: discovery");
    runDiscovery(projectDir, cfg.discovery);
  }
  if (should("select")) {
    console.log("Stage 4/11: select");
  }
  if (should("normalize")) {
    console.log("Stage 5/11: normalize");
    runPy(path.resolve("./packages/pipeline/src-py/download_normalize.py"), pyProjectConfigArgs);
    runPy(path.resolve("./packages/pipeline/src-py/validate_media.py"), pyProjectConfigArgs);
  }
  if (should("annotations")) {
    console.log("Stage 6/11: annotations");
  }
  if (should("subtitles")) {
    console.log(`Stage 7/11: subtitles (variant ${variantId})`);
    // Voiceover first so subtitles time to the fresh narration.wav duration.
    runPy(path.resolve("./packages/pipeline/src-py/generate_voiceover.py"), voiceoverProjectArgs);
    const subtitleArtifacts = buildEditableSrt(variantWorkDir);
    console.log(`SRT generated: ${subtitleArtifacts.srt}`);
    console.log(`Subtitle cues (FCPXML + tooling): ${subtitleArtifacts.subtitleCues}`);
    console.log(`Speaker style map: ${subtitleArtifacts.styleMap}`);
    console.log(`Resolve styling guide: ${subtitleArtifacts.resolveGuide}`);
  }
  if (should("export")) {
    console.log(`Stage 8/11: export (variant ${variantId})`);
    const out = exportDaVinciBundle(projectDir, cfg, { variantId, variantWorkDir });
    console.log(`FCPXML: ${out.fcpxml}`);
    console.log(`Import report: ${out.report}`);
    mirrorVariantTimelineOutputsToProjectRoot(projectDir, variantWorkDir);
    if (path.resolve(variantWorkDir) !== path.resolve(projectDir)) {
      console.log(`Mirrored FCPXML + reports to ${path.resolve(projectDir, "output")} (project root)`);
    }
  }
  if (should("validate")) {
    console.log(`Stage 9/11: validate (variant ${variantId})`);
    const out = validateCropCoverage(variantWorkDir);
    console.log(`Crop validation: ${out.resultPath}`);
    console.log(`Crop checks: ${out.passedChecks}/${out.totalChecks}`);
    mirrorVariantTimelineOutputsToProjectRoot(projectDir, variantWorkDir);
  }
  if (should("render")) {
    console.log("Stage 10/11: render");
    runPy(path.resolve("./packages/pipeline/src-py/render_timeline.py"), pyProjectArgs);
  }
  if (should("upload")) {
    console.log("Stage 11/11: upload");
    runPy(path.resolve("./packages/pipeline/src-py/upload_youtube.py"), [
      ...pyProjectArgs,
      ...(skipUpload ? ["--skip-upload"] : []),
    ]);
  }
  console.log("Build complete.");
}

main().catch((e) => {
  console.error(e instanceof Error ? e.message : String(e));
  process.exit(1);
});
