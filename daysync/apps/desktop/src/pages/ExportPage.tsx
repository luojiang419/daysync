import { type FormEvent, useEffect, useState } from "react";

import {
  ApiError,
  exportCsv,
  listReviewQueue,
  listSyncResults,
  reviewSyncResult,
} from "../api/client";
import type { ReviewQueueItem } from "../api/types";
import { chooseDirectory } from "../api/tauri";
import { useAppState } from "../state/AppState";

export function ExportPage() {
  const { state, dispatch } = useAppState();
  const [outputPath, setOutputPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [reviewQueue, setReviewQueue] = useState<ReviewQueueItem[]>([]);
  const [reviewBusyId, setReviewBusyId] = useState<string | null>(null);
  const [adjustOffsets, setAdjustOffsets] = useState<Record<string, string>>({});

  useEffect(() => {
    if (state.currentProject) {
      setOutputPath(`${state.currentProject.root_path}\\exports\\sync_report.csv`);
    }
  }, [state.currentProject]);

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
  }

  async function handleChooseDirectory() {
    const directory = await chooseDirectory();
    if (directory) {
      setOutputPath(`${directory}\\sync_report.csv`);
    }
  }

  async function handleReviewAction(
    item: ReviewQueueItem,
    action: "accepted" | "rejected" | "adjusted",
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
      });
      await refreshReviewQueue();
      await refreshSyncResults();
      dispatch({
        type: "SET_NOTICE",
        payload: {
          tone: "success",
          message:
            action === "accepted"
              ? "候选已接受。"
              : action === "rejected"
                ? "候选已拒绝。"
                : "候选已按新 offset 接受。",
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

  return (
    <section className="page-grid">
      <article className="panel-card span-two">
        <header className="card-header">
          <h2>复核队列</h2>
          <span>{reviewQueue.length} 条待复核候选</span>
        </header>

        <div className="cluster-sample-list">
          {reviewQueue.map((item) => {
            const clusterSummary = (item.confidence_breakdown["cluster_summary"] ?? {}) as {
              final_offset_ms?: number | null;
              inlier_ratio?: number;
              passes?: boolean;
              reasons?: string[];
            };
            return (
              <article key={item.id} className="cluster-sample-card">
                <div className="candidate-card-header">
                  <strong>
                    {item.video_file} ↔ {item.audio_file}
                  </strong>
                  <span>{Math.round(item.confidence_score * 100)} 分</span>
                </div>
                <div className="candidate-meta">
                  <span>
                    当前 offset {item.offset_ms} ms · 状态 {item.status}
                  </span>
                  <span>
                    聚类 {clusterSummary.passes ? "通过" : "未通过"} · inlier ratio{" "}
                    {Math.round((clusterSummary.inlier_ratio ?? 0) * 100)}%
                  </span>
                </div>
                <div className="candidate-context">
                  <small>视频锚点：{item.video_anchor_text ?? "-"}</small>
                  <small>音频锚点：{item.audio_anchor_text ?? "-"}</small>
                  <small>原因：{(clusterSummary.reasons ?? []).join(", ") || "无"}</small>
                </div>
                <div className="inline-field">
                  <input
                    value={adjustOffsets[item.id] ?? String(item.offset_ms)}
                    onChange={(event) =>
                      setAdjustOffsets((current) => ({
                        ...current,
                        [item.id]: event.target.value,
                      }))
                    }
                  />
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={reviewBusyId === item.id}
                    onClick={() => handleReviewAction(item, "accepted")}
                  >
                    接受
                  </button>
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={reviewBusyId === item.id}
                    onClick={() => handleReviewAction(item, "adjusted")}
                  >
                    微调后接受
                  </button>
                  <button
                    type="button"
                    className="ghost-button"
                    disabled={reviewBusyId === item.id}
                    onClick={() => handleReviewAction(item, "rejected")}
                  >
                    拒绝
                  </button>
                </div>
                {item.review_events.length ? (
                  <div className="candidate-context">
                    {item.review_events.slice(0, 2).map((event) => (
                      <small key={event.id}>
                        {event.event_type} · old {event.old_offset_ms ?? "-"} · new{" "}
                        {event.new_offset_ms ?? "-"} · {event.created_at}
                      </small>
                    ))}
                  </div>
                ) : null}
              </article>
            );
          })}
          {!reviewQueue.length ? <span className="status-meta">当前没有待复核候选。</span> : null}
        </div>
      </article>

      <article className="panel-card span-two">
        <header className="card-header">
          <h2>同步结果与 CSV 导出</h2>
          <span>只导出 `accepted_manual / accepted_auto` 结果</span>
        </header>
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
        </form>

        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>状态</th>
                <th>offset_ms</th>
                <th>视频素材</th>
                <th>音频素材</th>
                <th>视频锚点</th>
                <th>音频锚点</th>
              </tr>
            </thead>
            <tbody>
              {state.syncResults.map((item) => (
                <tr key={item.id}>
                  <td>{item.status}</td>
                  <td>{item.offset_ms}</td>
                  <td>{item.video_file ?? "-"}</td>
                  <td>{item.audio_file ?? "-"}</td>
                  <td>{item.video_anchor_text ?? "-"}</td>
                  <td>{item.audio_anchor_text ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </article>
    </section>
  );
}
