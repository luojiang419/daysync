import { type FormEvent, useEffect, useMemo, useState } from "react";

import {
  analyzeOffsetCluster,
  ApiError,
  createClusterCandidate,
  createManualSync,
  importSubtitles,
  listSyncResults,
  recommendAutoCandidates,
  saveProjectSettings,
  searchSubtitles,
} from "../api/client";
import type {
  AutoCandidate,
  AutoCandidateResponse,
  OffsetClusterAnalysisResponse,
  OffsetClusterSample,
  SearchResult,
} from "../api/types";
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
    | "video-import"
    | "audio-import"
    | "search"
    | "align"
    | "recommend"
    | "cluster"
    | "queue"
    | null
  >(null);
  const [recommendation, setRecommendation] = useState<AutoCandidateResponse | null>(null);
  const [recommendingFrom, setRecommendingFrom] = useState<"video_ref" | "external_audio" | null>(
    null,
  );
  const [clusterSamples, setClusterSamples] = useState<OffsetClusterSample[]>([]);
  const [clusterAnalysis, setClusterAnalysis] = useState<OffsetClusterAnalysisResponse | null>(null);
  const [isRestoringWorkspace, setIsRestoringWorkspace] = useState(false);
  const latestVideoTimeline = videoTimelines[videoTimelines.length - 1];
  const latestAudioTimeline = audioTimelines[audioTimelines.length - 1];
  const latestVideoTimelineId = latestVideoTimeline?.flat_timeline_id ?? latestVideoTimeline?.id ?? "";
  const latestAudioTimelineId = latestAudioTimeline?.flat_timeline_id ?? latestAudioTimeline?.id ?? "";

  useEffect(() => {
    if (!videoTimelineId && latestVideoTimelineId) {
      setVideoTimelineId(latestVideoTimelineId);
    }
  }, [latestVideoTimelineId, videoTimelineId]);

  useEffect(() => {
    if (!audioTimelineId && latestAudioTimelineId) {
      setAudioTimelineId(latestAudioTimelineId);
    }
  }, [audioTimelineId, latestAudioTimelineId]);

  useEffect(() => {
    if (!state.currentProject || !state.projectSettings) {
      return;
    }
    const workspace = state.projectSettings.subtitle_workspace;
    setIsRestoringWorkspace(true);
    setVideoTimelineId(
      latestVideoTimelineId ||
        workspace.video_timeline_id ||
        "",
    );
    setAudioTimelineId(
      latestAudioTimelineId ||
        workspace.audio_timeline_id ||
        "",
    );
    setVideoSrtPath(workspace.video_srt_path || "");
    setAudioSrtPath(workspace.audio_srt_path || "");
    setQuery(workspace.query || "");
    setClusterSamples(workspace.cluster_samples || []);
    setClusterAnalysis(null);
    const timeoutId = window.setTimeout(() => setIsRestoringWorkspace(false), 0);
    return () => window.clearTimeout(timeoutId);
  }, [latestAudioTimelineId, latestVideoTimelineId, state.currentProject?.id, state.projectSettings]);

  useEffect(() => {
    if (!state.currentProject || !state.projectSettings || isRestoringWorkspace) {
      return;
    }
    const timeoutId = window.setTimeout(async () => {
      try {
        await saveProjectSettings(state.currentProject!.id, {
          subtitle_workspace: {
            video_timeline_id: videoTimelineId,
            audio_timeline_id: audioTimelineId,
            video_srt_path: videoSrtPath,
            audio_srt_path: audioSrtPath,
            query,
            cluster_samples: clusterSamples,
          },
          export_workspace: state.projectSettings?.export_workspace ?? {},
        });
      } catch {
        // 项目恢复写回失败不打断当前工作流程。
      }
    }, 300);
    return () => window.clearTimeout(timeoutId);
  }, [
    audioSrtPath,
    audioTimelineId,
    clusterSamples,
    dispatch,
    isRestoringWorkspace,
    query,
    state.currentProject,
    state.projectSettings,
    videoSrtPath,
    videoTimelineId,
  ]);

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
      setClusterAnalysis(null);
      dispatch({ type: "SET_SEARCH_RESULTS", payload: results });
      dispatch({
        type: "SET_NOTICE",
        payload: { tone: "success", message: "字幕搜索已完成，请选择一组锚点后把结果批量应用到整轨。" },
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

  function handleAddCandidateClusterSample(candidate: AutoCandidate) {
    if (!recommendation) {
      return;
    }
    if (recommendation.target_track_type === "external_audio") {
      addClusterSample({
        video_subtitle_id: recommendation.anchor.subtitle_id,
        video_text: recommendation.anchor.raw_text,
        video_source_filename: recommendation.anchor.source_filename,
        audio_subtitle_id: candidate.subtitle_id,
        audio_text: candidate.raw_text,
        audio_source_filename: candidate.source_filename,
      });
      return;
    }

    addClusterSample({
      video_subtitle_id: candidate.subtitle_id,
      video_text: candidate.raw_text,
      video_source_filename: candidate.source_filename,
      audio_subtitle_id: recommendation.anchor.subtitle_id,
      audio_text: recommendation.anchor.raw_text,
      audio_source_filename: recommendation.anchor.source_filename,
    });
  }

  function handleAddCurrentSelectionSample() {
    const videoResult = findSearchResultById(state.searchResults, state.selectedVideoSubtitleId);
    const audioResult = findSearchResultById(state.searchResults, state.selectedAudioSubtitleId);
    if (!videoResult || !audioResult) {
      dispatch({
        type: "SET_NOTICE",
        payload: { tone: "error", message: "请先左右各选择一条字幕，再加入聚类样本。" },
      });
      return;
    }
    addClusterSample({
      video_subtitle_id: videoResult.subtitle_id,
      video_text: videoResult.raw_text,
      video_source_filename: videoResult.source_filename,
      audio_subtitle_id: audioResult.subtitle_id,
      audio_text: audioResult.raw_text,
      audio_source_filename: audioResult.source_filename,
    });
  }

  async function handleAnalyzeCluster() {
    if (!state.currentProject || !clusterSamples.length) {
      return;
    }
    setBusy("cluster");
    try {
      const result = await analyzeOffsetCluster(state.currentProject.id, {
        pairs: clusterSamples.map((sample) => ({
          video_subtitle_id: sample.video_subtitle_id,
          audio_subtitle_id: sample.audio_subtitle_id,
        })),
        tolerance_ms: 500,
        min_inlier_ratio: 0.6,
        min_anchor_count: 3,
        context_radius: 1,
      });
      setClusterAnalysis(result);
      dispatch({
        type: "SET_NOTICE",
        payload: {
          tone: result.cluster_summary.passes ? "success" : "neutral",
          message: result.cluster_summary.passes
            ? `聚类通过，建议 offset ${result.cluster_summary.final_offset_ms} ms。`
            : `聚类完成，但当前还未满足通过条件：${result.cluster_summary.reasons.join(", ") || "无"}`,
        },
      });
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "offset 聚类分析失败。";
      dispatch({ type: "SET_NOTICE", payload: { tone: "error", message } });
    } finally {
      setBusy(null);
    }
  }

  async function handleSaveClusterCandidate() {
    if (!state.currentProject || !clusterSamples.length) {
      return;
    }
    setBusy("queue");
    try {
      const result = await createClusterCandidate(state.currentProject.id, {
        pairs: clusterSamples.map((sample) => ({
          video_subtitle_id: sample.video_subtitle_id,
          audio_subtitle_id: sample.audio_subtitle_id,
        })),
        tolerance_ms: 500,
        min_inlier_ratio: 0.6,
        min_anchor_count: 3,
        context_radius: 1,
      });
      dispatch({
        type: "SET_NOTICE",
        payload: {
          tone: "success",
          message:
            result.sync_result.status === "accepted_auto"
              ? `候选已自动通过，offset ${result.sync_result.offset_ms} ms，并已进入最终结果。`
              : `候选已保存到复核队列，当前状态 ${result.sync_result.status}，建议 offset ${result.sync_result.offset_ms} ms。`,
        },
      });
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "保存复核候选失败。";
      dispatch({ type: "SET_NOTICE", payload: { tone: "error", message } });
    } finally {
      setBusy(null);
    }
  }

  function handleRemoveClusterSample(videoSubtitleId: string, audioSubtitleId: string) {
    setClusterSamples((current) =>
      current.filter(
        (sample) =>
          !(
            sample.video_subtitle_id === videoSubtitleId &&
            sample.audio_subtitle_id === audioSubtitleId
          ),
      ),
    );
    setClusterAnalysis(null);
  }

  function handleClearClusterSamples() {
    setClusterSamples([]);
    setClusterAnalysis(null);
  }

  function addClusterSample(sample: OffsetClusterSample) {
    const sampleKey = `${sample.video_subtitle_id}:${sample.audio_subtitle_id}`;
    setClusterSamples((current) => {
      if (
        current.some(
          (item) => `${item.video_subtitle_id}:${item.audio_subtitle_id}` === sampleKey,
        )
      ) {
        return current;
      }
      return [...current, sample];
    });
    setClusterAnalysis(null);
    dispatch({
      type: "SET_NOTICE",
      payload: { tone: "success", message: "已加入聚类样本，可以继续累积更多锚点对。" },
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
      const refreshed = await listSyncResults(state.currentProject.id);
      dispatch({ type: "SET_SYNC_RESULTS", payload: refreshed.sync_results });
      dispatch({
        type: "SET_NOTICE",
        payload: {
          tone: "success",
          message: `整轨对齐已保存，轨道 offset ${result.track_offset_ms} ms，本次共生成 ${result.generated_count} 条同步结果。`,
        },
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
          <span>同一关键词同时在视频整轨与音频整轨里检索，确定一组锚点后可批量作用到整轨</span>
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
          <AutoCandidatePanel
            recommendation={recommendation}
            onUseCandidate={handleUseCandidate}
            onAddClusterSample={handleAddCandidateClusterSample}
          />
        ) : null}

        <section className="cluster-analysis-panel">
          <header className="result-column-header">
            <div>
              <h3>多锚点 offset 聚类</h3>
              <span>收集多组视频/音频字幕对后，做正反向验证与聚类分析</span>
            </div>
            <span>{clusterSamples.length} 组样本</span>
          </header>

          <div className="button-row">
            <button
              type="button"
              className="ghost-button"
              disabled={!state.selectedVideoSubtitleId || !state.selectedAudioSubtitleId}
              onClick={handleAddCurrentSelectionSample}
            >
              将当前选择加入聚类样本
            </button>
            <button
              type="button"
              className="primary-button"
              disabled={!clusterSamples.length || busy === "cluster"}
              onClick={handleAnalyzeCluster}
            >
              {busy === "cluster" ? "分析中..." : "分析 offset 聚类"}
            </button>
            <button
              type="button"
              className="secondary-button"
              disabled={!clusterSamples.length || busy === "queue"}
              onClick={handleSaveClusterCandidate}
            >
              {busy === "queue" ? "生成中..." : "生成同步候选"}
            </button>
            <button
              type="button"
              className="ghost-button"
              disabled={!clusterSamples.length}
              onClick={handleClearClusterSamples}
            >
              清空样本
            </button>
          </div>

          <div className="cluster-sample-list">
            {clusterSamples.map((sample) => (
              <article
                key={`${sample.video_subtitle_id}:${sample.audio_subtitle_id}`}
                className="cluster-sample-card"
              >
                <div>
                  <strong>视频：</strong>
                  {sample.video_text}
                  <small> · {sample.video_source_filename ?? "未映射素材"}</small>
                </div>
                <div>
                  <strong>音频：</strong>
                  {sample.audio_text}
                  <small> · {sample.audio_source_filename ?? "未映射素材"}</small>
                </div>
                <button
                  type="button"
                  className="ghost-button"
                  onClick={() =>
                    handleRemoveClusterSample(sample.video_subtitle_id, sample.audio_subtitle_id)
                  }
                >
                  移除
                </button>
              </article>
            ))}
          </div>

          {clusterAnalysis ? (
            <div className="cluster-result-card">
              <div className="metrics-grid">
                <div className="metric-card">
                  <span>中位 offset</span>
                  <strong>{clusterAnalysis.cluster_summary.median_offset_ms}</strong>
                </div>
                <div className="metric-card">
                  <span>最终 offset</span>
                  <strong>
                    {clusterAnalysis.cluster_summary.final_offset_ms ?? "未通过"}
                  </strong>
                </div>
                <div className="metric-card">
                  <span>inlier ratio</span>
                  <strong>{Math.round(clusterAnalysis.cluster_summary.inlier_ratio * 100)}%</strong>
                </div>
              </div>

              <div className="candidate-context">
                <small>
                  通过：{clusterAnalysis.cluster_summary.passes ? "是" : "否"} · reverse 一致{" "}
                  {clusterAnalysis.cluster_summary.reverse_consistent_count}/
                  {clusterAnalysis.cluster_summary.candidate_count}
                </small>
                <small>
                  原因：{clusterAnalysis.cluster_summary.reasons.join(", ") || "无"}
                </small>
                <small>
                  自动通过预判：
                  {clusterAnalysis.auto_accept_decision.eligible
                    ? " 可自动通过"
                    : ` 需复核 (${clusterAnalysis.auto_accept_decision.reasons.join(", ") || "无"})`}
                </small>
              </div>

              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>视频字幕</th>
                      <th>音频字幕</th>
                      <th>offset</th>
                      <th>文本/上下文</th>
                      <th>正反向</th>
                      <th>deviation</th>
                      <th>inlier</th>
                    </tr>
                  </thead>
                  <tbody>
                    {clusterAnalysis.pair_analyses.map((analysis) => (
                      <tr
                        key={`${analysis.video_subtitle_id}:${analysis.audio_subtitle_id}`}
                      >
                        <td>{analysis.video_text}</td>
                        <td>{analysis.audio_text}</td>
                        <td>{analysis.offset_ms}</td>
                        <td>
                          {Math.round(analysis.text_similarity * 100)}% /{" "}
                          {Math.round(analysis.context_similarity * 100)}%
                        </td>
                        <td>
                          {analysis.reverse_match_consistent ? "一致" : "不一致"} · 分差{" "}
                          {Math.round(analysis.candidate_margin * 100)}
                        </td>
                        <td>{analysis.cluster_deviation_ms}</td>
                        <td>{analysis.is_inlier ? "是" : "否"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}
        </section>
      </article>
    </section>
  );
}

function findSearchResultById(
  searchResults: { video_results: SearchResult[]; audio_results: SearchResult[] } | null,
  subtitleId: string | null,
): SearchResult | null {
  if (!searchResults || !subtitleId) {
    return null;
  }
  const allResults = [...searchResults.video_results, ...searchResults.audio_results];
  return allResults.find((item) => item.subtitle_id === subtitleId) ?? null;
}
