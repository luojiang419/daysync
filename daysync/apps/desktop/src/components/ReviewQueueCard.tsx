import type { ReviewQueueItem } from "../api/types";

type ReviewAction = "accepted" | "rejected" | "adjusted" | "commented";

type Props = {
  item: ReviewQueueItem;
  reviewBusy: boolean;
  adjustOffset: string;
  note: string;
  onAdjustOffsetChange: (value: string) => void;
  onNoteChange: (value: string) => void;
  onReviewAction: (action: ReviewAction) => void;
};

type ClusterSummary = {
  final_offset_ms?: number | null;
  inlier_ratio?: number;
  passes?: boolean;
  reasons?: string[];
};

type AutoAcceptDecision = {
  eligible?: boolean;
  reasons?: string[];
  average_candidate_margin?: number;
  min_candidate_margin?: number;
};

type ConfidenceBreakdown = {
  text_similarity?: number;
  context_similarity?: number;
  offset_cluster_stability?: number;
  reverse_match_consistency?: number;
  candidate_margin?: number;
  negative_evidence_count?: number;
  final_score?: number;
  cluster_summary?: ClusterSummary;
  auto_accept_decision?: AutoAcceptDecision;
  pair_analyses?: Array<{
    video_text?: string;
    audio_text?: string;
    offset_ms?: number;
    final_score?: number;
    reverse_match_consistent?: boolean;
    negative_evidence_count?: number;
    cluster_deviation_ms?: number;
    is_inlier?: boolean;
    mapping_warning?: string | null;
  }>;
  note?: string | null;
};

function asConfidenceBreakdown(value: Record<string, unknown>): ConfidenceBreakdown {
  return value as unknown as ConfidenceBreakdown;
}

function percent(value: number | undefined): string {
  return `${Math.round((value ?? 0) * 100)}%`;
}

export function ReviewQueueCard({
  item,
  reviewBusy,
  adjustOffset,
  note,
  onAdjustOffsetChange,
  onNoteChange,
  onReviewAction,
}: Props) {
  const confidence = asConfidenceBreakdown(item.confidence_breakdown);
  const clusterSummary = confidence.cluster_summary ?? {};
  const autoAcceptDecision = confidence.auto_accept_decision ?? {};
  const pairAnalyses = confidence.pair_analyses ?? [];

  return (
    <article className="cluster-sample-card review-card">
      <div className="candidate-card-header">
        <strong>
          {item.video_file} ↔ {item.audio_file}
        </strong>
        <span>{Math.round(item.confidence_score * 100)} 分</span>
      </div>

      <div className="candidate-meta">
        <span>
          当前 offset {item.offset_ms} ms · 状态 {item.status}
        </span>
        <span>
          聚类 {clusterSummary.passes ? "通过" : "未通过"} · inlier ratio{" "}
          {Math.round((clusterSummary.inlier_ratio ?? 0) * 100)}%
        </span>
      </div>

      <div className="candidate-context">
        <small>视频锚点：{item.video_anchor_text ?? "-"}</small>
        <small>音频锚点：{item.audio_anchor_text ?? "-"}</small>
        <small>自动通过预判：{autoAcceptDecision.eligible ? "可自动通过" : "需复核"}</small>
        <small>原因：{(clusterSummary.reasons ?? []).join(", ") || "无"}</small>
      </div>

      <div className="inline-field">
        <input value={adjustOffset} onChange={(event) => onAdjustOffsetChange(event.target.value)} />
        <button
          type="button"
          className="secondary-button"
          disabled={reviewBusy}
          onClick={() => onReviewAction("accepted")}
        >
          接受
        </button>
        <button
          type="button"
          className="secondary-button"
          disabled={reviewBusy}
          onClick={() => onReviewAction("adjusted")}
        >
          微调后接受
        </button>
        <button
          type="button"
          className="ghost-button"
          disabled={reviewBusy}
          onClick={() => onReviewAction("rejected")}
        >
          拒绝
        </button>
      </div>

      <label className="form-stack">
        <span>复核备注</span>
        <div className="inline-field">
          <input
            value={note}
            onChange={(event) => onNoteChange(event.target.value)}
            placeholder="记录负证据、现场情况或人工判断依据"
          />
          <button
            type="button"
            className="ghost-button"
            disabled={reviewBusy || !note.trim()}
            onClick={() => onReviewAction("commented")}
          >
            记录备注
          </button>
        </div>
      </label>

      <details className="explain-details">
        <summary>评分拆解</summary>
        <div className="candidate-context">
          <small>text_similarity：{percent(confidence.text_similarity)}</small>
          <small>context_similarity：{percent(confidence.context_similarity)}</small>
          <small>offset_cluster_stability：{percent(confidence.offset_cluster_stability)}</small>
          <small>reverse_match_consistency：{percent(confidence.reverse_match_consistency)}</small>
          <small>candidate_margin：{percent(confidence.candidate_margin)}</small>
          <small>negative_evidence_count：{confidence.negative_evidence_count ?? 0}</small>
          <small>final_score：{percent(confidence.final_score)}</small>
        </div>
      </details>

      <details className="explain-details">
        <summary>自动通过判断</summary>
        <div className="candidate-context">
          <small>eligible：{autoAcceptDecision.eligible ? "true" : "false"}</small>
          <small>
            average_candidate_margin：{percent(autoAcceptDecision.average_candidate_margin)}
          </small>
          <small>min_candidate_margin：{percent(autoAcceptDecision.min_candidate_margin)}</small>
          <small>reasons：{(autoAcceptDecision.reasons ?? []).join(", ") || "无"}</small>
        </div>
      </details>

      <details className="explain-details">
        <summary>锚点 pair 明细</summary>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>视频字幕</th>
                <th>音频字幕</th>
                <th>offset</th>
                <th>final_score</th>
                <th>reverse</th>
                <th>deviation</th>
                <th>negative</th>
                <th>inlier</th>
              </tr>
            </thead>
            <tbody>
              {pairAnalyses.map((analysis, index) => (
                <tr key={`${analysis.video_text ?? "video"}:${analysis.audio_text ?? "audio"}:${index}`}>
                  <td>{analysis.video_text ?? "-"}</td>
                  <td>{analysis.audio_text ?? "-"}</td>
                  <td>{analysis.offset_ms ?? "-"}</td>
                  <td>{percent(analysis.final_score)}</td>
                  <td>{analysis.reverse_match_consistent ? "一致" : "不一致"}</td>
                  <td>{analysis.cluster_deviation_ms ?? "-"}</td>
                  <td>{analysis.negative_evidence_count ?? 0}</td>
                  <td>{analysis.is_inlier ? "是" : "否"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>

      <details className="explain-details" open={item.review_events.length > 0}>
        <summary>复核历史</summary>
        <div className="candidate-context">
          {item.review_events.length ? (
            item.review_events.map((event) => (
              <small key={event.id}>
                {event.event_type} · old {event.old_offset_ms ?? "-"} · new {event.new_offset_ms ?? "-"} ·{" "}
                {event.note ?? "无备注"} · {event.created_at}
              </small>
            ))
          ) : (
            <small>当前还没有复核历史。</small>
          )}
        </div>
      </details>
    </article>
  );
}
