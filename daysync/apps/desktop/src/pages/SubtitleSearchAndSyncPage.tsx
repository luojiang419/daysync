import { type FormEvent, useEffect, useMemo, useState } from "react";

import {
  ApiError,
  createManualSync,
  importSubtitles,
  recommendAutoCandidates,
  searchSubtitles,
} from "../api/client";
import type { AutoCandidate, AutoCandidateResponse } from "../api/types";
import { AutoCandidatePanel } from "../components/AutoCandidatePanel";
import { chooseSubtitleFile } from "../api/tauri";
import { SubtitleMatchBoard } from "../components/SubtitleMatchBoard";
import { useAppState } from "../state/AppState";

export function SubtitleSearchAndSyncPage() {
  const { state, dispatch } = useAppState();
  const videoTimelines = useMemo(
    () => state.flatTimelines.filter((timeline) => timeline.media_type === "video"),
    [state.flatTimelines],
  );
  const audioTimelines = useMemo(
    () => state.flatTimelines.filter((timeline) => timeline.media_type === "audio"),
    [state.flatTimelines],
  );

  const [videoTimelineId, setVideoTimelineId] = useState("");
  const [audioTimelineId, setAudioTimelineId] = useState("");
  const [videoSrtPath, setVideoSrtPath] = useState("");
  const [audioSrtPath, setAudioSrtPath] = useState("");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState<
    "video-import" | "audio-import" | "search" | "align" | "recommend" | null
  >(null);
  const [recommendation, setRecommendation] = useState<AutoCandidateResponse | null>(null);
  const [recommendingFrom, setRecommendingFrom] = useState<"video_ref" | "external_audio" | null>(
    null,
  );

  useEffect(() => {
    if (!videoTimelineId && videoTimelines[0]) {
      setVideoTimelineId(videoTimelines[0].flat_timeline_id ?? videoTimelines[0].id ?? "");
    }
  }, [videoTimelineId, videoTimelines]);

  useEffect(() => {
    if (!audioTimelineId && audioTimelines[0]) {
      setAudioTimelineId(audioTimelines[0].flat_timeline_id ?? audioTimelines[0].id ?? "");
    }
  }, [audioTimelineId, audioTimelines]);

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

  async function handleImport(kind: "video" | "audio") {
    if (!state.currentProject) {
      dispatch({
        type: "SET_NOTICE",
        payload: { tone: "error", message: "请先创建或打开项目。" },
      });
      return;
    }

    const timelineId = kind === "video" ? videoTimelineId : audioTimelineId;
    const path = kind === "video" ? videoSrtPath : audioSrtPath;
    setBusy(kind === "video" ? "video-import" : "audio-import");
    try {
      const result = await importSubtitles(state.currentProject.id, {
        flat_timeline_id: timelineId,
        track_type: kind === "video" ? "video_ref" : "external_audio",
        source_type: "srt_import",
        path,
        language: "zh-CN",
      });
      dispatch({
        type: "SET_NOTICE",
        payload: {
          tone: "success",
          message: `${kind === "video" ? "视频" : "音频"}字幕已导入，共 ${result.imported_count} 条，warning ${result.warning_count} 条。`,
        },
      });
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "导入字幕失败。";
      dispatch({ type: "SET_NOTICE", payload: { tone: "error", message } });
    } finally {
      setBusy(null);
    }
  }

  async function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!state.currentProject) {
      return;
    }
    setBusy("search");
    try {
      const results = await searchSubtitles(state.currentProject.id, query, 20);
      setRecommendation(null);
      dispatch({ type: "SET_SEARCH_RESULTS", payload: results });
      dispatch({
        type: "SET_NOTICE",
        payload: { tone: "success", message: "字幕搜索已完成，请左右各选择一条锚点。" },
      });
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "搜索字幕失败。";
      dispatch({ type: "SET_NOTICE", payload: { tone: "error", message } });
    } finally {
      setBusy(null);
    }
  }

  async function handleRecommend(anchorSubtitleId: string) {
    if (!state.currentProject) {
      return;
    }
    const anchorTrackType =
      state.selectedVideoSubtitleId === anchorSubtitleId ? "video_ref" : "external_audio";
    setBusy("recommend");
    setRecommendingFrom(anchorTrackType);
    try {
      const result = await recommendAutoCandidates(state.currentProject.id, {
        anchor_subtitle_id: anchorSubtitleId,
        limit: 5,
        context_radius: 1,
      });
      setRecommendation(result);
      dispatch({
        type: "SET_NOTICE",
        payload: { tone: "success", message: "已生成自动候选，请选择更合适的一条。" },
      });
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "生成自动候选失败。";
      dispatch({ type: "SET_NOTICE", payload: { tone: "error", message } });
    } finally {
      setBusy(null);
      setRecommendingFrom(null);
    }
  }

  function handleUseCandidate(candidate: AutoCandidate) {
    const currentResults = state.searchResults;
    const currentVideoSelection = state.selectedVideoSubtitleId;
    const currentAudioSelection = state.selectedAudioSubtitleId;
    if (currentResults) {
      const listKey: "audio_results" | "video_results" =
        recommendation?.target_track_type === "external_audio" ? "audio_results" : "video_results";
      const candidateAsSearchResult = {
        subtitle_id: candidate.subtitle_id,
        track_type: candidate.track_type,
        raw_text: candidate.raw_text,
        normalized_text: candidate.normalized_text,
        source_media_file_id: candidate.source_media_file_id,
        source_start_ms: candidate.source_start_ms,
        source_end_ms: candidate.source_end_ms,
        flat_start_ms: candidate.flat_start_ms,
        flat_end_ms: candidate.flat_end_ms,
        relevance_score: candidate.final_score,
        source_filename: candidate.source_filename,
      };
      const targetList = currentResults[listKey];
      const mergedList = targetList.some((item) => item.subtitle_id === candidate.subtitle_id)
        ? targetList
        : [candidateAsSearchResult, ...targetList];
      dispatch({
        type: "SET_SEARCH_RESULTS",
        payload: { ...currentResults, [listKey]: mergedList },
      });
    }

    if (recommendation?.target_track_type === "external_audio") {
      dispatch({ type: "SELECT_VIDEO_SUBTITLE", payload: currentVideoSelection });
      dispatch({ type: "SELECT_AUDIO_SUBTITLE", payload: candidate.subtitle_id });
    } else {
      dispatch({ type: "SELECT_AUDIO_SUBTITLE", payload: currentAudioSelection });
      dispatch({ type: "SELECT_VIDEO_SUBTITLE", payload: candidate.subtitle_id });
    }

    dispatch({
      type: "SET_NOTICE",
      payload: { tone: "success", message: "候选已应用，现在可以直接点击一键对齐。" },
    });
  }

  async function handleAlign() {
    if (!state.currentProject || !state.selectedVideoSubtitleId || !state.selectedAudioSubtitleId) {
      return;
    }
    setBusy("align");
    try {
      const result = await createManualSync(state.currentProject.id, {
        video_subtitle_id: state.selectedVideoSubtitleId,
        audio_subtitle_id: state.selectedAudioSubtitleId,
      });
      dispatch({ type: "ADD_SYNC_RESULT", payload: result.sync_result });
      dispatch({
        type: "SET_NOTICE",
        payload: { tone: "success", message: `手动同步已保存，offset ${result.sync_result.offset_ms} ms。` },
      });
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "手动同步失败。";
      dispatch({ type: "SET_NOTICE", payload: { tone: "error", message } });
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="page-grid">
      <article className="panel-card">
        <header className="card-header">
          <h2>导入视频字幕</h2>
          <span>选择视频 flat timeline 与 `video_flat.srt`</span>
        </header>
        <div className="form-stack">
          <label>
            <span>视频时间线</span>
            <select value={videoTimelineId} onChange={(event) => setVideoTimelineId(event.target.value)}>
              <option value="">请选择</option>
              {videoTimelines.map((timeline, index) => (
                <option
                  key={timeline.flat_timeline_id ?? timeline.id ?? index}
                  value={timeline.flat_timeline_id ?? timeline.id ?? ""}
                >
                  {timeline.name ?? `video_${index + 1}`}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>SRT 路径</span>
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
            disabled={!videoTimelineId || !videoSrtPath || busy === "video-import"}
            onClick={() => handleImport("video")}
          >
            {busy === "video-import" ? "导入中..." : "导入视频字幕"}
          </button>
        </div>
      </article>

      <article className="panel-card">
        <header className="card-header">
          <h2>导入音频字幕</h2>
          <span>选择音频 flat timeline 与 `audio_flat.srt`</span>
        </header>
        <div className="form-stack">
          <label>
            <span>音频时间线</span>
            <select value={audioTimelineId} onChange={(event) => setAudioTimelineId(event.target.value)}>
              <option value="">请选择</option>
              {audioTimelines.map((timeline, index) => (
                <option
                  key={timeline.flat_timeline_id ?? timeline.id ?? index}
                  value={timeline.flat_timeline_id ?? timeline.id ?? ""}
                >
                  {timeline.name ?? `audio_${index + 1}`}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>SRT 路径</span>
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
            disabled={!audioTimelineId || !audioSrtPath || busy === "audio-import"}
            onClick={() => handleImport("audio")}
          >
            {busy === "audio-import" ? "导入中..." : "导入音频字幕"}
          </button>
        </div>
      </article>

      <article className="panel-card span-two">
        <header className="card-header">
          <h2>统一字幕搜索</h2>
          <span>同一关键词同时在视频轨与外录音轨里检索</span>
        </header>
        <form className="inline-form" onSubmit={handleSearch}>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="输入一句字幕，例如：我们到了这里"
          />
          <button type="submit" className="primary-button" disabled={!query || busy === "search"}>
            {busy === "search" ? "搜索中..." : "开始搜索"}
          </button>
        </form>

        <div className="button-row">
          <button
            type="button"
            className="ghost-button"
            disabled={!state.selectedVideoSubtitleId || busy === "recommend"}
            onClick={() =>
              state.selectedVideoSubtitleId && handleRecommend(state.selectedVideoSubtitleId)
            }
          >
            {busy === "recommend" && recommendingFrom === "video_ref"
              ? "推荐中..."
              : "根据视频锚点推荐音频候选"}
          </button>
          <button
            type="button"
            className="ghost-button"
            disabled={!state.selectedAudioSubtitleId || busy === "recommend"}
            onClick={() =>
              state.selectedAudioSubtitleId && handleRecommend(state.selectedAudioSubtitleId)
            }
          >
            {busy === "recommend" && recommendingFrom === "external_audio"
              ? "推荐中..."
              : "根据音频锚点推荐视频候选"}
          </button>
        </div>

        <SubtitleMatchBoard
          videoResults={state.searchResults?.video_results ?? []}
          audioResults={state.searchResults?.audio_results ?? []}
          selectedVideoSubtitleId={state.selectedVideoSubtitleId}
          selectedAudioSubtitleId={state.selectedAudioSubtitleId}
          isAligning={busy === "align"}
          lastOffsetMs={state.lastOffsetMs}
          onSelectVideo={(subtitleId) =>
            dispatch({ type: "SELECT_VIDEO_SUBTITLE", payload: subtitleId })
          }
          onSelectAudio={(subtitleId) =>
            dispatch({ type: "SELECT_AUDIO_SUBTITLE", payload: subtitleId })
          }
          onAlign={handleAlign}
        />

        {recommendation ? (
          <AutoCandidatePanel recommendation={recommendation} onUseCandidate={handleUseCandidate} />
        ) : null}
      </article>
    </section>
  );
}
