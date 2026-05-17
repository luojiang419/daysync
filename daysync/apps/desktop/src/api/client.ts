import type {
  AutoCandidateResponse,
  FlatTimeline,
  MediaFile,
  ProjectSnapshot,
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
};

type AutoCandidateApiResponse = AutoCandidateResponse;

type SyncListResponse = {
  sync_results: SyncResult[];
};

type ExportCsvResponse = {
  output_path: string;
  row_count: number;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });

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
