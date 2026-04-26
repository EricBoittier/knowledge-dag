export type MediaSource = "youtube" | "wikimedia" | "internet_archive";

export interface ExportVariantDescriptor {
  id: string;
  label: string;
  target_duration_sec?: number;
  notes?: string;
}

export interface VariantsIndexDoc {
  schema_version: number;
  generated_at: string;
  active_variant_id: string;
  variants: ExportVariantDescriptor[];
}

export interface TimelineMarker {
  id: string;
  t_seconds: number;
  label?: string;
  color?: string;
}

export interface TextOverlayStyle {
  placement?: string;
  alignment?: string;
  font?: string;
  fontFace?: string;
  fontSize?: number;
  fontColor?: string;
}

export interface TextOverlay {
  id: string;
  start: number;
  end: number;
  text: string;
  lane?: number;
  style?: TextOverlayStyle;
}

export type MediaOverlayKind = "video" | "audio" | "image";

export interface MediaOverlay {
  id: string;
  kind: MediaOverlayKind;
  path: string;
  start: number;
  duration?: number;
  source_in?: number;
  source_out?: number;
  lane?: number;
  volume?: number;
  label?: string;
}

export interface TimelineAnnotationsDoc {
  schema_version: number;
  generated_at: string;
  mode: "simple" | "studio";
  markers: TimelineMarker[];
  text_overlays: TextOverlay[];
  media_overlays: MediaOverlay[];
}

/** One row in the ordered timeline index (export + UI table). */
export interface TimelineIndexRow {
  order: number;
  start_sec: number;
  end_sec: number;
  lane: number;
  category: "spine" | "narration" | "caption" | "studio_text" | "studio_media" | "marker";
  label: string;
  detail?: string;
  source?: string;
}

export interface TimelineIndexDoc {
  generated_at: string;
  variant_id?: string;
  sequence_duration_sec: number;
  rows: TimelineIndexRow[];
}

export interface DagNode {
  id: string;
  title: string;
  tags?: string[];
  importance?: number;
  duration_intent_sec?: number;
}

export interface DagEdge {
  from: string;
  to: string;
}

export interface DagProject {
  nodes: DagNode[];
  edges: DagEdge[];
}

export interface SegmentPlan {
  segment_id: string;
  concept: string;
  keywords: string[];
  target_duration_sec: number;
  priority: number;
  query: string;
}

export interface ScriptDraftLine {
  segment_id: string;
  text: string;
  subtitle_text: string;
}

export interface EditAnnotation {
  segment_id: string;
  transition: string;
  effects: string[];
  lut_hint: string;
  audio_note: string;
}

export interface MediaCandidate {
  segment_id: string;
  source: MediaSource;
  source_id: string;
  title: string;
  url: string;
  creator: string;
  duration_sec: number;
  thumbnail_url?: string;
  filesize_bytes?: number;
  license?: string;
  attribution?: string;
  score: number;
  /** True when discovery found a still image (e.g. Commons bitmap). */
  is_image?: boolean;
  mime_type?: string;
}
