import fs from "node:fs";
import path from "node:path";
import { PipelineConfig } from "../config";
import { readJsonFile } from "../utils/fs";

interface MediaManifestEntry {
  segment_id: string;
  concept: string;
  normalized: string;
  duration_seconds: number;
  timeline?: {
    in_seconds?: number;
    out_seconds?: number;
    label?: string;
    enabled?: boolean;
  };
}

interface MediaManifest {
  generated_at: string;
  entries: MediaManifestEntry[];
}

interface OverlaySubtitleSegment {
  text: string;
  start: number;
  end: number;
}

interface OverlayManifest {
  subtitle_segments?: OverlaySubtitleSegment[];
}

function secToRational(sec: number, scale = 24000): string {
  const v = Math.max(0, Math.round(sec * scale));
  return `${v}/${scale}s`;
}

function xmlEscape(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function toUri(p: string): string {
  return new URL(`file://${path.resolve(p)}`).toString();
}

export function buildFcpxmlFromMediaManifest(config: PipelineConfig, repoRoot: string): string {
  const manifestPath = path.resolve(repoRoot, "data/media-manifest.json");
  const media = readJsonFile<MediaManifest>(manifestPath);
  const entries = media.entries.filter((e) => e.timeline?.enabled !== false);
  if (entries.length === 0) {
    throw new Error("No timeline-enabled entries in media manifest");
  }
  let subtitleSegments: OverlaySubtitleSegment[] = [];
  if (config.timeline.overlay_manifest_path && fs.existsSync(config.timeline.overlay_manifest_path)) {
    const overlayPayload = readJsonFile<OverlayManifest>(config.timeline.overlay_manifest_path);
    subtitleSegments = overlayPayload.subtitle_segments ?? [];
  }

  const assetsXml: string[] = [];
  const clipsXml: string[] = [];
  let offset = 0;

  entries.forEach((e, idx) => {
    const assetId = `r${idx + 1}`;
    const duration = e.duration_seconds;
    const tin = Math.max(0, e.timeline?.in_seconds ?? config.timeline.segment_trim_lead_sec);
    const toutRaw = e.timeline?.out_seconds ?? Math.max(tin + 0.1, duration - config.timeline.segment_trim_tail_sec);
    const tout = Math.min(duration, toutRaw);
    const clipDuration = Math.max(0.1, tout - tin);
    const clipName = e.timeline?.label || e.concept || `Shot ${idx + 1}`;

    assetsXml.push(
      `<asset id="${assetId}" name="${xmlEscape(path.basename(e.normalized))}" src="${xmlEscape(
        toUri(e.normalized)
      )}" start="0s" duration="${secToRational(duration)}" hasVideo="1" hasAudio="1" audioSources="1" audioChannels="2" audioRate="${config.timeline.audio_rate}" format="rFormat" />`
    );
    const markerXml: string[] = [];
    const clipStart = offset;
    const clipEnd = offset + clipDuration;
    subtitleSegments.forEach((seg) => {
      if (seg.start < clipStart || seg.start >= clipEnd) {
        return;
      }
      const markerStart = Math.max(0, seg.start - clipStart + tin);
      const markerDur = Math.max(0.05, seg.end - seg.start);
      markerXml.push(
        `<marker start="${secToRational(markerStart)}" duration="${secToRational(markerDur)}" value="${xmlEscape(seg.text)}" />`
      );
    });
    clipsXml.push(
      `<asset-clip name="${xmlEscape(clipName)}" ref="${assetId}" offset="${secToRational(offset)}" start="${secToRational(
        tin
      )}" duration="${secToRational(clipDuration)}">${markerXml.join("")}</asset-clip>`
    );
    offset += clipDuration;
  });

  const xml = `<?xml version='1.0' encoding='utf-8'?>
<fcpxml version="1.13">
  <resources>
    <format id="rFormat" name="FFVideoFormat1080p30" frameDuration="1001/30000s" width="${config.timeline.width}" height="${config.timeline.height}" colorSpace="1-1-1 (Rec. 709)" />
    ${assetsXml.join("\n    ")}
  </resources>
  <library>
    <event name="DagVideoEditor">
      <project name="${xmlEscape(config.timeline.name)}">
        <sequence format="rFormat" tcStart="0s" tcFormat="NDF">
          <spine>
            ${clipsXml.join("\n            ")}
          </spine>
        </sequence>
      </project>
    </event>
  </library>
</fcpxml>
`;

  fs.mkdirSync(path.dirname(config.timeline.output_fcpxml), { recursive: true });
  fs.writeFileSync(config.timeline.output_fcpxml, xml, "utf8");
  return config.timeline.output_fcpxml;
}
