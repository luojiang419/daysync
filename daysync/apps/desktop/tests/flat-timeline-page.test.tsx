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
      video_source_subtitle_groups: [],
      audio_source_subtitle_groups: [],
      auto_conform_readiness: {
        status: "missing",
        reasons: ["missing_video_subtitles", "missing_audio_subtitles"],
        video_group_count: 0,
        audio_group_count: 0,
        video_warning_count: 0,
        audio_warning_count: 0,
        video_failed_count: 0,
        audio_failed_count: 0,
        video_eligible_seed_count: 0,
      },
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
    previewAutoConform: vi.fn().mockResolvedValue({
      representative_pair: {
        video_subtitle_id: "video-sub-1",
        video_text: "我们到了这里",
        video_source_media_file_id: "video-file-1",
        video_source_filename: "A001_C001.mov",
        video_source_start_ms: 1000,
        video_flat_start_ms: 1000,
        audio_subtitle_id: "audio-sub-1",
        audio_text: "我们到了这里",
        audio_source_media_file_id: "audio-file-1",
        audio_source_filename: "ZOOM0001.wav",
        audio_source_start_ms: 575180,
        audio_flat_start_ms: 575180,
        offset_ms: 574180,
        source_offset_ms: 574180,
        text_similarity: 1,
        context_similarity: 1,
        final_score: 1,
        candidate_margin: 0.3,
        reverse_margin: 0.3,
        reverse_match_consistent: true,
        negative_evidence_count: 0,
        mapping_warning: null,
        cluster_deviation_ms: 0,
        is_inlier: true,
      },
      anchor_pairs: [
        {
          video_subtitle_id: "video-sub-1",
          video_text: "我们到了这里",
          video_source_media_file_id: "video-file-1",
          video_source_filename: "A001_C001.mov",
          video_source_start_ms: 1000,
          video_flat_start_ms: 1000,
          audio_subtitle_id: "audio-sub-1",
          audio_text: "我们到了这里",
          audio_source_media_file_id: "audio-file-1",
          audio_source_filename: "ZOOM0001.wav",
          audio_source_start_ms: 575180,
          audio_flat_start_ms: 575180,
          offset_ms: 574180,
          source_offset_ms: 574180,
          text_similarity: 1,
          context_similarity: 1,
          final_score: 1,
          candidate_margin: 0.3,
          reverse_margin: 0.3,
          reverse_match_consistent: true,
          negative_evidence_count: 0,
          mapping_warning: null,
          cluster_deviation_ms: 0,
          is_inlier: true,
        },
      ],
      excluded_seeds: [],
      cluster_summary: {
        candidate_count: 1,
        median_offset_ms: 574180,
        final_offset_ms: 574180,
        inlier_count: 1,
        inlier_ratio: 1,
        passes: false,
        tolerance_ms: 500,
        min_inlier_ratio: 0.6,
        min_anchor_count: 3,
        reverse_consistent_count: 1,
        negative_evidence_pair_count: 0,
        reasons: ["not_enough_anchor_pairs"],
      },
      auto_accept_decision: {
        eligible: false,
        reasons: ["not_enough_anchor_pairs"],
        average_candidate_margin: 0.3,
        min_candidate_margin: 0.1,
      },
      preview_segments: [
        {
          id: "preview-1",
          video_media_file_id: "video-file-1",
          audio_media_file_id: "audio-file-1",
          video_file: "A001_C001.mov",
          audio_file: "ZOOM0001.wav",
          video_in_ms: 0,
          video_out_ms: 10000,
          audio_in_ms: 574180,
          audio_out_ms: 584180,
          offset_ms: 574180,
          timeline_start_ms: 0,
          timeline_end_ms: 10000,
        },
      ],
      ready_to_apply: true,
      selected_seed_count: 1,
      eligible_seed_count: 1,
    }),
    applyAutoConform: vi.fn().mockResolvedValue({
      sync_result: {
        id: "sync-1",
        offset_ms: 574180,
        status: "accepted_manual",
        source: "auto_text",
        confidence_score: 0.85,
      },
      generated_count: 1,
      track_offset_ms: 574180,
      sync_result_summary: {
        status: "accepted_manual",
        source: "auto_text",
        accepted_count: 1,
        representative_video_file: "A001_C001.mov",
        representative_audio_file: "ZOOM0001.wav",
      },
    }),
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

  it("可以展示自动整日合板预览结果", async () => {
    const user = userEvent.setup();
    const apiClient = await import("../src/api/client");
    vi.mocked(apiClient.getStudioTimeline).mockResolvedValueOnce({
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
      video_subtitle_track: {
        id: "video-track-1",
        kind: "video_ref",
        name: "video_ref",
        track_type: "video_ref",
        source_type: "srt_import",
        language: "zh-CN",
        original_path: "D:\\subs\\video_flat.srt",
        cue_count: 1,
        total_duration_ms: 10000,
        created_at: "2026-05-17T10:00:00Z",
      },
      audio_subtitle_track: {
        id: "audio-track-1",
        kind: "external_audio",
        name: "external_audio",
        track_type: "external_audio",
        source_type: "srt_import",
        language: "zh-CN",
        original_path: "D:\\subs\\audio_flat.srt",
        cue_count: 1,
        total_duration_ms: 12000,
        created_at: "2026-05-17T10:00:00Z",
      },
      video_clips: [],
      audio_clips: [],
      video_subtitles: [],
      audio_subtitles: [],
      video_source_subtitle_groups: [
        {
          media_file_id: "video-file-1",
          source_filename: "A001_C001.mov",
          cue_count: 1,
          warning_count: 0,
          failed_count: 0,
          eligible_seed_count: 1,
          cues: [],
        },
      ],
      audio_source_subtitle_groups: [
        {
          media_file_id: "audio-file-1",
          source_filename: "ZOOM0001.wav",
          cue_count: 1,
          warning_count: 0,
          failed_count: 0,
          eligible_seed_count: 1,
          cues: [],
        },
      ],
      auto_conform_readiness: {
        status: "ready",
        reasons: [],
        video_group_count: 1,
        audio_group_count: 1,
        video_warning_count: 0,
        audio_warning_count: 0,
        video_failed_count: 0,
        audio_failed_count: 0,
        video_eligible_seed_count: 1,
      },
      sync_segments: [],
      accepted_sync_summary: {
        status: "missing",
        accepted_count: 0,
        median_offset_ms: null,
        latest_source: null,
        latest_updated_at: null,
      },
    });

    render(<FlatTimelinePage />);

    await screen.findByText("自动整日合板");
    await user.click(screen.getByRole("button", { name: "自动分析整日锚点" }));

    await waitFor(() => {
      expect(apiClient.previewAutoConform).toHaveBeenCalledWith("project-1", {
        context_radius: 2,
        min_anchor_count: 3,
        tolerance_ms: 500,
        min_inlier_ratio: 0.6,
      });
    });
    expect(screen.getByText("代表锚点")).toBeInTheDocument();
    expect(screen.getByText("确认此 offset 并生成时间线")).toBeInTheDocument();
  });
});
