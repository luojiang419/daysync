import type { ProjectSnapshot } from "../src/api/types";
import { appReducer, initialState } from "../src/state/AppState";

describe("appReducer", () => {
  it("可以用项目快照整体刷新状态", () => {
    const snapshot: ProjectSnapshot = {
      project: {
        id: "project-1",
        name: "测试项目",
        root_path: "D:\\projects\\demo",
      },
      stats: {
        media_count: 1,
        subtitle_count: 2,
        sync_result_count: 1,
      },
      media_files: [{ id: "media-1", media_type: "video", filename: "A001.mov", duration_ms: 1000 }],
      flat_timelines: [
        {
          id: "timeline-1",
          media_type: "video",
          items: [
            {
              media_file_id: "media-1",
              flat_start_ms: 0,
              flat_end_ms: 1000,
              source_start_ms: 0,
              source_end_ms: 1000,
            },
          ],
        },
      ],
      sync_results: [
        {
          id: "sync-1",
          offset_ms: 574180,
          status: "accepted_manual",
          source: "manual_anchor",
          confidence_score: 1,
        },
      ],
      project_settings: {
        subtitle_workspace: {
          video_timeline_id: "timeline-1",
          audio_timeline_id: "",
          video_srt_path: "",
          audio_srt_path: "",
          query: "我们到了这里",
          cluster_samples: [],
        },
        export_workspace: {
          output_path: "D:\\projects\\demo\\exports\\sync_report.csv",
          status_filter: "all",
          source_filter: "all",
          min_confidence_filter: "0",
        },
      },
    };

    const nextState = appReducer(initialState, { type: "HYDRATE_PROJECT", payload: snapshot });
    expect(nextState.currentProject?.name).toBe("测试项目");
    expect(nextState.projectSettings?.subtitle_workspace.query).toBe("我们到了这里");
    expect(nextState.mediaFiles).toHaveLength(1);
    expect(nextState.flatTimelines[0].flat_timeline_id).toBe("timeline-1");
    expect(nextState.syncResults[0].offset_ms).toBe(574180);
  });
});
