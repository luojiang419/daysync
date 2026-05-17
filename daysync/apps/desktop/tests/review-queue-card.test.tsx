import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ReviewQueueCard } from "../src/components/ReviewQueueCard";

describe("ReviewQueueCard", () => {
  it("展示解释信息并支持记录备注", async () => {
    const user = userEvent.setup();
    const onReviewAction = vi.fn();
    const onAdjustOffsetChange = vi.fn();
    const onNoteChange = vi.fn();

    render(
      <ReviewQueueCard
        item={{
          id: "sync-1",
          project_id: "project-1",
          video_media_file_id: "video-media-1",
          audio_media_file_id: "audio-media-1",
          video_in_ms: 0,
          video_out_ms: 10000,
          audio_in_ms: 574180,
          audio_out_ms: 584180,
          offset_ms: 574180,
          confidence_score: 0.92,
          status: "needs_review",
          source: "auto_text",
          video_anchor_subtitle_id: "video-sub-1",
          audio_anchor_subtitle_id: "audio-sub-1",
          created_at: "2026-05-17T13:00:00Z",
          updated_at: "2026-05-17T13:00:00Z",
          video_file: "A001.mov",
          audio_file: "ZOOM0001.wav",
          video_anchor_text: "现在开始",
          audio_anchor_text: "现在开始",
          confidence_breakdown: {
            text_similarity: 0.95,
            context_similarity: 0.88,
            offset_cluster_stability: 0.75,
            reverse_match_consistency: 1,
            candidate_margin: 0.16,
            negative_evidence_count: 0,
            final_score: 0.92,
            cluster_summary: {
              passes: true,
              inlier_ratio: 0.75,
              reasons: [],
            },
            auto_accept_decision: {
              eligible: false,
              reasons: ["candidate_margin_too_small"],
              average_candidate_margin: 0.08,
              min_candidate_margin: 0.1,
            },
            pair_analyses: [
              {
                video_text: "现在开始",
                audio_text: "现在开始",
                offset_ms: 574180,
                final_score: 0.95,
                reverse_match_consistent: true,
                negative_evidence_count: 0,
                cluster_deviation_ms: 0,
                is_inlier: true,
              },
            ],
          },
          review_events: [
            {
              id: "event-1",
              sync_result_id: "sync-1",
              event_type: "commented",
              old_offset_ms: 574180,
              new_offset_ms: null,
              note: "需要导演确认",
              created_at: "2026-05-17T13:01:00Z",
            },
          ],
        }}
        reviewBusy={false}
        adjustOffset="574180"
        note="补充说明"
        onAdjustOffsetChange={onAdjustOffsetChange}
        onNoteChange={onNoteChange}
        onReviewAction={onReviewAction}
      />,
    );

    expect(screen.getByText(/自动通过预判：需复核/)).toBeInTheDocument();
    expect(screen.getByText(/candidate_margin_too_small/)).toBeInTheDocument();
    expect(screen.getByText(/需要导演确认/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "记录备注" }));
    expect(onReviewAction).toHaveBeenCalledWith("commented");
  });
});
