import { render, screen } from "@testing-library/react";

import { SyncResultCard } from "../src/components/SyncResultCard";

describe("SyncResultCard", () => {
  it("展示自动结果依据和复核历史", () => {
    render(
      <SyncResultCard
        item={{
          id: "sync-1",
          offset_ms: 574180,
          status: "accepted_auto",
          source: "auto_text",
          confidence_score: 0.93,
          video_in_ms: 0,
          video_out_ms: 10000,
          audio_in_ms: 574180,
          audio_out_ms: 584180,
          video_file: "A001.mov",
          audio_file: "ZOOM0001.wav",
          video_anchor_text: "现在开始",
          audio_anchor_text: "现在开始",
          created_at: "2026-05-17T13:20:00Z",
          confidence_breakdown: {
            text_similarity: 0.95,
            context_similarity: 0.88,
            offset_cluster_stability: 0.75,
            reverse_match_consistency: 1,
            candidate_margin: 0.16,
            negative_evidence_count: 0,
            final_score: 0.93,
            auto_accept_decision: {
              eligible: true,
              reasons: [],
              average_candidate_margin: 0.16,
              min_candidate_margin: 0.1,
            },
            cluster_summary: {
              passes: true,
              inlier_ratio: 0.75,
              candidate_count: 4,
              final_offset_ms: 574180,
              reasons: [],
            },
            pair_analyses: [
              {
                video_text: "现在开始",
                audio_text: "现在开始",
                offset_ms: 574180,
                final_score: 0.95,
                reverse_match_consistent: true,
                cluster_deviation_ms: 0,
                negative_evidence_count: 0,
                is_inlier: true,
              },
            ],
          },
          review_events: [
            {
              id: "event-1",
              sync_result_id: "sync-1",
              event_type: "accepted",
              old_offset_ms: 574180,
              new_offset_ms: 574180,
              note: "自动通过",
              created_at: "2026-05-17T13:21:00Z",
            },
          ],
        }}
      />,
    );

    expect(screen.getByText(/状态 accepted_auto/)).toBeInTheDocument();
    expect(screen.queryByText(/当前结果没有自动评分拆解/)).not.toBeInTheDocument();
    expect(screen.getByText(/自动通过判断/)).toBeInTheDocument();
    expect(screen.getByText(/自动通过 · 2026-05-17T13:21:00Z/)).toBeInTheDocument();
  });

  it("为手动结果显示无自动拆解提示", () => {
    render(
      <SyncResultCard
        item={{
          id: "sync-2",
          offset_ms: 574180,
          status: "accepted_manual",
          source: "manual_anchor",
          confidence_score: 1,
          video_file: "A001.mov",
          audio_file: "ZOOM0001.wav",
          review_events: [],
        }}
      />,
    );

    expect(screen.getByText(/当前结果没有自动评分拆解/)).toBeInTheDocument();
  });
});
