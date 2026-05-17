import { type FormEvent, useEffect, useMemo, useState } from "react";

import {
  ApiError,
  exportCsv,
  exportFcp7Xml,
  listReviewQueue,
  listSyncResults,
  reviewSyncResult,
  saveProjectSettings,
} from "../api/client";
import type { ReviewQueueItem, SyncResult } from "../api/types";
import { ReviewQueueCard } from "../components/ReviewQueueCard";
import { SyncResultCard } from "../components/SyncResultCard";
import { chooseDirectory } from "../api/tauri";
import { useAppState } from "../state/AppState";

export function ExportPage() {
  const { state, dispatch } = useAppState();
  const [outputPath, setOutputPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [reviewQueue, setReviewQueue] = useState<ReviewQueueItem[]>([]);
  const [reviewBusyId, setReviewBusyId] = useState<string | null>(null);
  const [adjustOffsets, setAdjustOffsets] = useState<Record<string, string>>({});
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});
  const [statusFilter, setStatusFilter] = useState<
    "all" | "accepted_manual" | "accepted_auto" | "needs_review" | "rejected"
  >("all");
  const [sourceFilter, setSourceFilter] = useState<"all" | "manual_anchor" | "auto_text">("all");
  const [minConfidenceFilter, setMinConfidenceFilter] = useState("0");
  const [isRestoringWorkspace, setIsRestoringWorkspace] = useState(false);

  const filteredSyncResults = useMemo(() => {
    const minConfidence = Number(minConfidenceFilter || "0");
    return state.syncResults.filter((item) => {
      if (statusFilter !== "all" && item.status !== statusFilter) {
        return false;
      }
      if (sourceFilter !== "all" && item.source !== sourceFilter) {
        return false;
      }
      if ((item.confidence_score ?? 0) < minConfidence) {
        return false;
      }
      return true;
    });
  }, [minConfidenceFilter, sourceFilter, state.syncResults, statusFilter]);

  const acceptedManualCount = state.syncResults.filter((item) => item.status === "accepted_manual").length;
  const acceptedAutoCount = state.syncResults.filter((item) => item.status === "accepted_auto").length;
  const reviewHistoryCount = state.syncResults.reduce(
    (count, item) => count + (item.review_events?.length ?? 0),
    0,
  );

  useEffect(() => {
    if (state.currentProject) {
      setOutputPath(`${state.currentProject.root_path}\\exports\\sync_report.csv`);
    }
  }, [state.currentProject]);

  useEffect(() => {
    if (!state.currentProject || !state.projectSettings) {
      return;
    }
    const workspace = state.projectSettings.export_workspace;
    setIsRestoringWorkspace(true);
    setOutputPath(workspace.output_path || `${state.currentProject.root_path}\\exports\\sync_report.csv`);
    setStatusFilter(workspace.status_filter || "all");
    setSourceFilter(workspace.source_filter || "all");
    setMinConfidenceFilter(workspace.min_confidence_filter || "0");
    const timeoutId = window.setTimeout(() => setIsRestoringWorkspace(false), 0);
    return () => window.clearTimeout(timeoutId);
  }, [state.currentProject, state.projectSettings]);

  useEffect(() => {
    if (!state.currentProject || !state.projectSettings || isRestoringWorkspace) {
      return;
    }
    const timeoutId = window.setTimeout(async () => {
      try {
        await saveProjectSettings(state.currentProject!.id, {
          subtitle_workspace: state.projectSettings?.subtitle_workspace ?? {},
          export_workspace: {
            output_path: outputPath,
            status_filter: statusFilter,
            source_filter: sourceFilter,
            min_confidence_filter: minConfidenceFilter,
          },
        });
      } catch {
        // 项目恢复写回失败不打断当前工作流程。
      }
    }, 300);
    return () => window.clearTimeout(timeoutId);
  }, [
    isRestoringWorkspace,
    minConfidenceFilter,
    outputPath,
    sourceFilter,
    state.currentProject,
    state.projectSettings,
    statusFilter,
  ]);

  useEffect(() => {
    if (!state.currentProject) {
      return;
    }
    void refreshReviewQueue();
    void refreshSyncResults();
  }, [state.currentProject]);

  async function refreshSyncResults() {
    if (!state.currentProject) {
      return;
    }
    const response = await listSyncResults(state.currentProject.id);
    dispatch({ type: "SET_SYNC_RESULTS", payload: response.sync_results });
  }

  async function refreshReviewQueue() {
    if (!state.currentProject) {
      return;
    }
    const response = await listReviewQueue(state.currentProject.id);
    setReviewQueue(response.items);
    setAdjustOffsets((current) => {
      const next = { ...current };
      response.items.forEach((item) => {
        if (next[item.id] === undefined) {
          next[item.id] = String(item.offset_ms);
        }
      });
      return next;
    });
    setReviewNotes((current) => {
      const next = { ...current };
      response.items.forEach((item) => {
        if (next[item.id] === undefined) {
          next[item.id] = "";
        }
      });
      return next;
    });
  }

  async function handleChooseDirectory() {
    const directory = await chooseDirectory();
    if (directory) {
      setOutputPath(`${directory}\\sync_report.csv`);
    }
  }

  async function handleReviewAction(
    item: ReviewQueueItem,
    action: "accepted" | "rejected" | "adjusted" | "commented",
  ) {
    if (!state.currentProject) {
      return;
    }
    setReviewBusyId(item.id);
    try {
      await reviewSyncResult(state.currentProject.id, item.id, {
        action,
        new_offset_ms:
          action === "adjusted" ? Number(adjustOffsets[item.id] ?? item.offset_ms) : undefined,
        note: reviewNotes[item.id] ?? "",
      });
      await refreshReviewQueue();
      await refreshSyncResults();
      setReviewNotes((current) => ({ ...current, [item.id]: "" }));
      dispatch({
        type: "SET_NOTICE",
        payload: {
          tone: "success",
          message:
            action === "accepted"
              ? "候选已接受。"
              : action === "rejected"
                ? "候选已拒绝。"
                : action === "adjusted"
                  ? "候选已按新 offset 接受。"
                  : "备注已记录。",
        },
      });
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "复核操作失败。";
      dispatch({ type: "SET_NOTICE", payload: { tone: "error", message } });
    } finally {
      setReviewBusyId(null);
    }
  }

  async function handleExport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!state.currentProject) {
      return;
    }
    setBusy(true);
    try {
      await refreshSyncResults();
      const result = await exportCsv(state.currentProject.id, outputPath);
      dispatch({
        type: "SET_NOTICE",
        payload: { tone: "success", message: `CSV 已导出到 ${result.output_path}，共 ${result.row_count} 行。` },
      });
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "导出 CSV 失败。";
      dispatch({ type: "SET_NOTICE", payload: { tone: "error", message } });
    } finally {
      setBusy(false);
    }
  }

  async function handleExportFcp7Xml() {
    if (!state.currentProject) {
      return;
    }
    setBusy(true);
    try {
      await refreshSyncResults();
      const xmlPath = outputPath.toLowerCase().endsWith(".csv")
        ? `${outputPath.slice(0, -4)}_fcp7.xml`
        : `${outputPath}_fcp7.xml`;
      const result = await exportFcp7Xml(state.currentProject.id, xmlPath);
      dispatch({
        type: "SET_NOTICE",
        payload: {
          tone: "success",
          message: `FCP 7 XML 已导出到 ${result.output_path}，共 ${result.sequence_count} 条 sequence。`,
        },
      });
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "导出 FCP 7 XML 失败。";
      dispatch({ type: "SET_NOTICE", payload: { tone: "error", message } });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="page-grid">
      <article className="panel-card span-two">
        <header className="card-header">
          <h2>复核队列</h2>
          <span>{reviewQueue.length} 条待复核候选</span>
        </header>

        <div className="cluster-sample-list">
          {reviewQueue.map((item) => (
            <ReviewQueueCard
              key={item.id}
              item={item}
              reviewBusy={reviewBusyId === item.id}
              adjustOffset={adjustOffsets[item.id] ?? String(item.offset_ms)}
              note={reviewNotes[item.id] ?? ""}
              onAdjustOffsetChange={(value) =>
                setAdjustOffsets((current) => ({
                  ...current,
                  [item.id]: value,
                }))
              }
              onNoteChange={(value) =>
                setReviewNotes((current) => ({
                  ...current,
                  [item.id]: value,
                }))
              }
              onReviewAction={(action) => handleReviewAction(item, action)}
            />
          ))}
          {!reviewQueue.length ? <span className="status-meta">当前没有待复核候选。</span> : null}
        </div>
      </article>

      <article className="panel-card span-two">
        <header className="card-header">
          <h2>同步结果与 CSV 导出</h2>
          <span>只导出 `accepted_manual / accepted_auto` 结果</span>
        </header>

        <div className="metrics-grid">
          <div className="metric-card">
            <span>手动接受</span>
            <strong>{acceptedManualCount}</strong>
          </div>
          <div className="metric-card">
            <span>自动接受</span>
            <strong>{acceptedAutoCount}</strong>
          </div>
          <div className="metric-card">
            <span>复核历史</span>
            <strong>{reviewHistoryCount}</strong>
          </div>
        </div>

        <form className="form-stack" onSubmit={handleExport}>
          <label>
            <span>输出路径</span>
            <div className="inline-field">
              <input value={outputPath} onChange={(event) => setOutputPath(event.target.value)} />
              <button type="button" className="ghost-button" onClick={handleChooseDirectory}>
                选择目录
              </button>
            </div>
          </label>
          <button type="submit" className="primary-button" disabled={!outputPath || busy}>
            {busy ? "导出中..." : "导出 sync_report.csv"}
          </button>
          <button
            type="button"
            className="secondary-button"
            disabled={!outputPath || busy}
            onClick={handleExportFcp7Xml}
          >
            {busy ? "导出中..." : "导出 FCP 7 XML"}
          </button>
        </form>

        <div className="inline-settings">
          <label>
            <span>状态筛选</span>
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as typeof statusFilter)}>
              <option value="all">all</option>
              <option value="accepted_manual">accepted_manual</option>
              <option value="accepted_auto">accepted_auto</option>
              <option value="needs_review">needs_review</option>
              <option value="rejected">rejected</option>
            </select>
          </label>
          <label>
            <span>来源筛选</span>
            <select value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value as typeof sourceFilter)}>
              <option value="all">all</option>
              <option value="manual_anchor">manual_anchor</option>
              <option value="auto_text">auto_text</option>
            </select>
          </label>
          <label>
            <span>最低置信度</span>
            <input
              type="number"
              min={0}
              max={1}
              step={0.01}
              value={minConfidenceFilter}
              onChange={(event) => setMinConfidenceFilter(event.target.value)}
            />
          </label>
        </div>

        <div className="cluster-sample-list">
          {filteredSyncResults.map((item: SyncResult) => (
            <SyncResultCard key={item.id} item={item} />
          ))}
          {!filteredSyncResults.length ? (
            <span className="status-meta">当前筛选条件下没有同步结果。</span>
          ) : null}
        </div>
      </article>
    </section>
  );
}
