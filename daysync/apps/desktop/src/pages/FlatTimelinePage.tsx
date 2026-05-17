import { useMemo } from "react";

import type { FlatTimeline } from "../api/types";
import { useAppState } from "../state/AppState";

export function FlatTimelinePage() {
  const { state } = useAppState();
  const latestVideoTimeline = useMemo(() => {
    const timelines = state.flatTimelines.filter((timeline) => timeline.media_type === "video");
    return timelines[timelines.length - 1] ?? null;
  }, [state.flatTimelines]);
  const latestAudioTimeline = useMemo(() => {
    const timelines = state.flatTimelines.filter((timeline) => timeline.media_type === "audio");
    return timelines[timelines.length - 1] ?? null;
  }, [state.flatTimelines]);

  return (
    <section className="page-grid">
      <article className="panel-card hero-card span-two">
        <div>
          <span className="eyebrow">轨道总览</span>
          <h2>目录导入后自动生成整轨</h2>
          <p>
            当前页只展示自动生成的“视频整轨”和“音频整轨”。不再需要逐个素材打勾，目录内素材会直接按顺序平铺成剪辑软件风格的时间线轨道。
          </p>
        </div>
      </article>

      <TimelineOverviewCard title="视频整轨" timeline={latestVideoTimeline} />
      <TimelineOverviewCard title="音频整轨" timeline={latestAudioTimeline} />
    </section>
  );
}

function TimelineOverviewCard({
  title,
  timeline,
}: {
  title: string;
  timeline: FlatTimeline | null;
}) {
  return (
    <article className="panel-card">
      <header className="card-header">
        <h3>{title}</h3>
        <span>
          {timeline ? `${timeline.items.length} 段 · gap ${timeline.gap_ms ?? 1000} ms` : "等待导入目录"}
        </span>
      </header>

      {!timeline ? (
        <div className="lane-note-card">
          <strong>还没有自动整轨。</strong>
          <span>先到“媒体导入”页导入视频目录和音频目录，系统会自动创建当前轨道。</span>
        </div>
      ) : (
        <div className="table-wrap table-wrap-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>顺序</th>
                <th>素材</th>
                <th>flat_start</th>
                <th>flat_end</th>
                <th>source_end</th>
              </tr>
            </thead>
            <tbody>
              {timeline.items.map((item, index) => (
                <tr key={item.id ?? `${timeline.flat_timeline_id}-${index}`}>
                  <td>{index + 1}</td>
                  <td>{item.filename ?? item.media_file_id}</td>
                  <td>{item.flat_start_ms}</td>
                  <td>{item.flat_end_ms}</td>
                  <td>{item.source_end_ms}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </article>
  );
}
