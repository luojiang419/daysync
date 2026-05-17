import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { FlatTimelinePage } from "../src/pages/FlatTimelinePage";

class ResizeObserverMock {
  observe() {}
  disconnect() {}
  unobserve() {}
}

Object.defineProperty(globalThis, "ResizeObserver", {
  writable: true,
  value: ResizeObserverMock,
});

Object.defineProperty(HTMLMediaElement.prototype, "pause", {
  configurable: true,
  value: vi.fn(),
});

Object.defineProperty(HTMLMediaElement.prototype, "play", {
  configurable: true,
  value: vi.fn().mockResolvedValue(undefined),
});

Object.defineProperty(HTMLMediaElement.prototype, "load", {
  configurable: true,
  value: vi.fn(),
});

vi.mock("../src/state/AppState", () => ({
  useAppState: () => ({
    state: {
      currentProject: {
        id: "project-1",
        name: "测试项目",
        root_path: "D:\\projects\\demo",
      },
    },
    dispatch: vi.fn(),
  }),
}));

vi.mock("../src/api/tauri", () => ({
  chooseSubtitleFile: vi.fn().mockResolvedValue(null),
  isTauriRuntime: vi.fn().mockReturnValue(false),
  toMediaAssetUrl: vi.fn().mockReturnValue(null),
}));

vi.mock("../src/api/client", async () => {
  const actual = await vi.importActual<typeof import("../src/api/client")>("../src/api/client");
  return {
    ...actual,
    getStudioTimeline: vi.fn().mockResolvedValue({
      project_id: "project-1",
      video_timeline: {
        id: "video-timeline-1",
        kind: "video_timeline",
        name: "video_flat_timeline",
        media_type: "video",
        gap_ms: 1000,
        sort_mode: "filename",
        item_count: 1,
        total_duration_ms: 10000,
        created_at: "2026-05-17T10:00:00Z",
      },
      audio_timeline: {
        id: "audio-timeline-1",
        kind: "audio_timeline",
        name: "audio_flat_timeline",
        media_type: "audio",
        gap_ms: 1000,
        sort_mode: "filename",
        item_count: 1,
        total_duration_ms: 12000,
        created_at: "2026-05-17T10:00:00Z",
      },
      video_subtitle_track: null,
      audio_subtitle_track: null,
      video_clips: [
        {
          id: "video-item-1",
          timeline_id: "video-timeline-1",
          media_file_id: "video-file-1",
          item_index: 0,
          media_type: "video",
          filename: "A001_C001.mov",
          original_path: "D:\\media\\A001_C001.mov",
          flat_start_ms: 0,
          flat_end_ms: 10000,
          source_start_ms: 0,
          source_end_ms: 10000,
          gap_after_ms: 1000,
          has_video: true,
          has_audio: true,
        },
      ],
      audio_clips: [
        {
          id: "audio-item-1",
          timeline_id: "audio-timeline-1",
          media_file_id: "audio-file-1",
          item_index: 0,
          media_type: "audio",
          filename: "ZOOM0001.wav",
          original_path: "D:\\audio\\ZOOM0001.wav",
          flat_start_ms: 0,
          flat_end_ms: 12000,
          source_start_ms: 0,
          source_end_ms: 12000,
          gap_after_ms: 1000,
          has_video: false,
          has_audio: true,
        },
      ],
      video_subtitles: [],
      audio_subtitles: [],
      sync_segments: [],
      accepted_sync_summary: {
        status: "missing",
        accepted_count: 0,
        median_offset_ms: null,
        latest_source: null,
        latest_updated_at: null,
      },
    }),
    importSubtitles: vi.fn(),
    searchSubtitles: vi.fn(),
    createManualSync: vi.fn(),
    listSyncResults: vi.fn().mockResolvedValue({ sync_results: [] }),
  };
});

describe("FlatTimelinePage", () => {
  it("展示剪辑台式四轨布局和媒体片段", async () => {
    render(<FlatTimelinePage />);

    expect(await screen.findByText("播放器")).toBeInTheDocument();
    expect(screen.getByText("时间线轨道")).toBeInTheDocument();
    expect(screen.getByText("V1")).toBeInTheDocument();
    expect(screen.getByText("S1")).toBeInTheDocument();
    expect(screen.getByText("A1")).toBeInTheDocument();
    expect(screen.getByText("S2")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getAllByText("A001_C001.mov").length).toBeGreaterThan(0);
    expect(screen.getAllByText("ZOOM0001.wav").length).toBeGreaterThan(0);
  });

  it("无 accepted 同步结果时显示参考音回退提示", async () => {
    const user = userEvent.setup();
    render(<FlatTimelinePage />);

    await screen.findByText("当前回退为视频参考音");
    expect(screen.getByText("尚未建立外录音频预览同步")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "播放" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "缩小" }));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "适配" })).toBeInTheDocument();
    });
  });
});
