export interface DagNode {
  id: string;
  title: string;
  tags?: string[];
  importance?: number;
}

export interface DagEdge {
  from: string;
  to: string;
}

export interface DagSnapshot {
  nodes: DagNode[];
  edges: DagEdge[];
}

export interface ShotSegment {
  segment_id: string;
  concept: string;
  keywords: string[];
  target_duration_sec: number;
  priority: number;
  query: string;
}

export interface ShotPlan {
  generated_at: string;
  target_total_runtime_sec: number;
  segments: ShotSegment[];
}

export type MediaSource = "youtube" | "wikimedia" | "internet_archive";

export interface MediaCandidate {
  segment_id: string;
  concept: string;
  query: string;
  source: MediaSource;
  source_id: string;
  title: string;
  url: string;
  creator: string;
  duration_sec: number;
  license?: string;
  attribution?: string;
  score: number;
}

export interface SegmentSelection {
  segment_id: string;
  concept: string;
  query: string;
  selected: MediaCandidate[];
}

export interface TranscriptWord {
  start: number;
  end: number;
  word: string;
}

export interface TranscriptSegment {
  id: number;
  start: number;
  end: number;
  speaker: string;
  text: string;
  source_segment_id?: string;
  source_path?: string;
  clip_duration_seconds?: number;
  timeline_in_seconds?: number;
  timeline_out_seconds?: number;
  words: TranscriptWord[];
}

export interface TranscriptDocument {
  generated_at: string;
  pipeline_stage: "transcribe";
  engine: {
    name: string;
    model: string;
    language: string;
  };
  language: string;
  segments: TranscriptSegment[];
  text: string;
}
