import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { exportDaVinciBundle } from "./export";

function mkProject(): string {
  return fs.mkdtempSync(path.join(os.tmpdir(), "ai-director-export-var-"));
}

test("exportDaVinciBundle writes variant output and studio text lane", () => {
  const projectDir = mkProject();
  const variantWorkDir = path.join(projectDir, "variants", "short");
  fs.mkdirSync(path.join(variantWorkDir, "output"), { recursive: true });
  fs.writeFileSync(
    path.join(variantWorkDir, "media-manifest.json"),
    JSON.stringify({ generated_at: new Date().toISOString(), entries: [] }, null, 2)
  );
  fs.writeFileSync(
    path.join(variantWorkDir, "timeline-annotations.json"),
    JSON.stringify(
      {
        schema_version: 1,
        generated_at: new Date().toISOString(),
        mode: "studio",
        markers: [{ id: "m1", t_seconds: 1, label: "Test marker" }],
        text_overlays: [
          {
            id: "t1",
            start: 0.5,
            end: 2.0,
            text: "Hello studio",
            lane: -3,
          },
        ],
        media_overlays: [],
      },
      null,
      2
    )
  );

  const cfg = {
    timeline: { name: "UnitTest", width: 1920, height: 1080 },
    caption: { enabled: false, lane: -2, font: "Open Sans", font_size: 52, font_face: "Regular", font_color_hex: "#FFFFFF" },
  };

  const out = exportDaVinciBundle(projectDir, cfg, { variantId: "short", variantWorkDir });
  assert.ok(fs.existsSync(out.fcpxml));
  const xml = fs.readFileSync(out.fcpxml, "utf8");
  assert.match(xml, /Hello studio/);
  assert.match(xml, /lane="-3"/);
  assert.match(xml, /Test marker/);
  assert.match(xml, /\(short\)/);
  const emPath = path.join(variantWorkDir, "output", "export-manifest.json");
  assert.ok(fs.existsSync(emPath));
  const em = JSON.parse(fs.readFileSync(emPath, "utf8"));
  assert.equal(em.variant_id, "short");
  const tiPath = path.join(variantWorkDir, "output", "timeline-index.json");
  assert.ok(fs.existsSync(tiPath));
  const ti = JSON.parse(fs.readFileSync(tiPath, "utf8"));
  assert.ok(Array.isArray(ti.rows));
  assert.ok(ti.rows.length >= 2);
  const cats = ti.rows.map((r: { category: string }) => r.category);
  assert.ok(cats.includes("studio_text"));
  assert.ok(cats.includes("marker"));
});
