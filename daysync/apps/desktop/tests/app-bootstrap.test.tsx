import { render, waitFor } from "@testing-library/react";

import App from "../src/App";
import { AppStateProvider } from "../src/state/AppState";

vi.mock("../src/api/client", async () => {
  const actual = await vi.importActual<typeof import("../src/api/client")>("../src/api/client");
  return {
    ...actual,
    ensureLocalApiReady: vi.fn().mockResolvedValue({
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
    openProject: vi.fn().mockResolvedValue({
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
    }),
  };
});

vi.mock("../src/api/tauri", () => ({
  chooseDirectory: vi.fn().mockResolvedValue(null),
  chooseFiles: vi.fn().mockResolvedValue([]),
  chooseSubtitleFile: vi.fn().mockResolvedValue(null),
  listenForDirectoryDrops: vi.fn().mockResolvedValue(() => {}),
}));

describe("App bootstrap", () => {
  afterEach(() => {
    window.localStorage.clear();
    vi.clearAllMocks();
  });

  it("API 就绪后会自动恢复上次项目目录", async () => {
    const apiClient = await import("../src/api/client");
    window.localStorage.setItem("daysync.last_project_root", "D:\\projects\\demo");

    render(
      <AppStateProvider>
        <App />
      </AppStateProvider>,
    );

    await waitFor(() => {
      expect(apiClient.openProject).toHaveBeenCalledWith("D:\\projects\\demo");
    });
  });

  it("上次项目目录失效时会清除自动恢复记录", async () => {
    const apiClient = await import("../src/api/client");
    vi.mocked(apiClient.openProject).mockRejectedValueOnce(new Error("missing project"));
    window.localStorage.setItem("daysync.last_project_root", "D:\\projects\\missing");

    const view = render(
      <AppStateProvider>
        <App />
      </AppStateProvider>,
    );

    await waitFor(() => {
      expect(window.localStorage.getItem("daysync.last_project_root")).toBeNull();
    });
    await waitFor(() => {
      expect(
        view.getByText("上次项目目录已失效，自动恢复记录已清除，请重新打开项目。"),
      ).toBeInTheDocument();
    });
  });
});
