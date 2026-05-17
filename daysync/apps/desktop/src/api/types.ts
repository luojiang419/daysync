export type Project = {
  id: string;
  name: string;
  root_path: string;
  shooting_date?: string | null;
  schema_version?: string;
  created_at?: string;
  updated_at?: string;
};

export type ProjectStats = {
  media_count: number;
  subtitle_count: number;
  sync_result_count: number;
};

export type MediaFile = {
  id: string;
  media_type: "video" | "audio";
  filename: string;
  duration_ms: number;
  has_video?: boolean;
  has_audio?: boolean;
  original_path?: string;
};

export type FlatTimelineItem = {
  id?: string;
  media_file_id: string;
  item_index?: number;
  flat_start_ms: number;
  flat_end_ms: number;
  source_start_ms: number;
  source_end_ms: number;
  gap_after_ms?: number;
  filename?: string;
};

export type FlatTimeline = {
  id?: string;
  flat_timeline_id?: string;
  media_type: "video" | "audio";
  name?: string;
  gap_ms?: number;
  sort_mode?: "filename" | "created_at" | "manual";
  items: FlatTimelineItem[];
};

export type SearchResult = {
  subtitle_id: string;
  track_type: "video_ref" | "external_audio";
  raw_text: string;
  normalized_text: string;
  source_media_file_id?: string | null;
  source_start_ms?: number | null;
  source_end_ms?: number | null;
  flat_start_ms: number;
  flat_end_ms: number;
  relevance_score: number;
  source_filename?: string | null;
};

export type SearchResults = {
  query: string;
  video_results: SearchResult[];
  audio_results: SearchResult[];
};

export type AutoCandidate = {
  subtitle_id: string;
  track_type: "video_ref" | "external_audio";
  track_id: string;
  raw_text: string;
  normalized_text: string;
  source_media_file_id?: string | null;
  source_filename?: string | null;
  source_start_ms?: number | null;
  source_end_ms?: number | null;
  flat_start_ms: number;
  flat_end_ms: number;
  mapping_status: "ok" | "warning" | "failed";
  mapping_warning?: string | null;
  text_similarity: number;
  context_similarity: number;
  final_score: number;
  negative_evidence_count: number;
  duplicate_count: number;
  context_before_text: string;
  context_after_text: string;
  context_window_text: string;
};

export type AutoCandidateResponse = {
  anchor: {
    subtitle_id: string;
    track_type: "video_ref" | "external_audio";
    track_id: string;
    raw_text: string;
    normalized_text: string;
    source_media_file_id?: string | null;
    source_filename?: string | null;
    source_start_ms?: number | null;
    source_end_ms?: number | null;
    flat_start_ms: number;
    flat_end_ms: number;
    mapping_status: "ok" | "warning" | "failed";
    mapping_warning?: string | null;
    context_before_text: string;
    context_after_text: string;
    context_window_text: string;
  };
  target_track_type: "video_ref" | "external_audio";
  limit: number;
  context_radius: number;
  candidates: AutoCandidate[];
};

export type SyncResult = {
  id: string;
  offset_ms: number;
  status: string;
  source: string;
  confidence_score: number;
  video_file?: string;
  audio_file?: string;
  video_anchor_text?: string;
  audio_anchor_text?: string;
  created_at?: string;
};

export type ProjectSnapshot = {
  project: Project;
  stats: ProjectStats;
  media_files: MediaFile[];
  flat_timelines: FlatTimeline[];
  sync_results: SyncResult[];
};
