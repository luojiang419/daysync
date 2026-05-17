import type { RefObject } from "react";

type Props = {
  previewAvailable: boolean;
  videoSrc: string | null;
  audioPreviewEnabled: boolean;
  modeLabel: string;
  currentFlatTime: number;
  totalDurationMs: number;
  isPlaying: boolean;
  currentVideoSubtitle: string;
  currentAudioSubtitle: string;
  currentVideoFilename: string;
  currentAudioFilename: string;
  videoRef: RefObject<HTMLVideoElement | null>;
  audioRef: RefObject<HTMLAudioElement | null>;
  onTogglePlayback: () => void;
  onSeekRelative: (deltaMs: number) => void;
  onSeekToBoundary: (kind: "start" | "end") => void;
};
export function StudioPreviewPlayer({
  previewAvailable,
  videoSrc,
  audioPreviewEnabled,
  modeLabel,
  currentFlatTime,
  totalDurationMs,
  isPlaying,
  currentVideoSubtitle,
  currentAudioSubtitle,
  currentVideoFilename,
  currentAudioFilename,
  videoRef,
  audioRef,
  onTogglePlayback,
  onSeekRelative,
  onSeekToBoundary,
}: Props) {
  return (
    <section className="studio-player-panel">
      <header className="studio-section-header">
        <div>
          <h3>播放器</h3>
          <span>{modeLabel}</span>
        </div>
        <span>
          {formatTimecode(currentFlatTime)} / {formatTimecode(totalDurationMs)}
        </span>
      </header>

      <div className="studio-preview-stage">
        {previewAvailable && videoSrc ? (
          <video
            ref={videoRef}
            className="studio-preview-video"
            src={videoSrc}
            controls={false}
            playsInline
          />
        ) : (
          <div className="studio-preview-placeholder">
            <strong>当前环境不可直接预览本地媒体</strong>
            <span>请在 Tauri 桌面版中打开项目查看视频预览和外录音频联动。</span>
          </div>
        )}

        <div className="studio-preview-overlay">
          <div className="studio-overlay-line">
            <span>视频字幕</span>
            <strong>{currentVideoSubtitle || "当前无命中字幕"}</strong>
          </div>
          <div className="studio-overlay-line">
            <span>音频字幕</span>
            <strong>{currentAudioSubtitle || "当前无命中字幕"}</strong>
          </div>
          <div className="studio-overlay-meta">
            <span>视频文件：{currentVideoFilename || "-"}</span>
            <span>音频文件：{currentAudioFilename || "-"}</span>
          </div>
        </div>
      </div>

      <div className="studio-player-controls">
        <button type="button" className="secondary-button" onClick={() => onSeekToBoundary("start")}>
          回到开头
        </button>
        <button type="button" className="ghost-button" onClick={() => onSeekRelative(-5000)}>
          -5s
        </button>
        <button type="button" className="primary-button" onClick={onTogglePlayback} disabled={!previewAvailable || !videoSrc}>
          {isPlaying ? "暂停" : "播放"}
        </button>
        <button type="button" className="ghost-button" onClick={() => onSeekRelative(5000)}>
          +5s
        </button>
        <button type="button" className="secondary-button" onClick={() => onSeekToBoundary("end")}>
          跳到末尾
        </button>
        <span className={`studio-audio-indicator${audioPreviewEnabled ? " is-ready" : ""}`}>
          {audioPreviewEnabled ? "外录音频已联动" : "当前回退为视频参考音"}
        </span>
      </div>

      <audio ref={audioRef} hidden />
    </section>
  );
}

function formatTimecode(valueMs: number): string {
  const totalMs = Math.max(0, Math.round(valueMs));
  const hours = Math.floor(totalMs / 3_600_000);
  const minutes = Math.floor((totalMs % 3_600_000) / 60_000);
  const seconds = Math.floor((totalMs % 60_000) / 1000);
  const milliseconds = totalMs % 1000;
  return `${hours.toString().padStart(2, "0")}:${minutes
    .toString()
    .padStart(2, "0")}:${seconds.toString().padStart(2, "0")}.${Math.floor(
    milliseconds / 10,
  )
    .toString()
    .padStart(2, "0")}`;
}
