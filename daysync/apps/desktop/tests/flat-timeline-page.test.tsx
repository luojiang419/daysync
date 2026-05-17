import { render, screen } from "@testing-library/react";

import { FlatTimelinePage } from "../src/pages/FlatTimelinePage";

vi.mock("../src/state/AppState", () => ({
  useAppState: () => ({
    state: {
      flatTimelines: [
        {
          id: "video-timeline-1",
          flat_timeline_id: "video-timeline-1",
          media_type: "video",
          gap_ms: 1000,
          items: [
            {
              id: "video-item-1",
              media_file_id: "video-file-1",
              flat_start_ms: 0,
              flat_end_ms: 10000,
              source_start_ms: 0,
              source_end_ms: 10000,
              filename: "A001_C001.mov",
            },
          ],
        },
        {
          id: "audio-timeline-1",
          flat_timeline_id: "audio-timeline-1",
          media_type: "audio",
          gap_ms: 1000,
          items: [
            {
              id: "audio-item-1",
              media_file_id: "audio-file-1",
              flat_start_ms: 0,
              flat_end_ms: 12000,
              source_start_ms: 0,
              source_end_ms: 12000,
              filename: "ZOOM0001.wav",
            },
          ],
        },
      ],
    },
  }),
}));

describe("FlatTimelinePage", () => {
  it("展示自动整轨总览而不是复选框选择器", () => {
    render(<FlatTimelinePage />);

    expect(screen.getByText("目录导入后自动生成整轨")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByText("A001_C001.mov")).toBeInTheDocument();
    expect(screen.getByText("ZOOM0001.wav")).toBeInTheDocument();
  });
});
