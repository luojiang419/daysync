import { type FormEvent, useEffect, useMemo, useState } from "react";

import { ApiError, importMedia } from "../api/client";
import { chooseDirectory, listenForDirectoryDrops } from "../api/tauri";
import { assignDroppedDirectories } from "../media-import";
import { useAppState } from "../state/AppState";

export function MediaImportPage() {
  const { state, dispatch } = useAppState();
  const [videoDirectory, setVideoDirectory] = useState("");
  const [audioDirectory, setAudioDirectory] = useState("");
  const [busy, setBusy] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const paths = useMemo(() => [videoDirectory, audioDirectory].filter(Boolean), [audioDirectory, videoDirectory]);

  useEffect(() => {
    let unlisten: (() => void) | null = null;
    let disposed = false;

    void listenForDirectoryDrops((event) => {
      if (event.type === "enter" || event.type === "over") {
        setDragActive(true);
        return;
      }
      if (event.type === "leave") {
        setDragActive(false);
        return;
      }
      if (event.type !== "drop") {
        return;
      }

      setDragActive(false);
      const next = assignDroppedDirectories(videoDirectory, audioDirectory, event.paths);
      if (next.acceptedCount === 0) {
        dispatch({
          type: "SET_NOTICE",
          payload: {
            tone: "neutral",
            message: "拖入的目录未被采用。若两个目录都已填写，请先清空或直接改写输入框。",
          },
        });
        return;
      }

      setVideoDirectory(next.videoDirectory);
      setAudioDirectory(next.audioDirectory);
      dispatch({
        type: "SET_NOTICE",
        payload: {
          tone: next.ignoredCount ? "neutral" : "success",
          message: next.ignoredCount
            ? `已接收 ${next.acceptedCount} 个目录，忽略 ${next.ignoredCount} 个多余路径。`
            : `已接收 ${next.acceptedCount} 个拖入目录，现在可以开始导入。`,
        },
      });
    }).then((dispose) => {
      if (disposed) {
        dispose();
        return;
      }
      unlisten = dispose;
    });

    return () => {
      disposed = true;
      if (unlisten) {
        unlisten();
      }
    };
  }, [audioDirectory, dispatch, videoDirectory]);

  async function pickVideoDirectory() {
    const selected = await chooseDirectory();
    if (selected) {
      setVideoDirectory(selected);
    }
  }

  async function pickAudioDirectory() {
    const selected = await chooseDirectory();
    if (selected) {
      setAudioDirectory(selected);
    }
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
            ? `导入完成，成功 ${result.imported.length} 个，失败 ${result.failed.length} 个。请检查目录内是否包含受支持媒体文件。`
            : `已导入 ${result.imported.length} 个媒体文件。`,
        },
      });
      if (result.imported.length) {
        setVideoDirectory("");
        setAudioDirectory("");
      }
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
          <span>分别选择视频目录与外录音频目录，系统会自动递归导入 `mov / mp4 / wav / m4a / mp3`</span>
        </header>
        <form className="form-stack" onSubmit={handleImport}>
          <div className={`drop-zone${dragActive ? " is-active" : ""}`}>
            <strong>把视频目录或外录音频目录直接拖进这里也可以导入</strong>
            <span>
              拖入 1 个目录时会填到第一个空位；拖入 2 个目录时按“视频目录、外录音频目录”顺序填充。
            </span>
          </div>
          <label>
            <span>视频目录</span>
            <div className="inline-field">
              <input
                value={videoDirectory}
                onChange={(event) => setVideoDirectory(event.target.value)}
                placeholder="D:\\media\\video"
              />
              <button type="button" className="ghost-button" onClick={pickVideoDirectory}>
                选择视频目录
              </button>
            </div>
          </label>
          <label>
            <span>外录音频目录</span>
            <div className="inline-field">
              <input
                value={audioDirectory}
                onChange={(event) => setAudioDirectory(event.target.value)}
                placeholder="D:\\audio\\external"
              />
              <button type="button" className="ghost-button" onClick={pickAudioDirectory}>
                选择外录音频目录
              </button>
            </div>
          </label>
          <label>
            <span>待导入目录</span>
            <textarea
              rows={5}
              value={paths.join("\n")}
              readOnly
              placeholder={"选择或拖入视频目录与外录音频目录后，会显示在这里"}
            />
          </label>
          <div className="button-row">
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
