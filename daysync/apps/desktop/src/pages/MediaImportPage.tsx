import { type FormEvent, useMemo, useState } from "react";

import { ApiError, importMedia } from "../api/client";
import { chooseFiles } from "../api/tauri";
import { useAppState } from "../state/AppState";

export function MediaImportPage() {
  const { state, dispatch } = useAppState();
  const [rawPaths, setRawPaths] = useState("");
  const [busy, setBusy] = useState(false);
  const paths = useMemo(
    () =>
      rawPaths
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean),
    [rawPaths],
  );

  async function appendFilesFromDialog() {
    const selected = await chooseFiles();
    if (!selected.length) {
      return;
    }
    setRawPaths((current) => [current, ...selected].filter(Boolean).join("\n"));
  }

  async function handleImport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!state.currentProject) {
      dispatch({
        type: "SET_NOTICE",
        payload: { tone: "error", message: "请先创建或打开项目。" },
      });
      return;
    }
    setBusy(true);
    try {
      const result = await importMedia(state.currentProject.id, {
        paths,
        session_id: null,
      });
      dispatch({ type: "MERGE_MEDIA", payload: result.imported });
      dispatch({
        type: "SET_NOTICE",
        payload: {
          tone: result.failed.length ? "neutral" : "success",
          message: result.failed.length
            ? `导入完成，成功 ${result.imported.length} 个，失败 ${result.failed.length} 个。`
            : `已导入 ${result.imported.length} 个媒体文件。`,
        },
      });
      setRawPaths("");
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "导入媒体失败。";
      dispatch({ type: "SET_NOTICE", payload: { tone: "error", message } });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="page-grid">
      <article className="panel-card">
        <header className="card-header">
          <h2>导入视频与外录音频</h2>
          <span>支持 `mov / mp4 / wav / m4a`，不会移动原始素材</span>
        </header>
        <form className="form-stack" onSubmit={handleImport}>
          <label>
            <span>文件路径</span>
            <textarea
              rows={8}
              value={rawPaths}
              onChange={(event) => setRawPaths(event.target.value)}
              placeholder={"每行一个路径\nD:\\media\\A001_C001.mov\nD:\\audio\\ZOOM0001.wav"}
              required
            />
          </label>
          <div className="button-row">
            <button type="button" className="ghost-button" onClick={appendFilesFromDialog}>
              选择文件
            </button>
            <button type="submit" className="primary-button" disabled={busy || !paths.length}>
              {busy ? "导入中..." : "开始导入"}
            </button>
          </div>
        </form>
      </article>

      <article className="panel-card">
        <header className="card-header">
          <h3>当前媒体列表</h3>
          <span>{state.mediaFiles.length} 个文件已进入项目</span>
        </header>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>文件名</th>
                <th>类型</th>
                <th>时长(ms)</th>
              </tr>
            </thead>
            <tbody>
              {state.mediaFiles.map((media) => (
                <tr key={media.id}>
                  <td>{media.filename}</td>
                  <td>{media.media_type === "video" ? "视频" : "音频"}</td>
                  <td>{media.duration_ms}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </article>
    </section>
  );
}
