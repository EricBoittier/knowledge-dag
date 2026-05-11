import fs from "node:fs";
import path from "node:path";
import type { ExportVariantDescriptor, VariantsIndexDoc } from "./types";
import { writeJson } from "./fs";

export const VARIANTS_SCHEMA_VERSION = 1;

const FILES_TO_SEED = [
  "media-manifest.json",
  "script-lines.json",
  "script.md",
  "edit-annotations.json",
  "timeline-annotations.json",
] as const;

export function variantsIndexPath(projectDir: string): string {
  return path.resolve(projectDir, "variants.json");
}

export function variantDir(projectDir: string, variantId: string): string {
  return path.resolve(projectDir, "variants", variantId);
}

export function defaultVariantsIndex(): VariantsIndexDoc {
  return {
    schema_version: VARIANTS_SCHEMA_VERSION,
    generated_at: new Date().toISOString(),
    active_variant_id: "default",
    variants: [
      {
        id: "default",
        label: "Default cut",
        target_duration_sec: undefined,
        notes: undefined,
      },
    ],
  };
}

export function readVariantsIndex(projectDir: string): VariantsIndexDoc {
  const p = variantsIndexPath(projectDir);
  if (!fs.existsSync(p)) return defaultVariantsIndex();
  const raw = JSON.parse(fs.readFileSync(p, "utf8")) as VariantsIndexDoc;
  if (!raw.active_variant_id) raw.active_variant_id = "default";
  if (!Array.isArray(raw.variants)) raw.variants = [];
  return raw;
}

export function writeVariantsIndex(projectDir: string, doc: VariantsIndexDoc): void {
  doc.generated_at = new Date().toISOString();
  writeJson(variantsIndexPath(projectDir), doc);
}

export function ensureVariantDirs(projectDir: string, variantId: string): string {
  const dir = variantDir(projectDir, variantId);
  fs.mkdirSync(path.join(dir, "output"), { recursive: true });
  return dir;
}

function copyIfExists(src: string, dst: string): void {
  if (fs.existsSync(src)) fs.copyFileSync(src, dst);
}

/** Seed variant folder from project root when missing key files. */
export function seedVariantFromRoot(projectDir: string, variantId: string): void {
  const dir = ensureVariantDirs(projectDir, variantId);
  for (const name of FILES_TO_SEED) {
    const src = path.resolve(projectDir, name);
    const dst = path.resolve(dir, name);
    if (!fs.existsSync(dst) && fs.existsSync(src)) {
      fs.copyFileSync(src, dst);
    }
  }
  const taPath = path.resolve(dir, "timeline-annotations.json");
  if (!fs.existsSync(taPath)) {
    writeJson(taPath, emptyTimelineAnnotations());
  }
  const slPath = path.resolve(dir, "script-lines.json");
  if (!fs.existsSync(slPath)) {
    writeJson(slPath, { generated_at: new Date().toISOString(), lines: [] });
  }
}

export function emptyTimelineAnnotations(): {
  schema_version: 1;
  generated_at: string;
  mode: "simple" | "studio";
  markers: unknown[];
  text_overlays: unknown[];
  media_overlays: unknown[];
} {
  return {
    schema_version: 1,
    generated_at: new Date().toISOString(),
    mode: "simple",
    markers: [],
    text_overlays: [],
    media_overlays: [],
  };
}

/** Ensure variants.json exists and default variant is bootstrapped from legacy root files. */
export function ensureVariantsBootstrapped(projectDir: string): VariantsIndexDoc {
  const idxPath = variantsIndexPath(projectDir);
  let idx: VariantsIndexDoc;
  if (!fs.existsSync(idxPath)) {
    idx = defaultVariantsIndex();
    writeVariantsIndex(projectDir, idx);
  } else {
    idx = readVariantsIndex(projectDir);
  }
  const hasDescriptor = idx.variants.some((v) => v.id === "default");
  if (!hasDescriptor) {
    idx.variants.unshift({
      id: "default",
      label: "Default cut",
    });
    writeVariantsIndex(projectDir, idx);
  }
  seedVariantFromRoot(projectDir, "default");
  return readVariantsIndex(projectDir);
}

export function resolveActiveVariantWorkDir(projectDir: string, variantIdOverride?: string): {
  variantId: string;
  workDir: string;
} {
  const idx = readVariantsIndex(projectDir);
  const variantId = String(variantIdOverride || idx.active_variant_id || "default").trim() || "default";
  ensureVariantDirs(projectDir, variantId);
  seedVariantFromRoot(projectDir, variantId);
  return { variantId, workDir: variantDir(projectDir, variantId) };
}

export function setActiveVariant(projectDir: string, variantId: string): VariantsIndexDoc {
  const idx = readVariantsIndex(projectDir);
  if (!idx.variants.some((v) => v.id === variantId)) {
    throw new Error(`unknown_variant:${variantId}`);
  }
  idx.active_variant_id = variantId;
  writeVariantsIndex(projectDir, idx);
  return idx;
}

export function upsertVariantDescriptor(projectDir: string, d: ExportVariantDescriptor): VariantsIndexDoc {
  const idx = readVariantsIndex(projectDir);
  const i = idx.variants.findIndex((v) => v.id === d.id);
  if (i < 0) idx.variants.push(d);
  else idx.variants[i] = { ...idx.variants[i], ...d };
  writeVariantsIndex(projectDir, idx);
  return idx;
}

/** Copy an existing variant directory to a new id (full file tree). */
export function duplicateVariant(projectDir: string, fromId: string, toId: string, label?: string): void {
  const src = variantDir(projectDir, fromId);
  const dst = variantDir(projectDir, toId);
  if (!fs.existsSync(src)) throw new Error(`source_variant_missing:${fromId}`);
  if (fs.existsSync(dst)) throw new Error(`variant_already_exists:${toId}`);
  fs.cpSync(src, dst, { recursive: true });
  upsertVariantDescriptor(projectDir, {
    id: toId,
    label: label || toId,
  });
}

/** Copy root media-manifest (and optional edit-annotations) into variant from normalize output. */
export function syncVariantMediaFromRoot(projectDir: string, variantId: string): void {
  const dir = ensureVariantDirs(projectDir, variantId);
  copyIfExists(path.resolve(projectDir, "media-manifest.json"), path.resolve(dir, "media-manifest.json"));
  copyIfExists(path.resolve(projectDir, "edit-annotations.json"), path.resolve(dir, "edit-annotations.json"));
}

/**
 * Copy timeline export sidecars into `projectDir/output/` so the project root still has FCPXML/reports
 * (variant-aware export writes canonical files under `variants/<id>/output/`).
 * FCPXML `file://` paths remain absolute and may reference narration/processed assets under the variant folder.
 */
export function mirrorVariantTimelineOutputsToProjectRoot(projectDir: string, variantWorkDir: string): void {
  const vOut = path.resolve(variantWorkDir, "output");
  const rootOut = path.resolve(projectDir, "output");
  if (!fs.existsSync(vOut)) return;
  if (path.resolve(vOut) === path.resolve(rootOut)) return;
  fs.mkdirSync(rootOut, { recursive: true });
  const names = [
    "timeline_davinci_resolve.fcpxml",
    "import-report.md",
    "export-manifest.json",
    "timeline-index.json",
    "timeline-index.md",
    "crop-validation.json",
  ];
  for (const name of names) {
    const src = path.join(vOut, name);
    const dst = path.join(rootOut, name);
    if (fs.existsSync(src)) fs.copyFileSync(src, dst);
  }
}
