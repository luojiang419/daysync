import { useEffect, useMemo, useRef, useState } from "react";

import type { StudioMediaClip, StudioSubtitleCue } from "../../api/types";

type Props = {
  totalDurationMs: number;
  currentFlatTime: number;
  zoomFactor: number;
  videoClips: StudioMediaClip[];
  audioClips: StudioMediaClip[];
  videoSubtitles: StudioSubtitleCue[];
  audioSubtitles: StudioSubtitleCue[];
  selectedVideoSubtitleId: string | null;
  selectedAudioSubtitleId: string | null;
  onSeek: (flatTimeMs: number) => void;
  onSelectCue: (cue: StudioSubtitleCue) => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onZoomFit: () => void;
};

const LABEL_WIDTH = 84;

export function StudioTimelineCanvas({
  totalDurationMs,
  currentFlatTime,
  zoomFactor,
  videoClips,
  audioClips,
  videoSubtitles,
  audioSubtitles,
  selectedVideoSubtitleId,
  selectedAudioSubtitleId,
  onSeek,
  onSelectCue,
  onZoomIn,
  onZoomOut,
  onZoomFit,
}: Props) {
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const [viewportWidth, setViewportWidth] = useState(960);

  useEffect(() => {
    if (!viewportRef.current) {
      return;
    }
    const element = viewportRef.current;
    const observer = new ResizeObserver((entries) => {
      const nextWidth = entries[0]?.contentRect.width;
      if (nextWidth) {
        setViewportWidth(nextWidth);
      }
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const pixelsPerMs = useMemo(() => {
    if (totalDurationMs <= 0) {
      return 0.05;
    }
    const fitPixelsPerMs = Math.max((viewportWidth - 32) / totalDurationMs, 0.02);
    return fitPixelsPerMs * zoomFactor;
  }, [totalDurationMs, viewportWidth, zoomFactor]);

  const timelineWidth = Math.max(viewportWidth - 16, totalDurationMs * pixelsPerMs);
  const rulerTicks = useMemo(() => buildRulerTicks(totalDurationMs), [totalDurationMs]);

  function handleSeekByPointer(clientX: number) {
    if (!viewportRef.current) {
      return;
    }
    const rect = viewportRef.current.getBoundingClientRect();
    const scrollLeft = viewportRef.current.scrollLeft;
    const offsetX = clientX - rect.left + scrollLeft;
    const flatTimeMs = Math.max(0, Math.min(totalDurationMs, offsetX / pixelsPerMs));
    onSeek(flatTimeMs);
  }

  return (
    <section className="studio-timeline-panel">
      <header className="studio-section-header">
        <div>
          <h3>时间线轨道</h3>
          <span>点击片段或字幕块跳转播放头；当前为只读预览模式</span>
        </div>
        <div className="studio-timeline-tools">
          <button type="button" className="ghost-button" onClick={onZoomOut}>
            缩小
          </button>
          <button type="button" className="ghost-button" onClick={onZoomFit}>
            适配
          </button>
          <button type="button" className="ghost-button" onClick={onZoomIn}>
            放大
          </button>
        </div>
      </header>

      <div className="studio-timeline-shell">
        <div className="studio-track-labels">
          <div className="studio-ruler-label">时间</div>
          <div className="studio-track-label">V1</div>
          <div className="studio-track-label">S1</div>
          <div className="studio-track-label">A1</div>
          <div className="studio-track-label">S2</div>
        </div>

        <div
          ref={viewportRef}
          className="studio-timeline-viewport"
          onClick={(event) => handleSeekByPointer(event.clientX)}
        >
          <div className="studio-timeline-content" style={{ width: timelineWidth }}>
            <div className="studio-time-ruler">
              {rulerTicks.map((tick) => (
                <div
                  key={tick}
                  className="studio-ruler-tick"
                  style={{ left: tick * pixelsPerMs }}
                >
                  <span>{formatRulerTime(tick)}</span>
                </div>
              ))}
            </div>

            <TimelineLane
              clips={videoClips}
              pixelsPerMs={pixelsPerMs}
              currentFlatTime={currentFlatTime}
              tone="video"
              onSeek={onSeek}
            />
            <SubtitleLane
              cues={videoSubtitles}
              pixelsPerMs={pixelsPerMs}
              currentFlatTime={currentFlatTime}
              selectedCueId={selectedVideoSubtitleId}
              tone="video-subtitle"
              onSelectCue={onSelectCue}
            />
            <TimelineLane
              clips={audioClips}
              pixelsPerMs={pixelsPerMs}
              currentFlatTime={currentFlatTime}
              tone="audio"
              onSeek={onSeek}
            />
            <SubtitleLane
              cues={audioSubtitles}
              pixelsPerMs={pixelsPerMs}
              currentFlatTime={currentFlatTime}
              selectedCueId={selectedAudioSubtitleId}
              tone="audio-subtitle"
              onSelectCue={onSelectCue}
            />

            <div
              className="studio-playhead"
              style={{ left: LABEL_WIDTH + currentFlatTime * pixelsPerMs }}
            />
          </div>
        </div>
      </div>
    </section>
  );
}

function TimelineLane({
  clips,
  pixelsPerMs,
  currentFlatTime,
  tone,
  onSeek,
}: {
  clips: StudioMediaClip[];
  pixelsPerMs: number;
  currentFlatTime: number;
  tone: "video" | "audio";
  onSeek: (flatTimeMs: number) => void;
}) {
  return (
    <div className={`studio-track-lane is-${tone}`}>
      <div className="studio-track-lane-inner">
        {clips.map((clip) => {
          const active = clip.flat_start_ms <= currentFlatTime && currentFlatTime < clip.flat_end_ms;
          return (
            <button
              key={clip.id}
              type="button"
              className={`studio-clip-block${active ? " is-active" : ""}`}
              style={{
                left: clip.flat_start_ms * pixelsPerMs,
                width: Math.max((clip.flat_end_ms - clip.flat_start_ms) * pixelsPerMs, 18),
              }}
              onClick={(event) => {
                event.stopPropagation();
                onSeek(clip.flat_start_ms);
              }}
            >
              <strong>{clip.filename}</strong>
              <small>
                {formatRulerTime(clip.flat_start_ms)} - {formatRulerTime(clip.flat_end_ms)}
              </small>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function SubtitleLane({
  cues,
  pixelsPerMs,
  currentFlatTime,
  selectedCueId,
  tone,
  onSelectCue,
}: {
  cues: StudioSubtitleCue[];
  pixelsPerMs: number;
  currentFlatTime: number;
  selectedCueId: string | null;
  tone: "video-subtitle" | "audio-subtitle";
  onSelectCue: (cue: StudioSubtitleCue) => void;
}) {
  return (
    <div className={`studio-track-lane is-${tone}`}>
      <div className="studio-track-lane-inner">
        {cues.map((cue) => {
          const active = cue.flat_start_ms <= currentFlatTime && currentFlatTime < cue.flat_end_ms;
          const selected = cue.subtitle_id === selectedCueId;
          return (
            <button
              key={cue.subtitle_id}
              type="button"
              className={`studio-subtitle-block${active ? " is-active" : ""}${selected ? " is-selected" : ""}`}
              style={{
                left: cue.flat_start_ms * pixelsPerMs,
                width: Math.max((cue.flat_end_ms - cue.flat_start_ms) * pixelsPerMs, 20),
              }}
              onClick={(event) => {
                event.stopPropagation();
                onSelectCue(cue);
              }}
            >
              {cue.raw_text}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function buildRulerTicks(totalDurationMs: number): number[] {
  if (totalDurationMs <= 0) {
    return [0];
  }
  const stepMs =
    totalDurationMs > 1_800_000
      ? 120_000
      : totalDurationMs > 600_000
        ? 60_000
        : totalDurationMs > 180_000
          ? 30_000
          : totalDurationMs > 60_000
            ? 10_000
            : 5_000;
  const ticks: number[] = [];
  for (let value = 0; value <= totalDurationMs; value += stepMs) {
    ticks.push(value);
  }
  if (ticks[ticks.length - 1] !== totalDurationMs) {
    ticks.push(totalDurationMs);
  }
  return ticks;
}

function formatRulerTime(valueMs: number): string {
  const totalSeconds = Math.max(0, Math.floor(valueMs / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return `${hours.toString().padStart(2, "0")}:${minutes
    .toString()
    .padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
}
