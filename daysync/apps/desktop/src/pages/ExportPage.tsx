import { type FormEvent, useEffect, useState } from "react";

import { ApiError, exportCsv, listSyncResults } from "../api/client";
import { chooseDirectory } from "../api/tauri";
import { useAppState } from "../state/AppState";

export function ExportPage() {
  const { state, dispatch } = useAppState();
  const [outputPath, setOutputPath] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (state.currentProject) {
      setOutputPath(`${state.currentProject.root_path}\\exports\\sync_report.csv`);
    }
  }, [state.currentProject]);

  async function refreshSyncResults() {
    if (!state.currentProject) {
      return;
    }
    const response = await listSyncResults(state.currentProject.id);
    dispatch({ type: "SET_SYNC_RESULTS", payload: response.sync_results });
  }

  async function handleChooseDirectory() {
    const directory = await chooseDirectory();
    if (directory) {
      setOutputPath(`${directory}\\sync_report.csv`);
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
