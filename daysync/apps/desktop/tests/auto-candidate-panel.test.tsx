import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AutoCandidatePanel } from "../src/components/AutoCandidatePanel";

describe("AutoCandidatePanel", () => {
  it("显示候选评分并支持应用候选", async () => {
    const user = userEvent.setup();
    const onUseCandidate = vi.fn();
    render(
      <AutoCandidatePanel
        recommendation={{
          anchor: {
            subtitle_id: "video-1",
            track_type: "video_ref",
            track_id: "track-video",
            raw_text: "我们到了这里",
            normalized_text: "我们到了这里",
            source_media_file_id: "media-video",
            source_filename: "A001.mov",
            source_start_ms: 1000,
            source_end_ms: 2500,
            flat_start_ms: 1000,
            flat_end_ms: 2500,
            mapping_status: "ok",
            mapping_warning: null,
            context_before_text: "现在开始",
            context_after_text: "继续往前走",
            context_window_text: "现在开始 | 我们到了这里 | 继续往前走",
          },
          target_track_type: "external_audio",
          limit: 5,
          context_radius: 1,
          candidates: [
            {
              subtitle_id: "audio-1",
              track_type: "external_audio",
              track_id: "track-audio",
              raw_text: "我们到了这里",
              normalized_text: "我们到了这里",
              source_media_file_id: "media-audio",
              source_filename: "ZOOM0001.wav",
              source_start_ms: 575180,
              source_end_ms: 576680,
              flat_start_ms: 575180,
              flat_end_ms: 576680,
              mapping_status: "ok",
              mapping_warning: null,
              text_similarity: 1,
              context_similarity: 1,
              final_score: 1,
              negative_evidence_count: 0,
              duplicate_count: 1,
              context_before_text: "现在开始",
              context_after_text: "继续往前走",
              context_window_text: "现在开始 | 我们到了这里 | 继续往前走",
            },
          ],
        }}
        onUseCandidate={onUseCandidate}
      />,
    );

    expect(screen.getByText("自动推荐候选")).toBeInTheDocument();
    expect(screen.getByText(/文本相似 100%/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "使用这个候选" }));
    expect(onUseCandidate).toHaveBeenCalledTimes(1);
    expect(onUseCandidate.mock.calls[0][0].subtitle_id).toBe("audio-1");
  });
});
