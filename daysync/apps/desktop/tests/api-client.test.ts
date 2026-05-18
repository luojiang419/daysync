import { ApiError, checkHealth, createProject, ensureLocalApiReady, waitForApiReady } from "../src/api/client";

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
});
