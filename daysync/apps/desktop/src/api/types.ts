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

export type ProjectSettings = {
  subtitle_workspace: {
    video_timeline_id: string;
    audio_timeline_id: string;
    video_srt_path: string;
    audio_srt_path: string;
    query: string;
    cluster_samples: OffsetClusterSample[];
  };
  export_workspace: {
    output_path: string;
    status_filter: "all" | "accepted_manual" | "accepted_auto" | "needs_review" | "rejected";
    source_filter: "all" | "manual_anchor" | "auto_text";
    min_confidence_filter: string;
  };
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
  candidate_margin: number;
  reverse_margin: number;
  reverse_match_consistent: boolean;
  reverse_top_subtitle_id?: string | null;
  reverse_top_raw_text?: string | null;
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
    duplicate_count: number;
  };
  target_track_type: "video_ref" | "external_audio";
  limit: number;
  context_radius: number;
  candidates: AutoCandidate[];
};

export type OffsetClusterSample = {
  video_subtitle_id: string;
  video_text: string;
  video_source_filename?: string | null;
  audio_subtitle_id: string;
  audio_text: string;
  audio_source_filename?: string | null;
};

export type OffsetClusterPairAnalysis = {
  video_subtitle_id: string;
  video_text: string;
  video_source_filename?: string | null;
  video_source_start_ms: number;
  audio_subtitle_id: string;
  audio_text: string;
  audio_source_filename?: string | null;
  audio_source_start_ms: number;
  offset_ms: number;
  text_similarity: number;
  context_similarity: number;
  final_score: number;
  candidate_margin: number;
  reverse_margin: number;
  reverse_match_consistent: boolean;
  negative_evidence_count: number;
  mapping_warning?: string | null;
  reverse_top_subtitle_id?: string | null;
  reverse_top_raw_text?: string | null;
  cluster_deviation_ms: number;
  is_inlier: boolean;
};

export type OffsetClusterAnalysisResponse = {
  pair_analyses: OffsetClusterPairAnalysis[];
  cluster_summary: {
    candidate_count: number;
    median_offset_ms: number;
    final_offset_ms?: number | null;
    inlier_count: number;
    inlier_ratio: number;
    passes: boolean;
    tolerance_ms: number;
    min_inlier_ratio: number;
    min_anchor_count: number;
    reverse_consistent_count: number;
    negative_evidence_pair_count: number;
    reasons: string[];
  };
  auto_accept_decision: AutoAcceptDecision;
};

export type AutoAcceptDecision = {
  eligible: boolean;
  reasons: string[];
  average_candidate_margin: number;
  min_candidate_margin: number;
};

export type AutoConformExcludedSeed = {
  subtitle_id: string;
  raw_text: string;
  source_filename?: string | null;
  reason: string;
};

export type AutoConformAnchorPair = {
  video_subtitle_id: string;
  video_text: string;
  video_source_media_file_id?: string | null;
  video_source_filename?: string | null;
  video_source_start_ms: number;
  video_flat_start_ms: number;
  audio_subtitle_id: string;
  audio_text: string;
  audio_source_media_file_id?: string | null;
  audio_source_filename?: string | null;
  audio_source_start_ms: number;
  audio_flat_start_ms: number;
  offset_ms: number;
  source_offset_ms: number;
  text_similarity: number;
  context_similarity: number;
  final_score: number;
  candidate_margin: number;
  reverse_margin: number;
  reverse_match_consistent: boolean;
  negative_evidence_count: number;
  mapping_warning?: string | null;
  cluster_deviation_ms: number;
  is_inlier: boolean;
};

export type AutoConformPreview = {
  representative_pair: AutoConformAnchorPair | null;
  anchor_pairs: AutoConformAnchorPair[];
  excluded_seeds: AutoConformExcludedSeed[];
  cluster_summary: {
    candidate_count: number;
    median_offset_ms?: number | null;
    final_offset_ms?: number | null;
    inlier_count: number;
    inlier_ratio: number;
    passes: boolean;
    tolerance_ms: number;
    min_inlier_ratio: number;
    min_anchor_count: number;
    reverse_consistent_count: number;
    negative_evidence_pair_count: number;
    reasons: string[];
  };
  auto_accept_decision: AutoAcceptDecision;
  preview_segments: Array<{
    id: string;
    video_media_file_id: string;
    audio_media_file_id: string;
    video_file?: string;
    audio_file?: string;
    video_in_ms: number;
    video_out_ms: number;
    audio_in_ms: number;
    audio_out_ms: number;
    offset_ms: number;
    timeline_start_ms: number;
    timeline_end_ms: number;
  }>;
  ready_to_apply: boolean;
  selected_seed_count: number;
  eligible_seed_count: number;
};

export type AutoConformApplyResponse = {
  sync_result: SyncResult;
  generated_count: number;
  track_offset_ms: number;
  sync_result_summary: {
    status: string;
    source: string;
    accepted_count: number;
    representative_video_file?: string;
    representative_audio_file?: string;
  };
};

export type ReviewEvent = {
  id: string;
  sync_result_id: string;
  event_type: "accepted" | "rejected" | "adjusted" | "commented";
  old_offset_ms?: number | null;
  new_offset_ms?: number | null;
  note?: string | null;
  created_at: string;
};

export type ReviewQueueItem = {
  id: string;
  project_id: string;
  video_media_file_id: string;
  audio_media_file_id: string;
  video_in_ms: number;
  video_out_ms: number;
  audio_in_ms: number;
  audio_out_ms: number;
  offset_ms: number;
  confidence_score: number;
  status: string;
  source: string;
  video_anchor_subtitle_id?: string | null;
  audio_anchor_subtitle_id?: string | null;
  created_at: string;
  updated_at: string;
  video_file?: string;
  audio_file?: string;
  video_anchor_text?: string;
  audio_anchor_text?: string;
  confidence_breakdown: Record<string, unknown>;
  review_events: ReviewEvent[];
};

export type SyncResult = {
  id: string;
  offset_ms: number;
  status: string;
  source: string;
  confidence_score: number;
  project_id?: string;
  video_in_ms?: number;
  video_out_ms?: number;
  audio_in_ms?: number;
  audio_out_ms?: number;
  video_file?: string;
  audio_file?: string;
  video_anchor_text?: string;
  audio_anchor_text?: string;
  created_at?: string;
  updated_at?: string;
  confidence_breakdown?: Record<string, unknown>;
  review_events?: ReviewEvent[];
};

export type ExportJob = {
  id: string;
  project_id: string;
  export_type: "csv" | "fcp7_xml" | "fcpxml" | "otio" | "json";
  output_path: string;
  status: "pending" | "running" | "succeeded" | "failed";
  row_count?: number | null;
  error_message?: string | null;
  created_at: string;
  completed_at?: string | null;
};

export type StudioTrackMeta = {
  id: string;
  kind: string;
  name: string;
  media_type?: "video" | "audio";
  track_type?: "video_ref" | "external_audio";
  source_type?: string;
  language?: string | null;
  original_path?: string | null;
  gap_ms?: number;
  sort_mode?: "filename" | "created_at" | "manual";
  item_count?: number;
  cue_count?: number;
  total_duration_ms: number;
  created_at: string;
};

export type StudioMediaClip = {
  id: string;
  timeline_id: string;
  media_file_id: string;
  item_index: number;
  media_type: "video" | "audio";
  filename: string;
  original_path: string;
  flat_start_ms: number;
  flat_end_ms: number;
  source_start_ms: number;
  source_end_ms: number;
  gap_after_ms: number;
  has_video: boolean;
  has_audio: boolean;
};

export type StudioSubtitleCue = {
  subtitle_id: string;
  track_id: string;
  track_type: "video_ref" | "external_audio";
  subtitle_index: number;
  flat_start_ms: number;
  flat_end_ms: number;
  source_media_file_id?: string | null;
  source_start_ms?: number | null;
  source_end_ms?: number | null;
  raw_text: string;
  normalized_text?: string;
  mapping_status: "ok" | "warning" | "failed";
  mapping_warning?: string | null;
  source_filename?: string | null;
};

export type StudioSourceSubtitleGroup = {
  media_file_id?: string | null;
  source_filename?: string | null;
  cue_count: number;
  warning_count: number;
  failed_count: number;
  eligible_seed_count: number;
  cues: StudioSubtitleCue[];
};

export type StudioAutoConformReadiness = {
  status: "ready" | "missing";
  reasons: string[];
  video_group_count: number;
  audio_group_count: number;
  video_warning_count: number;
  audio_warning_count: number;
  video_failed_count: number;
  audio_failed_count: number;
  video_eligible_seed_count: number;
};

export type StudioSyncSegment = {
  sync_result_id: string;
  video_media_file_id: string;
  audio_media_file_id: string;
  video_filename: string;
  audio_filename: string;
  video_original_path: string;
  audio_original_path: string;
  video_flat_start_ms: number;
  video_flat_end_ms: number;
  audio_flat_start_ms: number;
  audio_flat_end_ms: number;
  video_in_ms: number;
  video_out_ms: number;
  audio_in_ms: number;
  audio_out_ms: number;
  offset_ms: number;
  status: string;
  source: string;
  created_at: string;
  updated_at: string;
};

export type StudioTimelineSnapshot = {
  project_id: string;
  video_timeline: StudioTrackMeta | null;
  audio_timeline: StudioTrackMeta | null;
  video_subtitle_track: StudioTrackMeta | null;
  audio_subtitle_track: StudioTrackMeta | null;
  video_clips: StudioMediaClip[];
  audio_clips: StudioMediaClip[];
  video_subtitles: StudioSubtitleCue[];
  audio_subtitles: StudioSubtitleCue[];
  video_source_subtitle_groups: StudioSourceSubtitleGroup[];
  audio_source_subtitle_groups: StudioSourceSubtitleGroup[];
  auto_conform_readiness: StudioAutoConformReadiness;
  sync_segments: StudioSyncSegment[];
  accepted_sync_summary: {
    status: "missing" | "ready";
    accepted_count: number;
    median_offset_ms?: number | null;
    latest_source?: string | null;
    latest_updated_at?: string | null;
  };
};

export type ProjectSnapshot = {
  project: Project;
  stats: ProjectStats;
  media_files: MediaFile[];
  flat_timelines: FlatTimeline[];
  sync_results: SyncResult[];
  project_settings: ProjectSettings;
};
