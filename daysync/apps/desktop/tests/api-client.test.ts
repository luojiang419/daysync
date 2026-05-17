import { ApiError, checkHealth, ensureLocalApiReady, waitForApiReady } from "../src/api/client";

vi.mock("../src/api/tauri", () => ({
  ensureDevApi: vi.fn().mockResolvedValue(true),
  isTauriRuntime: vi.fn().mockReturnValue(true),
}));

describe("api client", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("返回健康检查数据", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        text: async () =>
          JSON.stringify({
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
          }),
      }),
    );

    const result = await checkHealth();
    expect(result.status).toBe("ok");
    expect(result.registered_projects).toBe(2);
    expect(result.ffmpeg.source).toBe("project-local");
  });

  it("把后端错误解包成 ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        text: async () =>
          JSON.stringify({
            error: {
              code: "PROJECT_PATH_INVALID",
              message: "路径不可写",
              details: { root_path: "D:\\test" },
            },
          }),
      }),
    );

    await expect(checkHealth()).rejects.toMatchObject({
      code: "PROJECT_PATH_INVALID",
      message: "路径不可写",
    } satisfies Partial<ApiError>);
  });

  it("把网络失败包装成明确的 ApiError", async () => {
    const tauriApi = await import("../src/api/tauri");
    vi.mocked(tauriApi.ensureDevApi).mockRejectedValueOnce(new Error("spawn failed"));
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));

    await expect(checkHealth()).rejects.toMatchObject({
      code: "API_UNREACHABLE",
      message: "未连接到本地 API，请稍后重试；如果是桌面版，请等待本地运行时完成启动。",
    } satisfies Partial<ApiError>);
  });

  it("waitForApiReady 会重试直到健康检查成功", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockRejectedValueOnce(new TypeError("fetch failed"))
        .mockResolvedValueOnce({
          ok: true,
          text: async () =>
            JSON.stringify({
              status: "ok",
              registered_projects: 0,
              ffmpeg: {
                ready: true,
                source: "project-local",
                version: "8.1.1",
                root_path: "D:\\ffmpeg",
                ffmpeg_path: "D:\\ffmpeg\\ffmpeg.exe",
                ffprobe_path: "D:\\ffmpeg\\ffprobe.exe",
                error: null,
              },
            }),
        }),
    );

    const result = await waitForApiReady({ attempts: 2, delayMs: 0 });

    expect(result.status).toBe("ok");
  });

  it("桌面版请求失败时会自动拉起本地 API 后重试", async () => {
    const tauriApi = await import("../src/api/tauri");
    vi.mocked(tauriApi.ensureDevApi).mockResolvedValueOnce(true);
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockRejectedValueOnce(new TypeError("fetch failed"))
        .mockResolvedValueOnce({
          ok: true,
          text: async () =>
            JSON.stringify({
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
            }),
        })
        .mockResolvedValueOnce({
          ok: true,
          text: async () =>
            JSON.stringify({
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
            }),
        }),
    );

    const result = await checkHealth();

    expect(result.status).toBe("ok");
    expect(tauriApi.ensureDevApi).toHaveBeenCalled();
  });

  it("ensureLocalApiReady 会在桌面版自动等待 API 就绪", async () => {
    const tauriApi = await import("../src/api/tauri");
    vi.mocked(tauriApi.ensureDevApi).mockResolvedValueOnce(true);
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockRejectedValueOnce(new TypeError("fetch failed"))
        .mockResolvedValueOnce({
          ok: true,
          text: async () =>
            JSON.stringify({
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
            }),
        })
        .mockResolvedValueOnce({
          ok: true,
          text: async () =>
            JSON.stringify({
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
            }),
        }),
    );

    const result = await ensureLocalApiReady({ attempts: 2, delayMs: 0 });

    expect(result.registered_projects).toBe(3);
    expect(tauriApi.ensureDevApi).toHaveBeenCalled();
  });
});
