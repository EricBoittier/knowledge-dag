import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { validateCropCoverage } from "./validate-crop";

function mkProjectDir(): string {
  return fs.mkdtempSync(path.join(os.tmpdir(), "ai-director-crop-"));
}

test("validateCropCoverage passes when styled assets are mapped in FCPXML", () => {
  const projectDir = mkProjectDir();
  fs.mkdirSync(path.resolve(projectDir, "output/processed"), { recursive: true });
  fs.writeFileSync(
    path.resolve(projectDir, "media-manifest.json"),
    JSON.stringify(
      {
        entries: [
          {
            segment_id: "seg_001",
            normalized: "/tmp/seg_001.normalized.mov",
            crop: { x: 10, y: 20, width: 400, height: 300 },
          },
          {
            segment_id: "seg_002",
            normalized: "/tmp/seg_002.normalized.mov",
            crop: { x: 0, y: 0, width: 0, height: 0 },
          },
        ],
      },
      null,
      2
    )
  );
  fs.writeFileSync(path.resolve(projectDir, "output/processed/seg_001.normalized.styled.mov"), "x");
  fs.writeFileSync(
    path.resolve(projectDir, "output/timeline_davinci_resolve.fcpxml"),
    "<fcpxml><resources><asset name=\"seg_001.normalized.styled.mov\" /></resources></fcpxml>"
  );

  const out = validateCropCoverage(projectDir);
  assert.equal(out.totalChecks, 1);
  assert.equal(out.passedChecks, 1);
});

test("validateCropCoverage fails when FCPXML is not mapped to styled assets", () => {
  const projectDir = mkProjectDir();
  fs.mkdirSync(path.resolve(projectDir, "output/processed"), { recursive: true });
  fs.writeFileSync(
    path.resolve(projectDir, "media-manifest.json"),
    JSON.stringify(
      {
        entries: [
          {
            segment_id: "seg_003",
            normalized: "/tmp/seg_003.normalized.mov",
            crop: { x: 12, y: 12, width: 500, height: 500 },
          },
        ],
      },
      null,
      2
    )
  );
  fs.writeFileSync(path.resolve(projectDir, "output/processed/seg_003.normalized.styled.mov"), "x");
  fs.writeFileSync(path.resolve(projectDir, "output/timeline_davinci_resolve.fcpxml"), "<fcpxml></fcpxml>");

  const out = validateCropCoverage(projectDir);
  assert.equal(out.totalChecks, 1);
  assert.equal(out.passedChecks, 0);
  const validation = JSON.parse(fs.readFileSync(out.resultPath, "utf8"));
  assert.equal(validation.status, "fail");
});
