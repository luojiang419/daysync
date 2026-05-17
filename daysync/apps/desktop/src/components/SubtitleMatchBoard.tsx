import type { SearchResult } from "../api/types";

type Props = {
  videoResults: SearchResult[];
  audioResults: SearchResult[];
  selectedVideoSubtitleId: string | null;
  selectedAudioSubtitleId: string | null;
  isAligning: boolean;
  lastOffsetMs: number | null;
  onSelectVideo: (subtitleId: string) => void;
  onSelectAudio: (subtitleId: string) => void;
  onAlign: () => void;
};

function ResultCard({
  title,
  results,
  selectedId,
  onSelect,
}: {
  title: string;
  results: SearchResult[];
  selectedId: string | null;
  onSelect: (subtitleId: string) => void;
}) {
  return (
    <section className="result-column">
      <header className="result-column-header">
        <h3>{title}</h3>
        <span>{results.length} 条命中</span>
      </header>
      <div className="result-list">
        {results.map((result) => (
          <button
            key={result.subtitle_id}
            type="button"
            className={`result-card${selectedId === result.subtitle_id ? " selected" : ""}`}
            onClick={() => onSelect(result.subtitle_id)}
          >
            <strong>{result.raw_text}</strong>
            <span>
              {result.source_filename ?? "未映射素材"} · 源时间 {result.source_start_ms ?? "-"} ms
            </span>
            <small>
              Flat {result.flat_start_ms} - {result.flat_end_ms} ms
            </small>
          </button>
        ))}
      </div>
    </section>
  );
}

export function SubtitleMatchBoard({
  videoResults,
  audioResults,
  selectedVideoSubtitleId,
  selectedAudioSubtitleId,
  isAligning,
  lastOffsetMs,
  onSelectVideo,
  onSelectAudio,
  onAlign,
}: Props) {
  return (
    <div className="match-board">
      <div className="result-grid">
        <ResultCard
          title="视频字幕"
          results={videoResults}
          selectedId={selectedVideoSubtitleId}
          onSelect={onSelectVideo}
        />
        <ResultCard
          title="外录音频字幕"
          results={audioResults}
          selectedId={selectedAudioSubtitleId}
          onSelect={onSelectAudio}
        />
      </div>

      <div className="align-bar">
        <button
          type="button"
          className="primary-button"
          disabled={!selectedVideoSubtitleId || !selectedAudioSubtitleId || isAligning}
          onClick={onAlign}
        >
          {isAligning ? "计算中..." : "一键对齐"}
        </button>
        <span className="offset-pill">
          最近 offset: {lastOffsetMs === null ? "尚未计算" : `${lastOffsetMs} ms`}
        </span>
      </div>
    </div>
  );
}
