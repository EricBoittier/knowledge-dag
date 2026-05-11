import path from "node:path";
import { readJsonFile, resolveFromRepoRoot } from "./utils/fs";
import { MediaSource } from "./types";

export interface PipelineConfig {
  dag: {
    mode: string;
    snapshot_path: string;
    max_segments: number;
  };
  planner: {
    target_total_runtime_sec: number;
    default_segment_duration_sec: number;
  };
  youtube: {
    max_duration_sec: number;
    min_duration_sec: number;
    language: string;
    region: string;
    results_per_segment: number;
    selected_per_segment: number;
  };
  discovery: {
    sources: MediaSource[];
    prefer_sources: MediaSource[];
    allow_unknown_duration: boolean;
  };
  media: {
    download_dir: string;
    normalized_dir: string;
    normalize_container: string;
    video_codec: string;
    video_profile: string;
    pixel_format: string;
    audio_codec: string;
    audio_rate: number;
    audio_channels: number;
  };
  broll_analyzer?: {
    enabled?: boolean;
    model_name?: string;
    device?: string;
    sample_interval_sec?: number;
    window_duration_sec?: number;
    max_windows?: number;
    min_window_score?: number;
    max_new_tokens?: number;
  };
  transcription: {
    enabled: boolean;
    model: string;
    language: string;
    compute_type: string;
    output_transcript_json: string;
  };
  subtitles: {
    output_srt: string;
    output_text: string;
    max_chars_per_line: number;
    max_lines_per_cue: number;
  };
  timeline: {
    name: string;
    width: number;
    height: number;
    fps: number;
    audio_rate: number;
    output_fcpxml: string;
    segment_trim_lead_sec: number;
    segment_trim_tail_sec: number;
    overlay_manifest_path?: string;
    use_broll_top_window?: boolean;
  };
  render: {
    mode: string;
    output_video: string;
  };
  upload: {
    enabled: boolean;
    title_prefix: string;
    description_template: string;
  };
}

export function loadConfig(configPath: string): { config: PipelineConfig; repoRoot: string; configPath: string } {
  const absConfigPath = path.resolve(configPath);
  const repoRoot = path.resolve(path.dirname(absConfigPath), "..");
  const config = readJsonFile<PipelineConfig>(absConfigPath);

  config.dag.snapshot_path = resolveFromRepoRoot(repoRoot, config.dag.snapshot_path);
  config.media.download_dir = resolveFromRepoRoot(repoRoot, config.media.download_dir);
  config.media.normalized_dir = resolveFromRepoRoot(repoRoot, config.media.normalized_dir);
  config.transcription.output_transcript_json = resolveFromRepoRoot(repoRoot, config.transcription.output_transcript_json);
  config.subtitles.output_srt = resolveFromRepoRoot(repoRoot, config.subtitles.output_srt);
  config.subtitles.output_text = resolveFromRepoRoot(repoRoot, config.subtitles.output_text);
  config.timeline.output_fcpxml = resolveFromRepoRoot(repoRoot, config.timeline.output_fcpxml);
  if (config.timeline.overlay_manifest_path) {
    config.timeline.overlay_manifest_path = resolveFromRepoRoot(repoRoot, config.timeline.overlay_manifest_path);
  }
  config.render.output_video = resolveFromRepoRoot(repoRoot, config.render.output_video);
  return { config, repoRoot, configPath: absConfigPath };
}
