import { useEffect, useMemo, useRef, useState } from "react";

import {
  ApiError,
  createManualSync,
  getStudioTimeline,
  importSubtitles,
  listSyncResults,
  searchSubtitles,
} from "../api/client";
import type {
  SearchResult,
  StudioMediaClip,
  StudioSubtitleCue,
  StudioSyncSegment,
  StudioTimelineSnapshot,
} from "../api/types";
import { StudioPreviewPlayer } from "../components/studio/StudioPreviewPlayer";
import { StudioTimelineCanvas } from "../components/studio/StudioTimelineCanvas";
import { chooseSubtitleFile, isTauriRuntime, toMediaAssetUrl } from "../api/tauri";
import { useAppState } from "../state/AppState";

type BusyState = "loading" | "video-import" | "audio-import" | "search" | "align" | null;
type SelectedAnchor = {
  subtitleId: string;
  rawText: string;
  trackType: "video_ref" | "external_audio";
  sourceFilename?: string | null;
  flatStartMs: number;
};

export function FlatTimelinePage() {
  const {
    state: { currentProject },
    dispatch,
  } = useAppState();
  const [studio, setStudio] = useState<StudioTimelineSnapshot | null>(null);
  const [busy, setBusy] = useState<BusyState>("loading");
  const [videoSrtPath, setVideoSrtPath] = useState("");
  const [audioSrtPath, setAudioSrtPath] = useState("");
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<{
    video_results: SearchResult[];
    audio_results: SearchResult[];
  } | null>(null);
  const [selectedVideoAnchor, setSelectedVideoAnchor] = useState<SelectedAnchor | null>(null);
  const [selectedAudioAnchor, setSelectedAudioAnchor] = useState<SelectedAnchor | null>(null);
  const [currentFlatTime, setCurrentFlatTime] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [zoomFactor, setZoomFactor] = useState(1);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const previewAvailable = isTauriRuntime();
  const totalDurationMs = useMemo(
    () =>
      Math.max(
        studio?.video_timeline?.total_duration_ms ?? 0,
        studio?.audio_timeline?.total_duration_ms ?? 0,
      ),
    [studio],
  );

  useEffect(() => {
    if (!currentProject) {
      setStudio(null);
      setBusy(null);
      setCurrentFlatTime(0);
      return;
    }
    void refreshStudioSnapshot();
  }, [currentProject?.id]);

  useEffect(() => {
    if (!isPlaying) {
      return;
    }
    if (totalDurationMs <= 0) {
      setIsPlaying(false);
      return;
    }
    const timer = window.setInterval(() => {
      setCurrentFlatTime((previous) => {
        const next = Math.min(previous + 100, totalDurationMs);
        if (next >= totalDurationMs) {
          window.setTimeout(() => setIsPlaying(false), 0);
        }
        return next;
      });
    }, 100);
    return () => window.clearInterval(timer);
  }, [isPlaying, totalDurationMs]);

  const currentVideoClip = useMemo(
    () => findClipAtFlatTime(studio?.video_clips ?? [], currentFlatTime),
    [currentFlatTime, studio?.video_clips],
  );
  const currentVideoCue = useMemo(
    () => findCueAtFlatTime(studio?.video_subtitles ?? [], currentFlatTime),
    [currentFlatTime, studio?.video_subtitles],
  );
  const currentSyncSegment = useMemo(
    () => findSyncSegmentAtFlatTime(studio?.sync_segments ?? [], currentFlatTime),
    [currentFlatTime, studio?.sync_segments],
  );
  const currentAudioFlatTime = useMemo(() => {
    if (!currentSyncSegment) {
      return null;
    }
    return (
      currentSyncSegment.audio_flat_start_ms +
      (currentFlatTime - currentSyncSegment.video_flat_start_ms)
    );
  }, [currentFlatTime, currentSyncSegment]);
  const currentAudioClip = useMemo(
    () =>
      currentAudioFlatTime === null
        ? null
        : findClipAtFlatTime(studio?.audio_clips ?? [], currentAudioFlatTime),
    [currentAudioFlatTime, studio?.audio_clips],
  );
  const currentAudioCue = useMemo(
    () =>
      currentAudioFlatTime === null
        ? null
        : findCueAtFlatTime(studio?.audio_subtitles ?? [], currentAudioFlatTime),
    [currentAudioFlatTime, studio?.audio_subtitles],
  );

  const videoSrc = toMediaAssetUrl(currentVideoClip?.original_path);
  const audioSrc = toMediaAssetUrl(currentAudioClip?.original_path);
  const audioPreviewEnabled =
    previewAvailable &&
    studio?.accepted_sync_summary.status === "ready" &&
    Boolean(currentSyncSegment && currentAudioClip && audioSrc);

  useEffect(() => {
    const videoElement = videoRef.current;
    if (!videoElement || !previewAvailable || !currentVideoClip || !videoSrc) {
      if (videoElement) {
        videoElement.pause();
      }
      return;
    }

    const targetSeconds =
      (currentVideoClip.source_start_ms + (currentFlatTime - currentVideoClip.flat_start_ms)) /
      1000;
    const shouldPlay = isPlaying;
    loadMediaElement(videoElement, videoSrc, currentVideoClip.media_file_id, targetSeconds, shouldPlay);
    videoElement.muted = audioPreviewEnabled;
    if (!shouldPlay) {
      videoElement.pause();
    }
  }, [
    audioPreviewEnabled,
    currentFlatTime,
    currentVideoClip,
    isPlaying,
    previewAvailable,
    videoSrc,
  ]);

  useEffect(() => {
    const audioElement = audioRef.current;
    if (!audioElement) {
      return;
    }
    if (!audioPreviewEnabled || !currentAudioClip || currentAudioFlatTime === null || !audioSrc) {
      audioElement.pause();
      return;
    }

    const targetSeconds =
      (currentAudioClip.source_start_ms +
        (currentAudioFlatTime - currentAudioClip.flat_start_ms)) /
      1000;
    loadMediaElement(audioElement, audioSrc, currentAudioClip.media_file_id, targetSeconds, isPlaying);
    if (!isPlaying) {
      audioElement.pause();
    }
  }, [
    audioPreviewEnabled,
    audioSrc,
    currentAudioClip,
    currentAudioFlatTime,
    isPlaying,
  ]);

  async function refreshStudioSnapshot() {
    if (!currentProject) {
      return;
    }
    setBusy("loading");
    try {
      const snapshot = await getStudioTimeline(currentProject.id);
      setStudio(snapshot);
      setCurrentFlatTime((previous) =>
        Math.min(previous, Math.max(snapshot.video_timeline?.total_duration_ms ?? 0, 0)),
      );
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "读取剪辑台快照失败。";
      dispatch({ type: "SET_NOTICE", payload: { tone: "error", message } });
    } finally {
      setBusy(null);
    }
  }

  async function pickSubtitlePath(kind: "video" | "audio") {
    const path = await chooseSubtitleFile();
    if (!path) {
      return;
    }
    if (kind === "video") {
      setVideoSrtPath(path);
      return;
    }
    setAudioSrtPath(path);
  }

  async function handleImportSubtitles(kind: "video" | "audio") {
    if (!currentProject || !studio) {
      return;
    }
    const timelineId =
      kind === "video" ? studio.video_timeline?.id ?? "" : studio.audio_timeline?.id ?? "";
    const path = kind === "video" ? videoSrtPath : audioSrtPath;
    if (!timelineId || !path) {
      return;
    }
    setBusy(kind === "video" ? "video-import" : "audio-import");
    try {
      const result = await importSubtitles(currentProject.id, {
        flat_timeline_id: timelineId,
        track_type: kind === "video" ? "video_ref" : "external_audio",
        source_type: "srt_import",
        path,
        language: "zh-CN",
      });
      await refreshStudioSnapshot();
      dispatch({
        type: "SET_NOTICE",
        payload: {
          tone: "success",
          message: `${kind === "video" ? "视频" : "音频"}字幕已导入，共 ${result.imported_count} 条。`,
        },
      });
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "导入字幕失败。";
      dispatch({ type: "SET_NOTICE", payload: { tone: "error", message } });
    } finally {
      setBusy(null);
    }
  }

  async function handleSearch() {
    if (!currentProject || !query.trim()) {
      return;
    }
    setBusy("search");
    try {
      const results = await searchSubtitles(currentProject.id, query.trim(), 12);
      setSearchResults(results);
      dispatch({
        type: "SET_NOTICE",
        payload: { tone: "success", message: "已完成快速搜索，请选择一组视频/音频字幕锚点。" },
      });
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "快速搜索失败。";
      dispatch({ type: "SET_NOTICE", payload: { tone: "error", message } });
    } finally {
      setBusy(null);
    }
  }

  function handleSelectSearchResult(result: SearchResult) {
    const anchor = {
      subtitleId: result.subtitle_id,
      rawText: result.raw_text,
      trackType: result.track_type,
      sourceFilename: result.source_filename,
      flatStartMs: result.flat_start_ms,
    } satisfies SelectedAnchor;
    if (result.track_type === "video_ref") {
      setSelectedVideoAnchor(anchor);
    } else {
      setSelectedAudioAnchor(anchor);
    }
    setCurrentFlatTime(result.flat_start_ms);
  }

  function handleSelectCue(cue: StudioSubtitleCue) {
    const anchor = {
      subtitleId: cue.subtitle_id,
      rawText: cue.raw_text,
      trackType: cue.track_type,
      sourceFilename: cue.source_filename,
      flatStartMs: cue.flat_start_ms,
    } satisfies SelectedAnchor;
    if (cue.track_type === "video_ref") {
      setSelectedVideoAnchor(anchor);
    } else {
      setSelectedAudioAnchor(anchor);
    }
    if (cue.track_type === "video_ref") {
      setCurrentFlatTime(cue.flat_start_ms);
    } else {
      const matchingSegment = findSyncSegmentByAudioFlatTime(studio?.sync_segments ?? [], cue.flat_start_ms);
      if (matchingSegment) {
        const mappedVideoFlatTime =
          matchingSegment.video_flat_start_ms +
          (cue.flat_start_ms - matchingSegment.audio_flat_start_ms);
        setCurrentFlatTime(mappedVideoFlatTime);
      }
    }
  }

  async function handleAlign() {
    if (!currentProject || !selectedVideoAnchor || !selectedAudioAnchor) {
      return;
    }
    setBusy("align");
    try {
      const result = await createManualSync(currentProject.id, {
        video_subtitle_id: selectedVideoAnchor.subtitleId,
        audio_subtitle_id: selectedAudioAnchor.subtitleId,
      });
      const syncResults = await listSyncResults(currentProject.id);
      dispatch({ type: "SET_SYNC_RESULTS", payload: syncResults.sync_results });
      await refreshStudioSnapshot();
      dispatch({
        type: "SET_NOTICE",
        payload: {
          tone: "success",
          message: `整轨一键对齐完成，轨道 offset ${result.track_offset_ms} ms，本次生成 ${result.generated_count} 条同步结果。`,
        },
      });
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "整轨对齐失败。";
      dispatch({ type: "SET_NOTICE", payload: { tone: "error", message } });
    } finally {
      setBusy(null);
    }
  }

  function handleSeek(targetMs: number) {
    setCurrentFlatTime(Math.max(0, Math.min(targetMs, totalDurationMs)));
  }

  function handleTogglePlayback() {
    if (!previewAvailable || !currentVideoClip) {
      return;
    }
    setIsPlaying((current) => !current);
  }

  function handleSeekRelative(deltaMs: number) {
    handleSeek(currentFlatTime + deltaMs);
  }

  function handleSeekToBoundary(kind: "start" | "end") {
    handleSeek(kind === "start" ? 0 : totalDurationMs);
  }

  function handleZoomFit() {
    setZoomFactor(1);
  }

  if (!currentProject) {
    return (
      <section className="studio-empty-state">
        <strong>请先创建或打开项目</strong>
        <span>剪辑台需要先绑定一个 DaySync 项目，才能读取整轨、字幕和同步状态。</span>
      </section>
    );
  }

  return (
    <section className="studio-shell">
      <aside className="studio-sidebar">
        <section className="studio-side-card">
          <header className="studio-section-header">
            <div>
              <h3>整轨摘要</h3>
              <span>{busy === "loading" ? "刷新中..." : "最新自动整轨"}</span>
            </div>
          </header>
          <div className="studio-kv-list">
            <div>
              <span>视频整轨</span>
              <strong>{studio?.video_timeline ? `${studio.video_clips.length} 段素材` : "未生成"}</strong>
            </div>
            <div>
              <span>音频整轨</span>
              <strong>{studio?.audio_timeline ? `${studio.audio_clips.length} 段素材` : "未生成"}</strong>
            </div>
            <div>
              <span>当前同步</span>
              <strong>
                {studio?.accepted_sync_summary.status === "ready"
                  ? `已建立 ${studio.accepted_sync_summary.accepted_count} 段`
                  : "尚未建立"}
              </strong>
            </div>
          </div>
        </section>

        <section className="studio-side-card">
          <header className="studio-section-header">
            <div>
              <h3>字幕加载</h3>
              <span>沿用当前整轨导入字幕</span>
            </div>
          </header>
          <div className="form-stack">
            <label>
              <span>视频字幕路径</span>
              <div className="inline-field">
                <input value={videoSrtPath} onChange={(event) => setVideoSrtPath(event.target.value)} />
                <button type="button" className="ghost-button" onClick={() => pickSubtitlePath("video")}>
                  选择文件
                </button>
              </div>
            </label>
            <button
              type="button"
              className="secondary-button"
              disabled={!studio?.video_timeline?.id || !videoSrtPath || busy === "video-import"}
              onClick={() => handleImportSubtitles("video")}
            >
              {busy === "video-import" ? "导入中..." : "加载视频字幕"}
            </button>
            <label>
              <span>音频字幕路径</span>
              <div className="inline-field">
                <input value={audioSrtPath} onChange={(event) => setAudioSrtPath(event.target.value)} />
                <button type="button" className="ghost-button" onClick={() => pickSubtitlePath("audio")}>
                  选择文件
                </button>
              </div>
            </label>
            <button
              type="button"
              className="secondary-button"
              disabled={!studio?.audio_timeline?.id || !audioSrtPath || busy === "audio-import"}
              onClick={() => handleImportSubtitles("audio")}
            >
              {busy === "audio-import" ? "导入中..." : "加载音频字幕"}
            </button>
          </div>
        </section>

        <section className="studio-side-card">
          <header className="studio-section-header">
            <div>
              <h3>快速搜索</h3>
              <span>选择一组字幕锚点后直接整轨对齐</span>
            </div>
          </header>
          <div className="studio-search-box">
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="输入一句字幕，例如：我们到了这里"
            />
            <button
              type="button"
              className="primary-button"
              disabled={!query.trim() || busy === "search"}
              onClick={handleSearch}
            >
              {busy === "search" ? "搜索中..." : "搜索字幕"}
            </button>
          </div>
          <div className="studio-anchor-grid">
            <div className="studio-anchor-card">
              <span>视频锚点</span>
              <strong>{selectedVideoAnchor?.rawText ?? "未选择"}</strong>
              <small>{selectedVideoAnchor?.sourceFilename ?? "请从视频字幕轨或搜索结果中选择"}</small>
            </div>
            <div className="studio-anchor-card">
              <span>音频锚点</span>
              <strong>{selectedAudioAnchor?.rawText ?? "未选择"}</strong>
              <small>{selectedAudioAnchor?.sourceFilename ?? "请从音频字幕轨或搜索结果中选择"}</small>
            </div>
          </div>
          <button
            type="button"
            className="primary-button"
            disabled={!selectedVideoAnchor || !selectedAudioAnchor || busy === "align"}
            onClick={handleAlign}
          >
            {busy === "align" ? "对齐中..." : "整轨一键对齐"}
          </button>

          {searchResults ? (
            <div className="studio-search-results">
              <SearchResultColumn
                title="视频命中"
                results={searchResults.video_results}
                selectedId={selectedVideoAnchor?.subtitleId ?? null}
                onSelect={handleSelectSearchResult}
              />
              <SearchResultColumn
                title="音频命中"
                results={searchResults.audio_results}
                selectedId={selectedAudioAnchor?.subtitleId ?? null}
                onSelect={handleSelectSearchResult}
              />
            </div>
          ) : null}
        </section>
      </aside>

      <div className="studio-main">
        <StudioPreviewPlayer
          previewAvailable={previewAvailable}
          videoSrc={videoSrc}
          audioPreviewEnabled={audioPreviewEnabled}
          modeLabel={
            audioPreviewEnabled
              ? "外录音频联动预览"
              : previewAvailable
                ? "视频参考音预览"
                : "仅桌面版支持本地媒体预览"
          }
          currentFlatTime={currentFlatTime}
          totalDurationMs={totalDurationMs}
          isPlaying={isPlaying}
          currentVideoSubtitle={currentVideoCue?.raw_text ?? ""}
          currentAudioSubtitle={audioPreviewEnabled ? currentAudioCue?.raw_text ?? "" : ""}
          currentVideoFilename={currentVideoClip?.filename ?? ""}
          currentAudioFilename={audioPreviewEnabled ? currentAudioClip?.filename ?? "" : ""}
          videoRef={videoRef}
          audioRef={audioRef}
          onTogglePlayback={handleTogglePlayback}
          onSeekRelative={handleSeekRelative}
          onSeekToBoundary={handleSeekToBoundary}
        />

        <section className="studio-inspector">
          <header className="studio-section-header">
            <div>
              <h3>当前检查器</h3>
              <span>随播放头和当前片段实时联动</span>
            </div>
          </header>
          <div className="studio-kv-list">
            <div>
              <span>视频文件</span>
              <strong>{currentVideoClip?.filename ?? "-"}</strong>
            </div>
            <div>
              <span>音频文件</span>
              <strong>{audioPreviewEnabled ? currentAudioClip?.filename ?? "-" : "未建立同步"}</strong>
            </div>
            <div>
              <span>视频字幕</span>
              <strong>{currentVideoCue?.raw_text ?? "-"}</strong>
            </div>
            <div>
              <span>音频字幕</span>
              <strong>{audioPreviewEnabled ? currentAudioCue?.raw_text ?? "-" : "未建立同步"}</strong>
            </div>
            <div>
              <span>同步状态</span>
              <strong>
                {studio?.accepted_sync_summary.status === "ready"
                  ? `已建立 ${studio.accepted_sync_summary.accepted_count} 段 accepted 结果`
                  : "尚未建立外录音频预览同步"}
              </strong>
            </div>
            <div>
              <span>中位 offset</span>
              <strong>{studio?.accepted_sync_summary.median_offset_ms ?? "-"}</strong>
            </div>
          </div>
        </section>

        <StudioTimelineCanvas
          totalDurationMs={totalDurationMs}
          currentFlatTime={currentFlatTime}
          zoomFactor={zoomFactor}
          videoClips={studio?.video_clips ?? []}
          audioClips={studio?.audio_clips ?? []}
          videoSubtitles={studio?.video_subtitles ?? []}
          audioSubtitles={studio?.audio_subtitles ?? []}
          selectedVideoSubtitleId={selectedVideoAnchor?.subtitleId ?? null}
          selectedAudioSubtitleId={selectedAudioAnchor?.subtitleId ?? null}
          onSeek={handleSeek}
          onSelectCue={handleSelectCue}
          onZoomIn={() => setZoomFactor((current) => Math.min(current * 1.25, 6))}
          onZoomOut={() => setZoomFactor((current) => Math.max(current * 0.8, 1))}
          onZoomFit={handleZoomFit}
        />
      </div>
    </section>
  );
}

function SearchResultColumn({
  title,
  results,
  selectedId,
  onSelect,
}: {
  title: string;
  results: SearchResult[];
  selectedId: string | null;
  onSelect: (result: SearchResult) => void;
}) {
  return (
    <section className="studio-search-column">
      <header className="studio-section-header">
        <div>
          <h3>{title}</h3>
          <span>{results.length} 条</span>
        </div>
      </header>
      <div className="studio-search-list">
        {results.map((result) => (
          <button
            key={result.subtitle_id}
            type="button"
            className={`studio-search-result${selectedId === result.subtitle_id ? " is-selected" : ""}`}
            onClick={() => onSelect(result)}
          >
            <strong>{result.raw_text}</strong>
            <small>{result.source_filename ?? "未映射素材"}</small>
          </button>
        ))}
        {!results.length ? <span className="status-meta">暂无命中</span> : null}
      </div>
    </section>
  );
}

function findClipAtFlatTime(
  clips: StudioMediaClip[],
  flatTimeMs: number,
): StudioMediaClip | null {
  return (
    clips.find((clip) => clip.flat_start_ms <= flatTimeMs && flatTimeMs < clip.flat_end_ms) ??
    null
  );
}

function findCueAtFlatTime(
  cues: StudioSubtitleCue[],
  flatTimeMs: number,
): StudioSubtitleCue | null {
  return (
    cues.find((cue) => cue.flat_start_ms <= flatTimeMs && flatTimeMs < cue.flat_end_ms) ?? null
  );
}

function findSyncSegmentAtFlatTime(
  segments: StudioSyncSegment[],
  flatTimeMs: number,
): StudioSyncSegment | null {
  return (
    segments.find(
      (segment) =>
        segment.video_flat_start_ms <= flatTimeMs && flatTimeMs < segment.video_flat_end_ms,
    ) ?? null
  );
}

function findSyncSegmentByAudioFlatTime(
  segments: StudioSyncSegment[],
  audioFlatTimeMs: number,
): StudioSyncSegment | null {
  return (
    segments.find(
      (segment) =>
        segment.audio_flat_start_ms <= audioFlatTimeMs && audioFlatTimeMs < segment.audio_flat_end_ms,
    ) ?? null
  );
}

function loadMediaElement(
  element: HTMLMediaElement,
  src: string,
  mediaId: string,
  targetSeconds: number,
  shouldPlay: boolean,
) {
  const currentMediaId = element.dataset.mediaId;
  if (currentMediaId !== mediaId || element.currentSrc !== src) {
    element.pause();
    element.dataset.mediaId = mediaId;
    element.src = src;
    const handleLoaded = () => {
      element.currentTime = Math.max(targetSeconds, 0);
      if (shouldPlay) {
        void element.play().catch(() => undefined);
      }
      element.removeEventListener("loadedmetadata", handleLoaded);
    };
    element.addEventListener("loadedmetadata", handleLoaded);
    element.load();
    return;
  }

  if (Number.isFinite(targetSeconds) && Math.abs(element.currentTime - targetSeconds) > 0.35) {
    element.currentTime = Math.max(targetSeconds, 0);
  }
  if (shouldPlay && element.paused) {
    void element.play().catch(() => undefined);
  }
}
