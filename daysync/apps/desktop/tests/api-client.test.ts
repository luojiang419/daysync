import {
  ApiError,
  applyAutoConform,
  checkHealth,
  createProject,
  ensureLocalApiReady,
  previewAutoConform,
  waitForApiReady,
} from "../src/api/client";

vi.mock("../src/api/tauri", () => ({
  RuntimeInvocationError: class RuntimeInvocationError extends Error {
    code: string;
    details: Record<string, unknown>;

    constructor(code: string, message: string, details: Record<string, unknown> = {}) {
      super(message);
      this.code = code;
      this.details = details;
    }
  },
  ensureRuntimeReady: vi.fn(),
  invokeRuntime: vi.fn(),
}));

describe("api client", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("返回本地运行时健康检查数据", async () => {
    const tauriApi = await import("../src/api/tauri");
    vi.mocked(tauriApi.ensureRuntimeReady).mockResolvedValueOnce({
      status: "ok",
      registered_projects: 2,
      ffmpeg: {
        ready: true,
        source: "project-local",
        version: "8.1.1",
        root_path: "D:\\ffmpeg",
        ffmpeg_path: "D:\\ffmpeg\\ffmpeg.exe",
        ffprobe_path: "D:\\ffmpeg\\ffprobe.exe",
        error: null,
      },
    });

    const result = await checkHealth();

    expect(result.status).toBe("ok");
    expect(result.registered_projects).toBe(2);
    expect(result.ffmpeg.source).toBe("project-local");
  });

  it("把运行时错误包装成 ApiError", async () => {
    const tauriApi = await import("../src/api/tauri");
    const runtimeError = new tauriApi.RuntimeInvocationError(
      "RUNTIME_UNAVAILABLE",
      "未能连接本地运行时，请稍后重试。",
      {
        cause: "spawn failed",
      },
    );
    vi.mocked(tauriApi.ensureRuntimeReady).mockRejectedValueOnce(
      runtimeError,
    );

    await expect(checkHealth()).rejects.toMatchObject({
      code: "RUNTIME_UNAVAILABLE",
      message: "未能连接本地运行时，请稍后重试。",
    } satisfies Partial<ApiError>);
  });

  it("waitForApiReady 会复用本地运行时健康检查", async () => {
    const tauriApi = await import("../src/api/tauri");
    vi.mocked(tauriApi.ensureRuntimeReady).mockResolvedValueOnce({
      status: "ok",
      registered_projects: 1,
      ffmpeg: {
        ready: true,
        source: "project-local",
        version: "8.1.1",
        root_path: "D:\\ffmpeg",
        ffmpeg_path: "D:\\ffmpeg\\ffmpeg.exe",
        ffprobe_path: "D:\\ffmpeg\\ffprobe.exe",
        error: null,
      },
    });

    const result = await waitForApiReady();

    expect(result.registered_projects).toBe(1);
  });

  it("ensureLocalApiReady 会直接调用本地运行时就绪检查", async () => {
    const tauriApi = await import("../src/api/tauri");
    vi.mocked(tauriApi.ensureRuntimeReady).mockResolvedValueOnce({
      status: "ok",
      registered_projects: 3,
      ffmpeg: {
        ready: true,
        source: "project-local",
        version: "8.1.1",
        root_path: "D:\\ffmpeg",
        ffmpeg_path: "D:\\ffmpeg\\ffmpeg.exe",
        ffprobe_path: "D:\\ffmpeg\\ffprobe.exe",
        error: null,
      },
    });

    const result = await ensureLocalApiReady();

    expect(result.registered_projects).toBe(3);
    expect(tauriApi.ensureRuntimeReady).toHaveBeenCalledTimes(1);
  });

  it("项目创建请求会直接转发到本地运行时方法", async () => {
    const tauriApi = await import("../src/api/tauri");
    vi.mocked(tauriApi.invokeRuntime).mockResolvedValueOnce({
      project: {
        id: "project-1",
        name: "测试项目",
        root_path: "D:\\projects\\demo",
      },
      stats: {
        media_count: 0,
        subtitle_count: 0,
        sync_result_count: 0,
      },
      media_files: [],
      flat_timelines: [],
      sync_results: [],
      project_settings: {
        subtitle_workspace: {
          video_timeline_id: "",
          audio_timeline_id: "",
          video_srt_path: "",
          audio_srt_path: "",
          query: "",
          cluster_samples: [],
        },
        export_workspace: {
          output_path: "",
          status_filter: "all",
          source_filter: "all",
          min_confidence_filter: "0",
        },
      },
    });

    await createProject({
      name: "测试项目",
      root_path: "D:\\projects\\demo",
      shooting_date: "2026-05-17",
    });

    expect(tauriApi.invokeRuntime).toHaveBeenCalledWith("project.create", {
      name: "测试项目",
      root_path: "D:\\projects\\demo",
      shooting_date: "2026-05-17",
    });
  });

  it("自动整日合板预览会调用新的 runtime 方法", async () => {
    const tauriApi = await import("../src/api/tauri");
    vi.mocked(tauriApi.invokeRuntime).mockResolvedValueOnce({
      representative_pair: null,
      anchor_pairs: [],
      excluded_seeds: [],
      cluster_summary: {
        candidate_count: 0,
        median_offset_ms: null,
        final_offset_ms: null,
        inlier_count: 0,
        inlier_ratio: 0,
        passes: false,
        tolerance_ms: 500,
        min_inlier_ratio: 0.6,
        min_anchor_count: 3,
        reverse_consistent_count: 0,
        negative_evidence_pair_count: 0,
        reasons: ["no_anchor_pairs"],
      },
      auto_accept_decision: {
        eligible: false,
        reasons: ["no_anchor_pairs"],
        average_candidate_margin: 0,
        min_candidate_margin: 0.1,
      },
      preview_segments: [],
      ready_to_apply: false,
      selected_seed_count: 0,
      eligible_seed_count: 0,
    });

    await previewAutoConform("project-1");

    expect(tauriApi.invokeRuntime).toHaveBeenCalledWith("sync.auto_conform_preview", {
      project_id: "project-1",
      context_radius: 2,
      min_anchor_count: 3,
      tolerance_ms: 500,
      min_inlier_ratio: 0.6,
    });
  });

  it("自动整日合板应用会调用新的 runtime 方法", async () => {
    const tauriApi = await import("../src/api/tauri");
    vi.mocked(tauriApi.invokeRuntime).mockResolvedValueOnce({
      sync_result: {
        id: "sync-1",
        offset_ms: 574180,
        status: "accepted_auto",
        source: "auto_text",
        confidence_score: 1,
      },
      generated_count: 2,
      track_offset_ms: 574180,
      sync_result_summary: {
        status: "accepted_auto",
        source: "auto_text",
        accepted_count: 2,
        representative_video_file: "A001_C001.mov",
        representative_audio_file: "ZOOM0001.wav",
      },
    });

    await applyAutoConform("project-1", {
      offset_ms: 574180,
      representative_video_subtitle_id: "video-sub-1",
      representative_audio_subtitle_id: "audio-sub-1",
    });

    expect(tauriApi.invokeRuntime).toHaveBeenCalledWith("sync.apply_auto_conform", {
      project_id: "project-1",
      offset_ms: 574180,
      representative_video_subtitle_id: "video-sub-1",
      representative_audio_subtitle_id: "audio-sub-1",
    });
  });
});
