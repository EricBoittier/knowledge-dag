"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.buildFcpxmlFromMediaManifest = buildFcpxmlFromMediaManifest;
const node_fs_1 = __importDefault(require("node:fs"));
const node_path_1 = __importDefault(require("node:path"));
const fs_1 = require("../utils/fs");
function secToRational(sec, scale = 24000) {
    const v = Math.max(0, Math.round(sec * scale));
    return `${v}/${scale}s`;
}
function xmlEscape(s) {
    return s
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}
function toUri(p) {
    return new URL(`file://${node_path_1.default.resolve(p)}`).toString();
}
function buildFcpxmlFromMediaManifest(config, repoRoot) {
    const manifestPath = node_path_1.default.resolve(repoRoot, "data/media-manifest.json");
    const media = (0, fs_1.readJsonFile)(manifestPath);
    const entries = media.entries.filter((e) => e.timeline?.enabled !== false);
    if (entries.length === 0) {
        throw new Error("No timeline-enabled entries in media manifest");
    }
    const assetsXml = [];
    const clipsXml = [];
    let offset = 0;
    entries.forEach((e, idx) => {
        const assetId = `r${idx + 1}`;
        const duration = e.duration_seconds;
        const tin = Math.max(0, e.timeline?.in_seconds ?? config.timeline.segment_trim_lead_sec);
        const toutRaw = e.timeline?.out_seconds ?? Math.max(tin + 0.1, duration - config.timeline.segment_trim_tail_sec);
        const tout = Math.min(duration, toutRaw);
        const clipDuration = Math.max(0.1, tout - tin);
        const clipName = e.timeline?.label || e.concept || `Shot ${idx + 1}`;
        assetsXml.push(`<asset id="${assetId}" name="${xmlEscape(node_path_1.default.basename(e.normalized))}" src="${xmlEscape(toUri(e.normalized))}" start="0s" duration="${secToRational(duration)}" hasVideo="1" hasAudio="1" audioSources="1" audioChannels="2" audioRate="${config.timeline.audio_rate}" format="rFormat" />`);
        clipsXml.push(`<asset-clip name="${xmlEscape(clipName)}" ref="${assetId}" offset="${secToRational(offset)}" start="${secToRational(tin)}" duration="${secToRational(clipDuration)}" />`);
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
    node_fs_1.default.mkdirSync(node_path_1.default.dirname(config.timeline.output_fcpxml), { recursive: true });
    node_fs_1.default.writeFileSync(config.timeline.output_fcpxml, xml, "utf8");
    return config.timeline.output_fcpxml;
}
