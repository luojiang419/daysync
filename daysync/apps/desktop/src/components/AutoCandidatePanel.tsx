import type { AutoCandidate, AutoCandidateResponse } from "../api/types";

type Props = {
  recommendation: AutoCandidateResponse;
  onUseCandidate: (candidate: AutoCandidate) => void;
};

export function AutoCandidatePanel({ recommendation, onUseCandidate }: Props) {
  return (
    <section className="auto-candidate-panel">
      <header className="result-column-header">
        <div>
          <h3>自动推荐候选</h3>
          <span>
            锚点：{recommendation.anchor.raw_text} · 目标轨道{" "}
            {recommendation.target_track_type === "external_audio" ? "外录音频" : "视频参考"}
          </span>
        </div>
        <span>Top {recommendation.limit}</span>
      </header>

      <div className="candidate-grid">
        {recommendation.candidates.map((candidate) => (
          <article key={candidate.subtitle_id} className="candidate-card">
            <div className="candidate-card-header">
              <strong>{candidate.raw_text}</strong>
              <span>{Math.round(candidate.final_score * 100)} 分</span>
            </div>
            <div className="candidate-meta">
              <span>
                文本相似 {Math.round(candidate.text_similarity * 100)}% · 上下文相似{" "}
                {Math.round(candidate.context_similarity * 100)}%
              </span>
              <span>
                {candidate.source_filename ?? "未映射素材"} · {candidate.source_start_ms ?? "-"} ms
              </span>
            </div>
            <div className="candidate-context">
              <small>前文：{candidate.context_before_text || "无"}</small>
              <small>后文：{candidate.context_after_text || "无"}</small>
            </div>
            <button
              type="button"
              className="secondary-button"
              onClick={() => onUseCandidate(candidate)}
            >
              使用这个候选
            </button>
          </article>
        ))}
      </div>
    </section>
  );
}
