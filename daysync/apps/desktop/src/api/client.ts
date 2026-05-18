import type {
  AutoAcceptDecision,
  AutoCandidateResponse,
  AutoConformApplyResponse,
  AutoConformPreview,
  ExportJob,
  FlatTimeline,
  MediaFile,
  OffsetClusterAnalysisResponse,
  ProjectSnapshot,
  ReviewQueueItem,
  SearchResults,
  StudioTimelineSnapshot,
  SyncResult,
} from "./types";
import { ensureRuntimeReady, RuntimeInvocationError, invokeRuntime } from "./tauri";

export class ApiError extends Error {
  code: string;
  details: Record<string, unknown>;

  constructor(code: string, message: string, details: Record<string, unknown> = {}) {
    super(message);
    this.code = code;
    this.details = details;
  }
}

type HealthResponse = {
  status: string;
  registered_projects: number;
  ffmpeg: {
    ready: boolean;
    source: string | null;
    version: string | null;
    root_path: string;
    ffmpeg_path: string | null;
    ffprobe_path: string | null;
    error: string | null;
  };
};

type ImportMediaResponse = {
  imported: MediaFile[];
  failed: Array<{ path: string; code: string; message: string }>;
  generated_timelines?: Array<{
    media_type: "video" | "audio";
    flat_timeline_id: string;
    items: FlatTimeline["items"];
  }>;
};

type FlatTimelineResponse = {
  flat_timeline_id: string;
  items: FlatTimeline["items"];
};

type ImportSubtitlesResponse = {
  track_id: string;
  imported_count: number;
  warning_count: number;
  failed_count: number;
};

type SyncResponse = {
  sync_result: SyncResult;
  generated_count: number;
  track_offset_ms: number;
};

type AutoCandidateApiResponse = AutoCandidateResponse;
type AutoConformPreviewResponse = AutoConformPreview;
type AutoConformApplyApiResponse = AutoConformApplyResponse;
type OffsetClusterApiResponse = OffsetClusterAnalysisResponse;
type ReviewQueueResponse = { items: ReviewQueueItem[] };
type ClusterCandidateResponse = {
  sync_result: SyncResult & {
    project_id: string;
    confidence_score: number;
    status: string;
    source: string;
  };
  cluster_summary: OffsetClusterAnalysisResponse["cluster_summary"];
  auto_accept_decision: AutoAcceptDecision;
};
type ReviewSyncResultResponse = {
  sync_result: ReviewQueueItem;
  review_event: {
    id: string;
    project_id: string;
    sync_result_id: string;
    event_type: string;
    old_offset_ms?: number | null;
    new_offset_ms?: number | null;
    note?: string | null;
    created_at: string;
  };
};

type SyncListResponse = {
  sync_results: SyncResult[];
};

type ExportCsvResponse = {
  output_path: string;
  row_count: number;
};

type ExportFcp7XmlResponse = {
  output_path: string;
  sequence_count: number;
};

type ExportJsonResponse = {
  output_path: string;
  item_count: number;
};

type ExportFcpxmlResponse = {
  output_path: string;
  project_count: number;
};

type ExportJobListResponse = {
  items: ExportJob[];
};

type RequestOptions = Record<string, never>;

async function request<T>(method: string, payload: Record<string, unknown> = {}): Promise<T> {
  try {
    return await invokeRuntime<T>(method, payload);
  } catch (error) {
    throw toApiError(error);
  }
}

function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) {
    return error;
  }
  if (error instanceof RuntimeInvocationError) {
    return new ApiError(error.code, error.message, error.details);
  }
  return new ApiError(
    "RUNTIME_UNAVAILABLE",
    "未能连接本地运行时，请稍后重试。",
    { cause: error instanceof Error ? error.message : String(error) },
  );
}

export async function checkHealth(_options: RequestOptions = {}): Promise<HealthResponse> {
  try {
    return await ensureRuntimeReady<HealthResponse>();
  } catch (error) {
    throw toApiError(error);
  }
}

export async function waitForApiReady(): Promise<HealthResponse> {
  return checkHealth();
}

export async function ensureLocalApiReady(): Promise<HealthResponse> {
  return checkHealth();
}

export async function createProject(payload: {
  name: string;
  root_path: string;
  shooting_date?: string;
}): Promise<ProjectSnapshot> {
  return request<ProjectSnapshot>("project.create", payload);
}

export async function openProject(rootPath: string): Promise<ProjectSnapshot> {
  return request<ProjectSnapshot>("project.open", { root_path: rootPath });
}

export async function saveProjectSettings(
  projectId: string,
  payload: {
    subtitle_workspace?: Record<string, unknown>;
    export_workspace?: Record<string, unknown>;
  },
): Promise<{ project_settings: Record<string, unknown> }> {
  return request<{ project_settings: Record<string, unknown> }>("project.save_settings", {
    project_id: projectId,
    ...payload,
  });
}

export async function importMedia(
  projectId: string,
  payload: { paths: string[]; session_id: string | null },
): Promise<ImportMediaResponse> {
  return request<ImportMediaResponse>("media.import", { project_id: projectId, ...payload });
}

export async function createFlatTimeline(
  projectId: string,
  payload: {
    media_type: "video" | "audio";
    media_file_ids: string[];
    sort_mode: "filename" | "created_at" | "manual";
    gap_ms: number;
  },
): Promise<FlatTimelineResponse> {
  return request<FlatTimelineResponse>("timeline.create", { project_id: projectId, ...payload });
}

export async function importSubtitles(
  projectId: string,
  payload: {
    flat_timeline_id: string;
    track_type: "video_ref" | "external_audio";
    source_type: "srt_import";
    path: string;
    language?: string;
  },
): Promise<ImportSubtitlesResponse> {
  return request<ImportSubtitlesResponse>("subtitle.import", { project_id: projectId, ...payload });
}

export async function searchSubtitles(
  projectId: string,
  query: string,
  limit = 20,
): Promise<SearchResults> {
  return request<SearchResults>("subtitle.search", { project_id: projectId, query, limit });
}

export async function createManualSync(
  projectId: string,
  payload: { video_subtitle_id: string; audio_subtitle_id: string },
): Promise<SyncResponse> {
  return request<SyncResponse>("sync.manual_anchor", { project_id: projectId, ...payload });
}

export async function recommendAutoCandidates(
  projectId: string,
  payload: { anchor_subtitle_id: string; limit?: number; context_radius?: number },
): Promise<AutoCandidateApiResponse> {
  return request<AutoCandidateApiResponse>("sync.auto_candidates", {
    project_id: projectId,
    anchor_subtitle_id: payload.anchor_subtitle_id,
    limit: payload.limit ?? 5,
    context_radius: payload.context_radius ?? 1,
  });
}

export async function previewAutoConform(
  projectId: string,
  payload: {
    context_radius?: number;
    min_anchor_count?: number;
    tolerance_ms?: number;
    min_inlier_ratio?: number;
  } = {},
): Promise<AutoConformPreviewResponse> {
  return request<AutoConformPreviewResponse>("sync.auto_conform_preview", {
    project_id: projectId,
    context_radius: payload.context_radius ?? 2,
    min_anchor_count: payload.min_anchor_count ?? 3,
    tolerance_ms: payload.tolerance_ms ?? 500,
    min_inlier_ratio: payload.min_inlier_ratio ?? 0.6,
  });
}

export async function applyAutoConform(
  projectId: string,
  payload: {
    offset_ms: number;
    representative_video_subtitle_id: string;
    representative_audio_subtitle_id: string;
  },
): Promise<AutoConformApplyApiResponse> {
  return request<AutoConformApplyApiResponse>("sync.apply_auto_conform", {
    project_id: projectId,
    offset_ms: payload.offset_ms,
    representative_video_subtitle_id: payload.representative_video_subtitle_id,
    representative_audio_subtitle_id: payload.representative_audio_subtitle_id,
  });
}

export async function analyzeOffsetCluster(
  projectId: string,
  payload: {
    pairs: Array<{ video_subtitle_id: string; audio_subtitle_id: string }>;
    tolerance_ms?: number;
    min_inlier_ratio?: number;
    min_anchor_count?: number;
    context_radius?: number;
  },
): Promise<OffsetClusterApiResponse> {
  return request<OffsetClusterApiResponse>("sync.offset_cluster", {
    project_id: projectId,
    pairs: payload.pairs,
    tolerance_ms: payload.tolerance_ms ?? 500,
    min_inlier_ratio: payload.min_inlier_ratio ?? 0.6,
    min_anchor_count: payload.min_anchor_count ?? 3,
    context_radius: payload.context_radius ?? 1,
  });
}

export async function createClusterCandidate(
  projectId: string,
  payload: {
    pairs: Array<{ video_subtitle_id: string; audio_subtitle_id: string }>;
    tolerance_ms?: number;
    min_inlier_ratio?: number;
    min_anchor_count?: number;
    context_radius?: number;
    note?: string;
  },
): Promise<ClusterCandidateResponse> {
  return request<ClusterCandidateResponse>("sync.cluster_candidate", {
    project_id: projectId,
    pairs: payload.pairs,
    tolerance_ms: payload.tolerance_ms ?? 500,
    min_inlier_ratio: payload.min_inlier_ratio ?? 0.6,
    min_anchor_count: payload.min_anchor_count ?? 3,
    context_radius: payload.context_radius ?? 1,
    note: payload.note ?? null,
  });
}

export async function listReviewQueue(projectId: string): Promise<ReviewQueueResponse> {
  return request<ReviewQueueResponse>("sync.review_queue", { project_id: projectId });
}

export async function reviewSyncResult(
  projectId: string,
  syncResultId: string,
  payload: { action: "accepted" | "rejected" | "adjusted" | "commented"; new_offset_ms?: number; note?: string },
): Promise<ReviewSyncResultResponse> {
  return request<ReviewSyncResultResponse>("sync.review_result", {
    project_id: projectId,
    sync_result_id: syncResultId,
    action: payload.action,
    new_offset_ms: payload.new_offset_ms ?? null,
    note: payload.note ?? null,
  });
}

export async function listSyncResults(projectId: string): Promise<SyncListResponse> {
  return request<SyncListResponse>("sync.list_results", { project_id: projectId });
}

export async function exportCsv(
  projectId: string,
  outputPath: string,
): Promise<ExportCsvResponse> {
  return request<ExportCsvResponse>("export.csv", { project_id: projectId, output_path: outputPath });
}

export async function exportFcp7Xml(
  projectId: string,
  outputPath: string,
): Promise<ExportFcp7XmlResponse> {
  return request<ExportFcp7XmlResponse>("export.fcp7_xml", { project_id: projectId, output_path: outputPath });
}

export async function exportJson(
  projectId: string,
  outputPath: string,
): Promise<ExportJsonResponse> {
  return request<ExportJsonResponse>("export.json", { project_id: projectId, output_path: outputPath });
}

export async function exportOtio(
  projectId: string,
  outputPath: string,
): Promise<ExportJsonResponse> {
  return request<ExportJsonResponse>("export.otio", { project_id: projectId, output_path: outputPath });
}

export async function exportFcpxml(
  projectId: string,
  outputPath: string,
): Promise<ExportFcpxmlResponse> {
  return request<ExportFcpxmlResponse>("export.fcpxml", { project_id: projectId, output_path: outputPath });
}

export async function listExportJobs(projectId: string): Promise<ExportJobListResponse> {
  return request<ExportJobListResponse>("export.list_jobs", { project_id: projectId });
}

export async function getStudioTimeline(projectId: string): Promise<StudioTimelineSnapshot> {
  return request<StudioTimelineSnapshot>("studio.timeline", { project_id: projectId });
}
