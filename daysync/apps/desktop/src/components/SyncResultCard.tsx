import type { ReviewEvent, SyncResult } from "../api/types";

type Props = {
  item: SyncResult;
};

type ConfidenceBreakdown = {
  text_similarity?: number;
  context_similarity?: number;
  offset_cluster_stability?: number;
  reverse_match_consistency?: number;
  candidate_margin?: number;
  negative_evidence_count?: number;
  final_score?: number;
  auto_accept_decision?: {
    eligible?: boolean;
    reasons?: string[];
    average_candidate_margin?: number;
    min_candidate_margin?: number;
  };
  cluster_summary?: {
    passes?: boolean;
    inlier_ratio?: number;
    candidate_count?: number;
    final_offset_ms?: number | null;
    reasons?: string[];
  };
  pair_analyses?: Array<{
    video_text?: string;
    audio_text?: string;
    offset_ms?: number;
    final_score?: number;
    reverse_match_consistent?: boolean;
    cluster_deviation_ms?: number;
    negative_evidence_count?: number;
    is_inlier?: boolean;
  }>;
  note?: string | null;
};

function percent(value: number | undefined): string {
  return `${Math.round((value ?? 0) * 100)}%`;
}

function reviewLabel(event: ReviewEvent): string {
  return `${event.event_type} · old ${event.old_offset_ms ?? "-"} · new ${event.new_offset_ms ?? "-"} · ${event.note ?? "无备注"} · ${event.created_at}`;
}

export function SyncResultCard({ item }: Props) {
  const confidence = (item.confidence_breakdown ?? {}) as ConfidenceBreakdown;
  const autoAccept = confidence.auto_accept_decision;
  const clusterSummary = confidence.cluster_summary;
  const pairAnalyses = confidence.pair_analyses ?? [];
  const hasAutoBreakdown = item.source === "auto_text" && Object.keys(confidence).length > 0;

  return (
    <article className="cluster-sample-card result-card-detailed">
      <div className="candidate-card-header">
        <strong>
          {item.video_file ?? "-"} ↔ {item.audio_file ?? "-"}
        </strong>
        <span>{Math.round(item.confidence_score * 100)} 分</span>
      </div>

      <div className="candidate-meta">
        <span>
          状态 {item.status} · 来源 {item.source}
        </span>
        <span>
          offset {item.offset_ms} ms · 视频区间 {item.video_in_ms ?? "-"} - {item.video_out_ms ?? "-"}
        </span>
      </div>

      <div className="candidate-context">
        <small>视频锚点：{item.video_anchor_text ?? "-"}</small>
        <small>音频锚点：{item.audio_anchor_text ?? "-"}</small>
        <small>创建时间：{item.created_at ?? "-"}</small>
      </div>

      {hasAutoBreakdown ? (
        <>
          <details className="explain-details">
            <summary>自动结果依据</summary>
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
              <small>eligible：{autoAccept?.eligible ? "true" : "false"}</small>
              <small>
                average_candidate_margin：{percent(autoAccept?.average_candidate_margin)}
              </small>
              <small>min_candidate_margin：{percent(autoAccept?.min_candidate_margin)}</small>
              <small>reasons：{(autoAccept?.reasons ?? []).join(", ") || "无"}</small>
            </div>
          </details>

          <details className="explain-details">
            <summary>聚类摘要</summary>
            <div className="candidate-context">
              <small>passes：{clusterSummary?.passes ? "true" : "false"}</small>
              <small>inlier_ratio：{percent(clusterSummary?.inlier_ratio)}</small>
              <small>candidate_count：{clusterSummary?.candidate_count ?? 0}</small>
              <small>final_offset_ms：{clusterSummary?.final_offset_ms ?? "-"}</small>
              <small>reasons：{(clusterSummary?.reasons ?? []).join(", ") || "无"}</small>
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
                    <th>score</th>
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
        </>
      ) : (
        <div className="candidate-context">
          <small>当前结果没有自动评分拆解，通常是手动锚点或人工微调结果。</small>
        </div>
      )}

      <details className="explain-details" open={Boolean(item.review_events?.length)}>
        <summary>复核历史</summary>
        <div className="candidate-context">
          {item.review_events?.length ? (
            item.review_events.map((event) => <small key={event.id}>{reviewLabel(event)}</small>)
          ) : (
            <small>当前没有复核历史。</small>
          )}
        </div>
      </details>
    </article>
  );
}
