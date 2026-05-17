import type {
  AutoAcceptDecision,
  AutoCandidateResponse,
  ExportJob,
  FlatTimeline,
  MediaFile,
  OffsetClusterAnalysisResponse,
  ProjectSnapshot,
  ReviewQueueItem,
  SearchResults,
  SyncResult,
} from "./types";

const API_BASE_URL =
  import.meta.env.VITE_DAYSYNC_API_URL ?? "http://127.0.0.1:17831";

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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
      ...init,
    });
  } catch (error) {
    throw new ApiError(
      "API_UNREACHABLE",
      "未连接到本地 API，请稍后重试；如果是桌面版，请等待本地运行时完成启动。",
      { cause: error instanceof Error ? error.message : String(error) },
    );
  }

  const payloadText = await response.text();
  const payload = payloadText ? (JSON.parse(payloadText) as Record<string, unknown>) : {};
  if (!response.ok) {
    const error = payload.error as
      | { code?: string; message?: string; details?: Record<string, unknown> }
      | undefined;
    throw new ApiError(
      error?.code ?? "UNKNOWN_ERROR",
      error?.message ?? `Request failed: ${response.status}`,
      error?.details ?? {},
    );
  }
  return payload as T;
}

export function getApiBaseUrl(): string {
  return API_BASE_URL;
}

export async function checkHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/api/health");
}

export async function waitForApiReady(
  options: { attempts?: number; delayMs?: number } = {},
): Promise<HealthResponse> {
  const attempts = options.attempts ?? 8;
  const delayMs = options.delayMs ?? 500;
  let lastError: unknown = null;

  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      return await checkHealth();
    } catch (error) {
      lastError = error;
      if (attempt < attempts - 1) {
        await new Promise((resolve) => setTimeout(resolve, delayMs));
      }
    }
  }

  if (lastError instanceof ApiError) {
    throw lastError;
  }
  throw new ApiError("API_UNREACHABLE", "未连接到本地 API。");
}

export async function createProject(payload: {
  name: string;
  root_path: string;
  shooting_date?: string;
}): Promise<ProjectSnapshot> {
  return request<ProjectSnapshot>("/api/projects", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function openProject(rootPath: string): Promise<ProjectSnapshot> {
  const query = new URLSearchParams({ root_path: rootPath });
  return request<ProjectSnapshot>(`/api/projects/open?${query.toString()}`);
}

export async function saveProjectSettings(
  projectId: string,
  payload: {
    subtitle_workspace?: Record<string, unknown>;
    export_workspace?: Record<string, unknown>;
  },
): Promise<{ project_settings: Record<string, unknown> }> {
  return request<{ project_settings: Record<string, unknown> }>(`/api/projects/${projectId}/settings`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function importMedia(
  projectId: string,
  payload: { paths: string[]; session_id: string | null },
): Promise<ImportMediaResponse> {
  return request<ImportMediaResponse>(`/api/projects/${projectId}/media/import`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
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
  return request<FlatTimelineResponse>(`/api/projects/${projectId}/flat-timelines`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
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
  return request<ImportSubtitlesResponse>(`/api/projects/${projectId}/subtitles/import`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function searchSubtitles(
  projectId: string,
  query: string,
  limit = 20,
): Promise<SearchResults> {
  const search = new URLSearchParams({ q: query, limit: String(limit) });
  return request<SearchResults>(`/api/projects/${projectId}/subtitles/search?${search.toString()}`);
}

export async function createManualSync(
  projectId: string,
  payload: { video_subtitle_id: string; audio_subtitle_id: string },
): Promise<SyncResponse> {
  return request<SyncResponse>(`/api/projects/${projectId}/sync/manual-anchor`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function recommendAutoCandidates(
  projectId: string,
  payload: { anchor_subtitle_id: string; limit?: number; context_radius?: number },
): Promise<AutoCandidateApiResponse> {
  return request<AutoCandidateApiResponse>(`/api/projects/${projectId}/sync/auto-candidates`, {
    method: "POST",
    body: JSON.stringify({
      anchor_subtitle_id: payload.anchor_subtitle_id,
      limit: payload.limit ?? 5,
      context_radius: payload.context_radius ?? 1,
    }),
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
  return request<OffsetClusterApiResponse>(`/api/projects/${projectId}/sync/offset-cluster`, {
    method: "POST",
    body: JSON.stringify({
      pairs: payload.pairs,
      tolerance_ms: payload.tolerance_ms ?? 500,
      min_inlier_ratio: payload.min_inlier_ratio ?? 0.6,
      min_anchor_count: payload.min_anchor_count ?? 3,
      context_radius: payload.context_radius ?? 1,
    }),
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
  return request<ClusterCandidateResponse>(`/api/projects/${projectId}/sync/cluster-candidate`, {
    method: "POST",
    body: JSON.stringify({
      pairs: payload.pairs,
      tolerance_ms: payload.tolerance_ms ?? 500,
      min_inlier_ratio: payload.min_inlier_ratio ?? 0.6,
      min_anchor_count: payload.min_anchor_count ?? 3,
      context_radius: payload.context_radius ?? 1,
      note: payload.note ?? null,
    }),
  });
}

export async function listReviewQueue(projectId: string): Promise<ReviewQueueResponse> {
  return request<ReviewQueueResponse>(`/api/projects/${projectId}/sync/review-queue`);
}

export async function reviewSyncResult(
  projectId: string,
  syncResultId: string,
  payload: { action: "accepted" | "rejected" | "adjusted" | "commented"; new_offset_ms?: number; note?: string },
): Promise<ReviewSyncResultResponse> {
  return request<ReviewSyncResultResponse>(`/api/projects/${projectId}/sync/results/${syncResultId}/review`, {
    method: "POST",
    body: JSON.stringify({
      action: payload.action,
      new_offset_ms: payload.new_offset_ms ?? null,
      note: payload.note ?? null,
    }),
  });
}

export async function listSyncResults(projectId: string): Promise<SyncListResponse> {
  return request<SyncListResponse>(`/api/projects/${projectId}/sync/results`);
}

export async function exportCsv(
  projectId: string,
  outputPath: string,
): Promise<ExportCsvResponse> {
  return request<ExportCsvResponse>(`/api/projects/${projectId}/exports/csv`, {
    method: "POST",
    body: JSON.stringify({ output_path: outputPath }),
  });
}

export async function exportFcp7Xml(
  projectId: string,
  outputPath: string,
): Promise<ExportFcp7XmlResponse> {
  return request<ExportFcp7XmlResponse>(`/api/projects/${projectId}/exports/fcp7-xml`, {
    method: "POST",
    body: JSON.stringify({ output_path: outputPath }),
  });
}

export async function exportJson(
  projectId: string,
  outputPath: string,
): Promise<ExportJsonResponse> {
  return request<ExportJsonResponse>(`/api/projects/${projectId}/exports/json`, {
    method: "POST",
    body: JSON.stringify({ output_path: outputPath }),
  });
}

export async function exportOtio(
  projectId: string,
  outputPath: string,
): Promise<ExportJsonResponse> {
  return request<ExportJsonResponse>(`/api/projects/${projectId}/exports/otio`, {
    method: "POST",
    body: JSON.stringify({ output_path: outputPath }),
  });
}

export async function exportFcpxml(
  projectId: string,
  outputPath: string,
): Promise<ExportFcpxmlResponse> {
  return request<ExportFcpxmlResponse>(`/api/projects/${projectId}/exports/fcpxml`, {
    method: "POST",
    body: JSON.stringify({ output_path: outputPath }),
  });
}

export async function listExportJobs(projectId: string): Promise<ExportJobListResponse> {
  return request<ExportJobListResponse>(`/api/projects/${projectId}/exports/jobs`);
}
