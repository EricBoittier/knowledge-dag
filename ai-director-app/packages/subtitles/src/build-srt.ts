import path from "node:path";
import fs from "node:fs";
import { spawnSync } from "node:child_process";
import { readJson, writeJson, writeText } from "../../core/src/fs";
import { cleanForNarration, isSkippableScriptLine, splitIntoSubtitleCues } from "./clean-script-text";

function fmt(sec: number): string {
  const ms = Math.max(0, Math.round(sec * 1000));
  const h = Math.floor(ms / 3600000);
  const m = Math.floor((ms % 3600000) / 60000);
  const s = Math.floor((ms % 60000) / 1000);
  const rem = ms % 1000;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")},${String(rem).padStart(3, "0")}`;
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

function cueWeight(text: string): number {
  const trimmed = text.trim();
  if (!trimmed) return 1;
  const wordCount = trimmed.split(/\s+/).filter(Boolean).length;
  const punctuationCount = (trimmed.match(/[.,!?;:]/g) || []).length;
  return Math.max(1, wordCount + punctuationCount * 0.35);
}

const SPEAKER_PALETTE = [
  { text: "#FFFFFF", outline: "#101418", shadow: "#000000A0" },
  { text: "#FFE082", outline: "#2A1F00", shadow: "#000000A0" },
  { text: "#90CAF9", outline: "#0D1B2A", shadow: "#000000A0" },
  { text: "#CE93D8", outline: "#2A0E35", shadow: "#000000A0" },
  { text: "#A5D6A7", outline: "#102A12", shadow: "#000000A0" },
];

type ScriptLine = {
  segment_id: string;
  text?: string;
  subtitle_text: string;
  speaker_id?: string;
  speaker?: string;
};

type SubtitleCue = {
  index: number;
  start: number;
  end: number;
  text: string;
  segment_id: string;
  speaker_id: string;
};

function findPipelineConfigPath(startDir: string): string {
  let d = path.resolve(startDir);
  for (let i = 0; i < 10; i++) {
    const candidate = path.join(d, "config", "pipeline.config.json");
    if (fs.existsSync(candidate)) return candidate;
    const parent = path.dirname(d);
    if (parent === d) break;
    d = parent;
  }
  return path.resolve(startDir, "../../config/pipeline.config.json");
}

function loadPipelineConfig(projectDir: string): { maxCueChars: number; minCueChars: number } {
  const cfgPath = findPipelineConfigPath(projectDir);
  try {
    const cfg = readJson<{ subtitle?: { max_chars_per_line?: number } }>(cfgPath);
    const perLine = Number(cfg.subtitle?.max_chars_per_line ?? 42);
    const maxCueChars = Math.min(120, Math.max(72, perLine * 2));
    return { maxCueChars, minCueChars: 12 };
  } catch {
    return { maxCueChars: 90, minCueChars: 12 };
  }
}

export function buildEditableSrt(projectDir: string): {
  srt: string;
  styleMap: string;
  resolveGuide: string;
  subtitleCues: string;
} {
  const script = readJson<{ lines: ScriptLine[] }>(path.resolve(projectDir, "script-lines.json"));
  const { maxCueChars, minCueChars } = loadPipelineConfig(projectDir);
  const speakers = new Set<string>();
  const cueSpeakerRows: Array<{ cue_index: number; segment_id: string; speaker_id: string }> = [];

  const narrationPath = path.resolve(projectDir, "output", "narration.wav");
  const narrationDuration = fs.existsSync(narrationPath) ? probeDurationSec(narrationPath) : 0;

  const flatCueTexts: { segment_id: string; speaker: string; text: string }[] = [];
  for (const line of script.lines) {
    const rawSub = String(line.subtitle_text || line.text || "");
    if (isSkippableScriptLine(rawSub)) continue;
    const speaker = String(line.speaker_id || line.speaker || "SPEAKER_00").trim() || "SPEAKER_00";
    speakers.add(speaker);
    const cleaned = cleanForNarration(rawSub);
    if (!cleaned) continue;
    const pieces = splitIntoSubtitleCues(cleaned, { maxChars: maxCueChars, minChars: minCueChars });
    for (const text of pieces) {
      flatCueTexts.push({ segment_id: line.segment_id, speaker, text });
    }
  }

  if (flatCueTexts.length === 0) {
    const srtPath = path.resolve(projectDir, "subtitles.srt");
    writeText(srtPath, "1\n00:00:00,000 --> 00:00:02,000\n(No subtitle lines after filtering script.)\n");
    const styleMapPath = path.resolve(projectDir, "subtitle-style.json");
    writeJson(styleMapPath, { generated_at: new Date().toISOString(), error: "no_cues_after_filter" });
    const cuesPath = path.resolve(projectDir, "subtitle-cues.json");
    writeJson(cuesPath, { generated_at: new Date().toISOString(), cues: [] });
    const guidePath = path.resolve(projectDir, "resolve-subtitle-styling.md");
    writeText(guidePath, "# No subtitle cues\n\nAll `script-lines` entries were filtered as scaffolding (markdown headings, `## seg_…`, etc.).\n");
    return { srt: srtPath, styleMap: styleMapPath, resolveGuide: guidePath, subtitleCues: cuesPath };
  }

  const weights = flatCueTexts.map((c) => cueWeight(c.text));
  const totalWeight = weights.reduce((a, b) => a + b, 0) || 1;
  const totalSeconds = narrationDuration > 0 ? narrationDuration : flatCueTexts.length * 4;

  const cues: SubtitleCue[] = [];
  let t = 0;
  for (let i = 0; i < flatCueTexts.length; i++) {
    const dur = Math.max(0.5, (weights[i] / totalWeight) * totalSeconds);
    const start = t;
    const end = t + dur;
    cues.push({
      index: i + 1,
      start,
      end,
      text: flatCueTexts[i].text,
      segment_id: flatCueTexts[i].segment_id,
      speaker_id: flatCueTexts[i].speaker,
    });
    cueSpeakerRows.push({
      cue_index: i + 1,
      segment_id: flatCueTexts[i].segment_id,
      speaker_id: flatCueTexts[i].speaker,
    });
    t = end;
  }

  const rows: string[] = [];
  for (const c of cues) {
    rows.push(String(c.index), `${fmt(c.start)} --> ${fmt(c.end)}`, c.text, "");
  }

  const srtPath = path.resolve(projectDir, "subtitles.srt");
  writeText(srtPath, rows.join("\n"));

  const sortedSpeakers = Array.from(speakers).sort();
  const styleMapPath = path.resolve(projectDir, "subtitle-style.json");
  writeJson(styleMapPath, {
    generated_at: new Date().toISOString(),
    timing_source: narrationDuration > 0 ? "narration.wav weighted by cue text length" : "estimated per-cue timing",
    narration_seconds: narrationDuration > 0 ? narrationDuration : undefined,
    default_style: {
      font: "Open Sans",
      size: 0.05,
      line_position: "bottom-center",
      tracking: 0.0,
      line_spacing: 1.0,
      box_enabled: true,
      box_color: "#00000066",
      box_padding: 0.02,
    },
    speakers: sortedSpeakers.map((speaker, i) => ({
      id: speaker,
      style: SPEAKER_PALETTE[i % SPEAKER_PALETTE.length],
    })),
    cue_speaker_map: cueSpeakerRows,
  });

  const cuesPath = path.resolve(projectDir, "subtitle-cues.json");
  writeJson(cuesPath, {
    generated_at: new Date().toISOString(),
    narration_seconds: narrationDuration > 0 ? narrationDuration : totalSeconds,
    cues: cues.map((c) => ({
      index: c.index,
      start: Number(c.start.toFixed(4)),
      end: Number(c.end.toFixed(4)),
      text: c.text,
      segment_id: c.segment_id,
      speaker_id: c.speaker_id,
    })),
  });

  const guidePath = path.resolve(projectDir, "resolve-subtitle-styling.md");
  const guide = [
    "# Resolve Subtitle Styling Guide",
    "",
    "1. Import `timeline_davinci_resolve.fcpxml` — captions may already be embedded (lane -2) with font/color from config.",
    "2. Alternatively import `subtitles.srt` onto a subtitle track.",
    "3. Open `subtitle-style.json` for per-speaker colors (see `cue_speaker_map`).",
    "4. `subtitle-cues.json` mirrors the same timing as the SRT for tooling.",
    "",
    "## Speaker Style Map",
    ...sortedSpeakers.map((speaker, i) => {
      const style = SPEAKER_PALETTE[i % SPEAKER_PALETTE.length];
      return `- ${speaker}: text=${style.text}, outline=${style.outline}, shadow=${style.shadow}`;
    }),
  ].join("\n");
  writeText(guidePath, guide);

  return { srt: srtPath, styleMap: styleMapPath, resolveGuide: guidePath, subtitleCues: cuesPath };
}
