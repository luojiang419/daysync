import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@tauri-apps/api/core", () => ({
  convertFileSrc: vi.fn(),
  invoke: vi.fn(),
}));

vi.mock("@tauri-apps/api/webview", () => ({
  getCurrentWebview: vi.fn(() => ({
    onDragDropEvent: vi.fn(),
  })),
}));

vi.mock("@tauri-apps/plugin-dialog", () => ({
  open: vi.fn(),
}));

describe("tauri runtime bridge", () => {
  afterEach(() => {
    delete window.__TAURI_INTERNALS__;
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("会等待 Tauri IPC 注入后再执行本地运行时握手", async () => {
    vi.useFakeTimers();
    const coreApi = await import("@tauri-apps/api/core");
    const tauriApi = await import("../src/api/tauri");

    vi.mocked(coreApi.invoke).mockResolvedValueOnce({
      ok: true,
      result: {
        status: "ok",
      },
    });

    const pending = tauriApi.ensureRuntimeReady<{ status: string }>();

    setTimeout(() => {
      window.__TAURI_INTERNALS__ = { invoke: vi.fn() };
    }, 120);

    await vi.advanceTimersByTimeAsync(200);

    await expect(pending).resolves.toEqual({ status: "ok" });
    expect(coreApi.invoke).toHaveBeenCalledWith("ensure_runtime_ready", undefined);
  });

  it("首轮返回运行时不可用时会自动重试一次", async () => {
    vi.useFakeTimers();
    window.__TAURI_INTERNALS__ = { invoke: vi.fn() };

    const coreApi = await import("@tauri-apps/api/core");
    const tauriApi = await import("../src/api/tauri");

    vi.mocked(coreApi.invoke)
      .mockResolvedValueOnce({
        ok: false,
        error: {
          code: "RUNTIME_UNAVAILABLE",
          message: "未能连接本地运行时，请稍后重试。",
          details: { cause: "worker warming up" },
        },
      })
      .mockResolvedValueOnce({
        ok: true,
        result: {
          status: "ok",
        },
      });

    const pending = tauriApi.ensureRuntimeReady<{ status: string }>();
    await vi.advanceTimersByTimeAsync(300);

    await expect(pending).resolves.toEqual({ status: "ok" });
    expect(coreApi.invoke).toHaveBeenCalledTimes(2);
  });
});
