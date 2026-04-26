import fs from "node:fs";
import path from "node:path";
import { readJson, writeJson, writeText } from "../../core/src/fs";

type ManifestEntry = {
  segment_id: string;
  normalized?: string;
  downloaded?: string;
  crop?: { x?: number; y?: number; width?: number; height?: number };
};

type CropCheck = {
  segment_id: string;
  expected_crop: { x: number; y: number; width: number; height: number };
  expects_processed_asset: boolean;
  processed_file_exists: boolean;
  fcpxml_references_processed_asset: boolean;
  passed: boolean;
  notes: string[];
};

function baseNameForEntry(e: ManifestEntry): string {
  const src = String(e.normalized || e.downloaded || "");
  if (!src) return e.segment_id;
  return path.parse(path.basename(src)).name;
}

function hasCrop(e: ManifestEntry): boolean {
  const w = Number(e.crop?.width || 0);
  const h = Number(e.crop?.height || 0);
  return w > 0 && h > 0;
}

export function validateCropCoverage(projectDir: string): {
  resultPath: string;
  passedChecks: number;
  totalChecks: number;
} {
  const mediaManifestPath = path.resolve(projectDir, "media-manifest.json");
  const fcpxmlPath = path.resolve(projectDir, "output", "timeline_davinci_resolve.fcpxml");
  const reportPath = path.resolve(projectDir, "output", "import-report.md");
  const outPath = path.resolve(projectDir, "output", "crop-validation.json");
  const processedDir = path.resolve(projectDir, "output", "processed");
  const media = readJson<{ entries: ManifestEntry[] }>(mediaManifestPath);
  const fcpxml = fs.existsSync(fcpxmlPath) ? fs.readFileSync(fcpxmlPath, "utf8") : "";

  const checks: CropCheck[] = [];
  for (const entry of media.entries || []) {
    if (!hasCrop(entry)) continue;
    const crop = {
      x: Number(entry.crop?.x || 0),
      y: Number(entry.crop?.y || 0),
      width: Number(entry.crop?.width || 0),
      height: Number(entry.crop?.height || 0),
    };
    const base = baseNameForEntry(entry);
    const processedName = `${base}.styled.mov`;
    const processedPath = path.resolve(processedDir, processedName);
    const processedExists = fs.existsSync(processedPath);
    const fcpxmlRefsProcessed = fcpxml.includes(processedName);
    const notes: string[] = [];
    if (!processedExists) notes.push(`missing processed file ${processedName}`);
    if (!fcpxmlRefsProcessed) notes.push(`FCPXML missing processed asset ${processedName}`);
    checks.push({
      segment_id: entry.segment_id,
      expected_crop: crop,
      expects_processed_asset: true,
      processed_file_exists: processedExists,
      fcpxml_references_processed_asset: fcpxmlRefsProcessed,
      passed: processedExists && fcpxmlRefsProcessed,
      notes,
    });
  }

  const passedChecks = checks.filter((c) => c.passed).length;
  const totalChecks = checks.length;
  const payload = {
    generated_at: new Date().toISOString(),
    project_dir: projectDir,
    fcpxml_path: fcpxmlPath,
    checked_segments: totalChecks,
    passed_checks: passedChecks,
    status: totalChecks === passedChecks ? "pass" : "fail",
    checks,
  };
  writeJson(outPath, payload);

  const reportLines = [
    "## Crop validation",
    totalChecks === 0 ? "- No segments required crop validation." : `- Crop checks passed: ${passedChecks}/${totalChecks}`,
    ...checks.map((c) => `- ${c.segment_id}: ${c.passed ? "PASS" : "FAIL"} (${c.notes.join("; ") || "processed asset mapped"})`),
  ];
  const existingReport = fs.existsSync(reportPath) ? fs.readFileSync(reportPath, "utf8") : "# DaVinci Import Report\n";
  const merged = existingReport.includes("## Crop validation")
    ? existingReport.replace(/## Crop validation[\s\S]*$/m, reportLines.join("\n"))
    : `${existingReport.trimEnd()}\n\n${reportLines.join("\n")}\n`;
  writeText(reportPath, merged);

  return { resultPath: outPath, passedChecks, totalChecks };
}
