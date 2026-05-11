import path from "node:path";
import fs from "node:fs";
import { spawnSync } from "node:child_process";
import { readJson, writeJson, writeText } from "../../core/src/fs";
import type { MediaOverlay, TimelineAnnotationsDoc, TimelineIndexDoc, TimelineIndexRow } from "../../core/src/types";

function secToRat(sec: number, scale = 24000): string {
  return `${Math.max(0, Math.round(sec * scale))}/${scale}s`;
}

function esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/** FCPXML `fontColor` uses normalized RGBA components (0–1). */
function hexToFcpxmlRgba(hex: string): string {
  const m = /^#?([0-9a-fA-F]{6})$/.exec(String(hex || "").trim());
  if (!m) return "1 1 1 1";
  const n = parseInt(m[1], 16);
  const r = ((n >> 16) & 255) / 255;
  const g = ((n >> 8) & 255) / 255;
  const b = (n & 255) / 255;
  return `${r} ${g} ${b} 1`;
}

type SubtitleCueFile = {
  cues: Array<{ index: number; start: number; end: number; text: string }>;
};

function pickExistingSource(e: any): string {
  const normalized = e?.normalized ? path.resolve(String(e.normalized)) : "";
  const downloaded = e?.downloaded ? path.resolve(String(e.downloaded)) : "";
  if (normalized && fs.existsSync(normalized)) return normalized;
  if (downloaded && fs.existsSync(downloaded)) return downloaded;
  return normalized || downloaded || "";
}

function filterForEffect(effect: string): string[] {
  switch (effect) {
    case "slow_zoom_in_105":
      return ["scale=iw*1.05:ih*1.05,crop=iw/1.05:ih/1.05:(iw-ow)/2:(ih-oh)/2"];
    case "slow_zoom_in_108":
      return ["scale=iw*1.08:ih*1.08,crop=iw/1.08:ih/1.08:(iw-ow)/2:(ih-oh)/2"];
    case "slow_zoom_out_103":
      return ["scale=iw*1.03:ih*1.03,crop=iw/1.03:ih/1.03:(iw-ow)/2:(ih-oh)/2"];
    case "ken_burns_right":
      return ["crop=iw*0.92:ih*0.92:x=(iw-ow)*0.25:y=(ih-oh)*0.5"];
    case "ken_burns_left":
      return ["crop=iw*0.92:ih*0.92:x=(iw-ow)*0.75:y=(ih-oh)*0.5"];
    case "push_in_center":
      return ["scale=iw*1.04:ih*1.04,crop=iw/1.04:ih/1.04:(iw-ow)/2:(ih-oh)/2"];
    case "pan_up_soft":
      return ["crop=iw*0.95:ih*0.95:x=(iw-ow)/2:y=(ih-oh)*0.3"];
    case "pan_down_soft":
      return ["crop=iw*0.95:ih*0.95:x=(iw-ow)/2:y=(ih-oh)*0.7"];
    case "denoise_light":
      return ["hqdn3d=1.5:1.5:3:3"];
    case "vignette_soft":
      return ["vignette=angle=PI/6"];
    case "contrast_pop":
      return ["eq=contrast=1.12:brightness=0.01:saturation=1.06"];
    case "clarity_soft":
      return ["unsharp=3:3:0.35:3:3:0.0"];
    case "clarity_medium":
      return ["unsharp=5:5:0.55:5:5:0.0"];
    case "warmth_minus_5":
      return ["colorbalance=rs=-0.02:gs=0.0:bs=0.02"];
    case "warmth_plus_4":
      return ["colorbalance=rs=0.02:gs=0.0:bs=-0.02"];
    case "saturation_plus_8":
      return ["eq=saturation=1.08"];
    case "desaturate_10":
      return ["eq=saturation=0.9"];
    case "cool_tint_6":
      return ["colorbalance=rs=-0.02:bs=0.03"];
    case "shadow_lift_8":
      return ["curves=all='0/0.08 0.4/0.45 1/1'"];
    case "highlight_rolloff":
      return ["curves=all='0/0 0.7/0.68 1/0.93'"];
    case "black_point_plus_3":
      return ["curves=all='0/0.03 1/1'"];
    case "film_grain_subtle":
      return ["noise=alls=6:allf=t"];
    case "edge_soften":
      return ["gblur=sigma=0.35"];
    default:
      return [];
  }
}

function filterForLutHint(lutHint: string): string[] {
  switch (lutHint) {
    case "soft_contrast_teal":
      return ["eq=contrast=1.08:saturation=1.03,colorbalance=bs=0.02"];
    case "cool_blue_lift":
      return ["colorbalance=bs=0.03:rs=-0.01,eq=brightness=0.01"];
    case "cold_arctic_finish":
      return ["colorbalance=rs=-0.03:bs=0.05,eq=contrast=1.06:saturation=0.94"];
    case "warm_film_stock":
      return ["colorbalance=rs=0.03:bs=-0.02,eq=contrast=1.05:saturation=1.04"];
    case "natural_green_lift":
      return ["colorbalance=gs=0.02,eq=saturation=1.02"];
    case "high_clarity_newsreel":
      return ["eq=contrast=1.1:saturation=0.97,unsharp=5:5:0.45:5:5:0.0"];
    default:
      return [];
  }
}

function probeDurationSec(filePath: string): number {
  const p = spawnSync(
    "ffprobe",
    ["-v", "error", "-show_entries", "format=duration", "-of", "default=nokey=1:noprint_wrappers=1", filePath],
    { encoding: "utf8" }
  );
  const v = Number((p.stdout || "").trim());
  return Number.isFinite(v) && v > 0 ? v : 0;
}

function sanitizeOverlayFileId(id: string): string {
  const s = String(id || "ov").replace(/[^a-zA-Z0-9._-]+/g, "_");
  const t = s.slice(0, 64).replace(/^_+/, "");
  return t || "overlay";
}

/** Transcode / bake studio overlays into `processed/` (DNxHR mezzanine like spine clips). */
function processStudioMediaOverlayToProcessed(
  mo: MediaOverlay,
  abs: string,
  processedDir: string,
  cfg: any,
  processedLog: string[]
): {
  outPath: string;
  clipStartInSource: number;
  assetDurationSec: number;
  clipDurOnTimeline: number;
  hasVideo: "0" | "1";
  hasAudio: "0" | "1";
  audCh: string;
  audRate: string;
} | null {
  const kind = mo.kind;
  const startSrc = Math.max(0, Number(mo.source_in ?? 0));
  let durOverlay = Number(mo.duration);
  if (!Number.isFinite(durOverlay) || durOverlay <= 0) {
    durOverlay = kind === "image" ? 5 : probeDurationSec(abs);
  }
  durOverlay = Math.max(0.1, durOverlay);
  const w = Number(cfg.timeline?.width ?? 1920);
  const h = Number(cfg.timeline?.height ?? 1080);
  const base = sanitizeOverlayFileId(mo.id);

  if (kind === "image") {
    const out = path.join(processedDir, `overlay_${base}.still.mov`);
    const vf = `scale=${w}:${h}:force_original_aspect_ratio=decrease,pad=${w}:${h}:(ow-iw)/2:(oh-ih)/2`;
    const ff = spawnSync(
      "ffmpeg",
      ["-y", "-loop", "1", "-i", abs, "-t", String(durOverlay), "-vf", vf, "-c:v", "dnxhd", "-profile:v", "dnxhr_hq", "-pix_fmt", "yuv422p", "-an", out],
      { encoding: "utf8" }
    );
    if (ff.status !== 0 || !fs.existsSync(out)) {
      processedLog.push(`${mo.id}: studio image overlay transcode failed`);
      return null;
    }
    const assetDur = Math.max(durOverlay, probeDurationSec(out) || durOverlay);
    processedLog.push(`${mo.id}: ${out} (studio image → processed)`);
    return {
      outPath: out,
      clipStartInSource: 0,
      assetDurationSec: assetDur,
      clipDurOnTimeline: durOverlay,
      hasVideo: "1",
      hasAudio: "0",
      audCh: "0",
      audRate: "0",
    };
  }

  if (kind === "video") {
    const out = path.join(processedDir, `overlay_${base}.mov`);
    let withAudio = false;
    let ff = spawnSync(
      "ffmpeg",
      [
        "-y",
        "-ss",
        String(startSrc),
        "-t",
        String(durOverlay),
        "-i",
        abs,
        "-c:v",
        "dnxhd",
        "-profile:v",
        "dnxhr_hq",
        "-pix_fmt",
        "yuv422p",
        "-c:a",
        "pcm_s16le",
        "-ar",
        "48000",
        out,
      ],
      { encoding: "utf8" }
    );
    if (ff.status === 0 && fs.existsSync(out)) {
      withAudio = true;
    } else {
      ff = spawnSync(
        "ffmpeg",
        [
          "-y",
          "-ss",
          String(startSrc),
          "-t",
          String(durOverlay),
          "-i",
          abs,
          "-c:v",
          "dnxhd",
          "-profile:v",
          "dnxhr_hq",
          "-pix_fmt",
          "yuv422p",
          "-an",
          out,
        ],
        { encoding: "utf8" }
      );
    }
    if (ff.status !== 0 || !fs.existsSync(out)) {
      processedLog.push(`${mo.id}: studio video overlay transcode failed`);
      return null;
    }
    const assetDur = Math.max(durOverlay, probeDurationSec(out) || durOverlay);
    processedLog.push(`${mo.id}: ${out} (studio video → processed)`);
    return {
      outPath: out,
      clipStartInSource: 0,
      assetDurationSec: assetDur,
      clipDurOnTimeline: durOverlay,
      hasVideo: "1",
      hasAudio: withAudio ? "1" : "0",
      audCh: withAudio ? "2" : "0",
      audRate: withAudio ? "48000" : "0",
    };
  }

  if (kind === "audio") {
    const out = path.join(processedDir, `overlay_${base}.wav`);
    const ff = spawnSync(
      "ffmpeg",
      [
        "-y",
        "-ss",
        String(startSrc),
        "-t",
        String(durOverlay),
        "-i",
        abs,
        "-vn",
        "-c:a",
        "pcm_s16le",
        "-ar",
        "48000",
        "-ac",
        "2",
        out,
      ],
      { encoding: "utf8" }
    );
    if (ff.status !== 0 || !fs.existsSync(out)) {
      processedLog.push(`${mo.id}: studio audio overlay transcode failed`);
      return null;
    }
    const assetDur = Math.max(durOverlay, probeDurationSec(out) || durOverlay);
    processedLog.push(`${mo.id}: ${out} (studio audio → processed)`);
    return {
      outPath: out,
      clipStartInSource: 0,
      assetDurationSec: assetDur,
      clipDurOnTimeline: durOverlay,
      hasVideo: "0",
      hasAudio: "1",
      audCh: "2",
      audRate: "48000",
    };
  }

  return null;
}

export type ExportBundleOptions = {
  variantId?: string;
  /** Working directory for variant-specific manifests, narration, subtitles, and output. Defaults to projectDir. */
  variantWorkDir?: string;
};

function resolveUnderProject(filePath: string, projectRoot: string): string {
  const abs = path.isAbsolute(filePath) ? path.normalize(filePath) : path.resolve(projectRoot, filePath);
  const root = path.resolve(projectRoot);
  if (!abs.startsWith(root)) {
    throw new Error(`overlay_path_outside_project:${abs}`);
  }
  return abs;
}

function loadTimelineAnnotations(workDir: string): TimelineAnnotationsDoc | null {
  const p = path.resolve(workDir, "timeline-annotations.json");
  if (!fs.existsSync(p)) return null;
  try {
    return readJson<TimelineAnnotationsDoc>(p);
  } catch {
    return null;
  }
}

type IndexDraft = Omit<TimelineIndexRow, "order">;

function finalizeTimelineIndexRows(rows: IndexDraft[]): TimelineIndexRow[] {
  const sorted = [...rows].sort((a, b) => {
    if (a.start_sec !== b.start_sec) return a.start_sec - b.start_sec;
    if (a.lane !== b.lane) return a.lane - b.lane;
    const rank = (c: TimelineIndexRow["category"]) =>
      ({ spine: 0, narration: 1, caption: 2, studio_text: 3, studio_media: 4, marker: 5 }[c] ?? 9);
    return rank(a.category) - rank(b.category);
  });
  return sorted.map((r, i) => ({ ...r, order: i + 1 }));
}

function formatMdCell(s: string): string {
  return String(s || "").replace(/\|/g, "\\|").replace(/\r?\n/g, " ").trim();
}

function buildTimelineIndexMarkdown(doc: TimelineIndexDoc): string {
  const head = [
    "# Timeline index",
    "",
    `Generated: ${doc.generated_at}`,
    doc.variant_id ? `Variant: **${doc.variant_id}**` : "",
    `Spine (main program) length: **${doc.sequence_duration_sec.toFixed(3)} s**`,
    "",
    "Sorted by **start time**, then **lane**.",
    "",
    "| # | Start (s) | End (s) | Δ (s) | Lane | Category | Label | Detail | Source |",
    "|---|---:|---:|---:|---:|---|---|---|---|",
  ].filter((line) => line !== "");
  const body = doc.rows.map((r) => {
    const delta = (r.end_sec - r.start_sec).toFixed(3);
    return `| ${r.order} | ${r.start_sec.toFixed(3)} | ${r.end_sec.toFixed(3)} | ${delta} | ${r.lane} | ${formatMdCell(r.category)} | ${formatMdCell(r.label)} | ${formatMdCell(r.detail || "")} | ${formatMdCell(r.source || "")} |`;
  });
  return [...head, ...body].join("\n") + "\n";
}

export function exportDaVinciBundle(projectDir: string, cfg: any, opts?: ExportBundleOptions): { fcpxml: string; report: string } {
  const workDir = path.resolve(opts?.variantWorkDir || projectDir);
  const variantLabel = opts?.variantId ? ` (${opts.variantId})` : "";
  const media = readJson<{ entries: any[] }>(path.resolve(workDir, "media-manifest.json"));
  const annPathWork = path.resolve(workDir, "edit-annotations.json");
  const annPathRoot = path.resolve(projectDir, "edit-annotations.json");
  let annotations: { annotations: any[] } = { annotations: [] };
  try {
    if (fs.existsSync(annPathWork)) {
      annotations = readJson<{ annotations: any[] }>(annPathWork);
    } else if (fs.existsSync(annPathRoot)) {
      annotations = readJson<{ annotations: any[] }>(annPathRoot);
    }
  } catch {
    annotations = { annotations: [] };
  }
  const annotationBySeg = new Map((annotations.annotations || []).map((a) => [a.segment_id, a]));
  const timelineEntries = media.entries.filter((e) => {
    const p = pickExistingSource(e);
    return Boolean(p && fs.existsSync(p));
  });
  const narrationPath = path.resolve(workDir, "output", "narration.wav");
  const narrationDurationSec = fs.existsSync(narrationPath) ? Math.max(0.1, probeDurationSec(narrationPath)) : 0;
  const rawMainTotal = timelineEntries.reduce((sum, e) => {
    const dur = Number(e.duration_seconds || 1);
    const tin = Number(e.timeline?.in_seconds || 0);
    const tout = Number(e.timeline?.out_seconds || dur);
    return sum + Math.max(0.1, Math.min(dur, tout) - tin);
  }, 0);
  const trimScale =
    narrationDurationSec > 0 && rawMainTotal > 0 ? Math.max(0.05, Math.min(1, narrationDurationSec / rawMainTotal)) : 1;
  const useBrollTopWindow = Boolean(cfg?.timeline?.use_broll_top_window);
  const processedDir = path.resolve(workDir, "output", "processed");
  fs.mkdirSync(processedDir, { recursive: true });
  const indexRowsDraft: IndexDraft[] = [];

  let offset = 0;
  const assets: string[] = [];
  const clips: string[] = [];
  const missing: string[] = [];
  const processed: string[] = [];
  let assetCount = 0;
  for (let i = 0; i < media.entries.length; i++) {
    const e = media.entries[i];
    const sourcePath = pickExistingSource(e);
    if (!sourcePath || !fs.existsSync(sourcePath)) {
      const expected = e?.normalized || e?.downloaded || `segment:${e?.segment_id || i}`;
      missing.push(path.resolve(String(expected)));
      continue;
    }
    assetCount += 1;
    const assetId = `r${assetCount}`;
    const dur = Number(e.duration_seconds || 1);
    let tin = Number(e.timeline?.in_seconds || 0);
    let tout = Number(e.timeline?.out_seconds || dur);
    if (useBrollTopWindow && e?.broll_top_window) {
      const bIn = Number(e.broll_top_window.start_seconds);
      const bOut = Number(e.broll_top_window.end_seconds);
      if (Number.isFinite(bIn) && Number.isFinite(bOut) && bOut > bIn) {
        tin = bIn;
        tout = bOut;
      }
    }
    const clipDurRaw = Math.max(0.1, Math.min(dur, tout) - tin);
    const clipDur = Math.max(0.1, clipDurRaw * trimScale);
    const ann = annotationBySeg.get(e.segment_id);
    const fx = Array.isArray(ann?.effects) ? ann.effects.join("+") : "";
    const lut = ann?.lut_hint ? String(ann.lut_hint) : "";
    const styleTag = ann ? ` [${ann.transition}]${fx ? ` [fx:${fx}]` : ""}${lut ? ` [lut:${lut}]` : ""}` : "";
    const clipName = `${e.concept}${styleTag}`;
    const src = sourcePath;
    let timelineSrc = src;
    let clipStartInSource = tin;
    let timelineAssetDur = dur;
    const crop = e.crop || {};
    const cw = Number(crop.width || 0);
    const ch = Number(crop.height || 0);
    const cx = Number(crop.x || 0);
    const cy = Number(crop.y || 0);
    const hasCrop = cw > 0 && ch > 0;
    const effectFilters = Array.isArray(ann?.effects)
      ? ann.effects.flatMap((fxName: string) => filterForEffect(String(fxName)))
      : [];
    const lutFilters = lut ? filterForLutHint(lut) : [];
    const shouldProcess = hasCrop || effectFilters.length > 0 || lutFilters.length > 0;
    if (shouldProcess && src && fs.existsSync(src)) {
      const processedOut = path.resolve(processedDir, `${path.parse(path.basename(src)).name}.styled.mov`);
      const filters: string[] = [];
      if (hasCrop) {
        filters.push(`crop=${Math.round(cw)}:${Math.round(ch)}:${Math.round(cx)}:${Math.round(cy)}`);
      }
      filters.push(...effectFilters, ...lutFilters);
      const ff = spawnSync(
        "ffmpeg",
        [
          "-y",
          "-ss",
          String(tin),
          "-t",
          String(clipDur),
          "-i",
          src,
          "-vf",
          filters.join(","),
          "-c:v",
          "dnxhd",
          "-profile:v",
          "dnxhr_hq",
          "-pix_fmt",
          "yuv422p",
          "-an",
          processedOut,
        ],
        { encoding: "utf8" }
      );
      if (ff.status === 0 && fs.existsSync(processedOut)) {
        timelineSrc = processedOut;
        clipStartInSource = 0;
        timelineAssetDur = clipDur;
        processed.push(
          `${e.segment_id}: ${processedOut} (crop=${hasCrop ? "yes" : "no"}, fx=${effectFilters.length}, lut=${lutFilters.length})`
        );
      }
    }

    assets.push(
      `<asset id="${assetId}" name="${esc(path.basename(timelineSrc))}" src="${esc(new URL(`file://${timelineSrc}`).toString())}" start="0s" duration="${secToRat(timelineAssetDur)}" hasVideo="1" hasAudio="0" audioSources="0" audioChannels="0" audioRate="0" format="rFormat" />`
    );
    clips.push(
      `<asset-clip name="${esc(clipName)}" ref="${assetId}" offset="${secToRat(offset)}" start="${secToRat(clipStartInSource)}" duration="${secToRat(clipDur)}" />`
    );
    indexRowsDraft.push({
      start_sec: Number(offset.toFixed(4)),
      end_sec: Number((offset + clipDur).toFixed(4)),
      lane: 0,
      category: "spine",
      label: clipName,
      detail: e.segment_id,
      source: timelineSrc,
    });
    const brollMarkers = Array.isArray(e?.broll_markers) ? e.broll_markers : [];
    for (const marker of brollMarkers) {
      const label = String(marker?.label || "B-roll");
      const score = Number(marker?.score || 0);
      indexRowsDraft.push({
        start_sec: Number(offset.toFixed(4)),
        end_sec: Number((offset + clipDur).toFixed(4)),
        lane: 0,
        category: "marker",
        label,
        detail: `broll score=${score.toFixed(3)} · ${e.segment_id || ""}`,
        source: timelineSrc,
      });
    }
    offset += clipDur;
    if (!fs.existsSync(timelineSrc)) {
      missing.push(timelineSrc);
      assets.pop();
      clips.pop();
      assetCount -= 1;
      offset -= clipDur;
      indexRowsDraft.pop();
      continue;
    }
  }

  const spineDurationSec = offset;

  let narrationAsset = "";
  let narrationClip = "";
  if (narrationDurationSec > 0) {
    const ndur = narrationDurationSec;
    narrationAsset = `\n    <asset id="rNarr" name="${esc(path.basename(narrationPath))}" src="${esc(
      new URL(`file://${narrationPath}`).toString()
    )}" start="0s" duration="${secToRat(ndur)}" hasAudio="1" audioSources="1" audioChannels="1" audioRate="48000" />`;
    narrationClip = `\n            <asset-clip name="Narration" ref="rNarr" lane="-1" offset="0s" start="0s" duration="${secToRat(ndur)}" />`;
    indexRowsDraft.push({
      start_sec: 0,
      end_sec: Number(ndur.toFixed(4)),
      lane: -1,
      category: "narration",
      label: "Narration",
      source: narrationPath,
    });
  }

  const cuesPath = path.resolve(workDir, "subtitle-cues.json");
  const capCfg = cfg.caption ?? {};
  const captionsEnabled = capCfg.enabled !== false;
  const dialogueCaptionLane = Number(capCfg.lane ?? -2);
  let captionsXml = "";
  if (captionsEnabled && fs.existsSync(cuesPath)) {
    try {
      const cueFile = readJson<SubtitleCueFile>(cuesPath);
      const lane = dialogueCaptionLane;
      const font = String(capCfg.font ?? "Open Sans");
      const fontSize = Number(capCfg.font_size ?? 52);
      const fontFace = String(capCfg.font_face ?? "Regular");
      const fontColor = hexToFcpxmlRgba(String(capCfg.font_color_hex ?? "#FFFFFF"));
      const placement = String(capCfg.placement ?? "bottom");
      const alignment = String(capCfg.alignment ?? "center");
      const vy = Number(capCfg.vertical_offset_normalized ?? -0.08);
      const cues = Array.isArray(cueFile.cues) ? cueFile.cues : [];
      for (const c of cues) {
        const st = Number(c.start);
        const en = Number(c.end);
        indexRowsDraft.push({
          start_sec: Number(st.toFixed(4)),
          end_sec: Number(en.toFixed(4)),
          lane,
          category: "caption",
          label: `Cue ${c.index}`,
          detail: (c.text || "").slice(0, 200),
        });
      }
      captionsXml =
        "\n            " +
        cues
          .map((c) => {
            const dur = Math.max(0.05, Number(c.end) - Number(c.start));
            return `<caption lane="${lane}" offset="${secToRat(Number(c.start))}" start="0s" duration="${secToRat(
              dur
            )}" name="${esc(`Cap_${c.index}`)}"><text placement="${esc(placement)}" alignment="${esc(
              alignment
            )}" offset="0 ${vy} 0 0" font="${esc(font)}" fontSize="${fontSize}" fontFace="${esc(
              fontFace
            )}" fontColor="${fontColor}">${esc(c.text)}</text></caption>`;
          })
          .join("\n            ");
    } catch {
      captionsXml = "";
    }
  }

  const studioDoc = loadTimelineAnnotations(workDir);
  const studioEnabled =
    studioDoc &&
    (studioDoc.mode === "studio" ||
      (studioDoc.text_overlays?.length || 0) > 0 ||
      (studioDoc.media_overlays?.length || 0) > 0 ||
      (studioDoc.markers?.length || 0) > 0);
  const studioTextLane = dialogueCaptionLane - 1;
  let studioCaptionsXml = "";
  if (studioEnabled && studioDoc) {
    const font = String(capCfg.font ?? "Open Sans");
    const fontSize = Number(capCfg.font_size ?? 52);
    const fontFace = String(capCfg.font_face ?? "Regular");
    const placement = String(capCfg.placement ?? "bottom");
    const alignment = String(capCfg.alignment ?? "center");
    const vy = Number(capCfg.vertical_offset_normalized ?? -0.08);
    for (const o of studioDoc.text_overlays || []) {
      const lane = Number(o.lane ?? studioTextLane);
      const stO = Number(o.start);
      const enO = Number(o.end);
      indexRowsDraft.push({
        start_sec: Number(stO.toFixed(4)),
        end_sec: Number(enO.toFixed(4)),
        lane,
        category: "studio_text",
        label: `Studio text: ${o.id}`,
        detail: (o.text || "").slice(0, 200),
      });
      const dur = Math.max(0.05, Number(o.end) - Number(o.start));
      const fontColor = hexToFcpxmlRgba(String(o.style?.fontColor || capCfg.font_color_hex || "#FFFFFF"));
      const fsz = Number(o.style?.fontSize ?? fontSize);
      const fnt = String(o.style?.font ?? font);
      const ff = String(o.style?.fontFace ?? fontFace);
      const pl = String(o.style?.placement ?? placement);
      const al = String(o.style?.alignment ?? alignment);
      studioCaptionsXml += `\n            <caption lane="${lane}" offset="${secToRat(Number(o.start))}" start="0s" duration="${secToRat(
        dur
      )}" name="${esc(`Studio_${o.id}`)}"><text placement="${esc(pl)}" alignment="${esc(
        al
      )}" offset="0 ${vy} 0 0" font="${esc(fnt)}" fontSize="${fsz}" fontFace="${esc(ff)}" fontColor="${fontColor}">${esc(
        o.text
      )}</text></caption>`;
    }
  }

  let extraAssetsXml = "";
  let extraClipsXml = "";
  let studioAssetCursor = assetCount;
  if (studioEnabled && studioDoc) {
    for (const mo of studioDoc.media_overlays || []) {
      const abs = resolveUnderProject(mo.path, projectDir);
      if (!fs.existsSync(abs)) continue;
      studioAssetCursor += 1;
      const ref = `r${studioAssetCursor}`;
      const kind = mo.kind;
      const startSrcRaw = Math.max(0, Number(mo.source_in ?? 0));
      let durOverlay = Number(mo.duration);
      if (!Number.isFinite(durOverlay) || durOverlay <= 0) {
        durOverlay = kind === "image" ? 5 : probeDurationSec(abs);
      }
      durOverlay = Math.max(0.1, durOverlay);

      const baked = processStudioMediaOverlayToProcessed(mo, abs, processedDir, cfg, processed);
      let timelineAbs = abs;
      let clipStartInSource = startSrcRaw;
      const probedSrc = probeDurationSec(abs);
      let assetDurationSec = Math.max(durOverlay + startSrcRaw, probedSrc > 0 ? probedSrc : durOverlay + startSrcRaw);
      let hasVid: string = kind === "video" || kind === "image" ? "1" : "0";
      let hasAud: string = kind === "audio" || kind === "video" ? "1" : "0";
      let audCh = kind === "audio" ? "2" : kind === "video" ? "2" : "0";
      let audRate = kind === "audio" || kind === "video" ? "48000" : "0";

      if (baked) {
        timelineAbs = baked.outPath;
        clipStartInSource = baked.clipStartInSource;
        assetDurationSec = baked.assetDurationSec;
        durOverlay = baked.clipDurOnTimeline;
        hasVid = baked.hasVideo;
        hasAud = baked.hasAudio;
        audCh = baked.audCh;
        audRate = baked.audRate;
      }

      extraAssetsXml += `\n    <asset id="${ref}" name="${esc(path.basename(timelineAbs))}" src="${esc(
        new URL(`file://${timelineAbs}`).toString()
      )}" start="0s" duration="${secToRat(assetDurationSec)}" hasVideo="${hasVid}" hasAudio="${hasAud}" audioSources="${hasAud}" audioChannels="${audCh}" audioRate="${audRate}" format="rFormat" />`;
      const lane = Number(mo.lane ?? (kind === "audio" ? 2 : 1));
      const label = mo.label ? esc(String(mo.label)) : esc(path.basename(timelineAbs));
      extraClipsXml += `\n            <asset-clip name="${label}" ref="${ref}" lane="${lane}" offset="${secToRat(
        Number(mo.start)
      )}" start="${secToRat(clipStartInSource)}" duration="${secToRat(durOverlay)}" />`;
      const startM = Number(mo.start);
      indexRowsDraft.push({
        start_sec: Number(startM.toFixed(4)),
        end_sec: Number((startM + durOverlay).toFixed(4)),
        lane,
        category: "studio_media",
        label: mo.label ? String(mo.label) : `${kind}: ${mo.id}`,
        detail: `${kind} · ${mo.id}`,
        source: timelineAbs,
      });
    }
  }

  if (studioEnabled && studioDoc?.markers?.length) {
    for (const m of studioDoc.markers) {
      const t = Number(m.t_seconds);
      indexRowsDraft.push({
        start_sec: Number(t.toFixed(4)),
        end_sec: Number(t.toFixed(4)),
        lane: 0,
        category: "marker",
        label: m.label || m.id,
        detail: m.id,
      });
    }
  }

  const markersXml = (studioEnabled && studioDoc?.markers?.length
    ? studioDoc.markers
        .map(
          (m) =>
            `\n            <!-- marker: ${esc(m.label || m.id)} @ ${Number(m.t_seconds).toFixed(3)}s -->`
        )
        .join("")
    : "") as string;

  const xmlWithNarr = `<?xml version='1.0' encoding='utf-8'?>
<fcpxml version="1.13">
  <resources>
    <format id="rFormat" name="FFVideoFormat1080p30" frameDuration="1001/30000s" width="${cfg.timeline.width}" height="${cfg.timeline.height}" colorSpace="1-1-1 (Rec. 709)" />
    ${assets.join("\n    ")}${extraAssetsXml}${narrationAsset}
  </resources>
  <library>
    <event name="AIDirector">
      <project name="${esc(cfg.timeline.name)}${esc(variantLabel)}">
        <sequence format="rFormat" tcStart="0s" tcFormat="NDF">
          <spine>
            ${clips.join("\n            ")}${narrationClip}${captionsXml}${studioCaptionsXml}${extraClipsXml}${markersXml}
          </spine>
        </sequence>
      </project>
    </event>
  </library>
</fcpxml>
`;

  const outDir = path.resolve(workDir, "output");
  const fcpxml = path.resolve(outDir, "timeline_davinci_resolve.fcpxml");
  const report = path.resolve(outDir, "import-report.md");
  const timelineIndexJson = path.resolve(outDir, "timeline-index.json");
  const timelineIndexMd = path.resolve(outDir, "timeline-index.md");
  const indexRows = finalizeTimelineIndexRows(indexRowsDraft);
  const timelineEnds = indexRows.map((r) => r.end_sec);
  const sequenceDurationSec = Math.max(0, spineDurationSec, ...(timelineEnds.length ? timelineEnds : [0]));
  const timelineIndexDoc: TimelineIndexDoc = {
    generated_at: new Date().toISOString(),
    variant_id: opts?.variantId,
    sequence_duration_sec: Number(sequenceDurationSec.toFixed(4)),
    rows: indexRows,
  };
  writeText(fcpxml, xmlWithNarr);
  writeJson(timelineIndexJson, timelineIndexDoc);
  writeText(timelineIndexMd, buildTimelineIndexMarkdown(timelineIndexDoc));
  writeJson(path.resolve(outDir, "export-manifest.json"), {
    generated_at: new Date().toISOString(),
    variant_id: opts?.variantId,
    fcpxml,
    timeline_index_json: timelineIndexJson,
    timeline_index_md: timelineIndexMd,
    subtitles: path.resolve(workDir, "subtitles.srt"),
    subtitle_cues: path.resolve(workDir, "subtitle-cues.json"),
    script: path.resolve(workDir, "script.md"),
    annotations: path.resolve(workDir, "edit-annotations.json"),
    media_manifest: path.resolve(workDir, "media-manifest.json"),
    timeline_annotations: path.resolve(workDir, "timeline-annotations.json"),
  });
  const reportText = [
    "# DaVinci Import Report",
    "",
    opts?.variantId ? `## Variant\n- **${opts.variantId}** (outputs under this variant's \`output/\` folder)\n` : "",
    "## Timeline index (ordered table)",
    `- JSON: \`${timelineIndexJson}\``,
    `- Markdown table: \`${timelineIndexMd}\``,
    `- ${indexRows.length} row(s); spine length **${spineDurationSec.toFixed(3)} s**`,
    "",
    "## Lane map",
    `- Spine: main video clips`,
    `- Lane -1: narration`,
    `- Lane ${dialogueCaptionLane}: dialogue captions (from script)`,
    `- Lane ${studioTextLane}: studio text overlays (when enabled)`,
    `- Lane 1 / 2: studio media overlays (video/image / audio defaults)`,
    "",
    "## Checklist",
    "- Import media first (source clip audio is muted in timeline)",
    "- Import timeline_davinci_resolve.fcpxml",
    "- Captions may be embedded in the FCPXML (`caption` elements); adjust in Inspector if needed",
    "- Or import `subtitles.srt` as an additional subtitle track",
    "- Narration.wav is the primary timeline audio track",
    "",
    "## Validation",
    missing.length ? "Missing media references:" : "No missing media references detected.",
    ...missing.map((m) => `- ${m}`),
    "",
    "## Video processing",
    processed.length ? "Processed clips generated:" : "No processed clips generated.",
    ...processed.map((m) => `- ${m}`),
    ...(path.resolve(workDir) !== path.resolve(projectDir)
      ? [
          "",
          "## Project root output (mirror)",
          `The build CLI also copies this FCPXML, this report, \`export-manifest.json\`, \`timeline-index.json\`, \`timeline-index.md\`, and \`crop-validation.json\` to:`,
          `- \`${path.resolve(projectDir, "output")}\``,
          "Narration (\`narration.wav\`) and \`processed/\` clips remain under the variant \`output/\` folder; FCPXML \`file://\` paths point to those absolute locations.",
        ]
      : []),
  ].join("\n");
  writeText(report, reportText);
  return { fcpxml, report };
}
