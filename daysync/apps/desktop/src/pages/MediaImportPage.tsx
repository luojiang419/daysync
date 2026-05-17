import { type FormEvent, useEffect, useMemo, useState } from "react";

import { ApiError, importMedia, openProject } from "../api/client";
import { chooseDirectory, listenForDirectoryDrops } from "../api/tauri";
import { assignDroppedDirectories, normalizeDroppedDirectories } from "../media-import";
import { useAppState } from "../state/AppState";

export function MediaImportPage() {
  const { state, dispatch } = useAppState();
  const [videoDirectory, setVideoDirectory] = useState("");
  const [audioDirectory, setAudioDirectory] = useState("");
  const [busy, setBusy] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [dropTarget, setDropTarget] = useState<"video" | "audio" | null>(null);
  const paths = useMemo(() => [videoDirectory, audioDirectory].filter(Boolean), [audioDirectory, videoDirectory]);
  const latestVideoTimeline = useMemo(() => {
    const timelines = state.flatTimelines.filter((timeline) => timeline.media_type === "video");
    return timelines[timelines.length - 1] ?? null;
  }, [state.flatTimelines]);
  const latestAudioTimeline = useMemo(() => {
    const timelines = state.flatTimelines.filter((timeline) => timeline.media_type === "audio");
    return timelines[timelines.length - 1] ?? null;
  }, [state.flatTimelines]);

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
        setDropTarget(null);
        return;
      }
      if (event.type !== "drop") {
        return;
      }

      setDragActive(false);
      const normalizedDirectories = normalizeDroppedDirectories(event.paths);
      if (dropTarget && normalizedDirectories[0]) {
        if (dropTarget === "video") {
          setVideoDirectory(normalizedDirectories[0]);
        } else {
          setAudioDirectory(normalizedDirectories[0]);
        }
        dispatch({
          type: "SET_NOTICE",
          payload: {
            tone: "success",
            message: `已将目录放入${dropTarget === "video" ? "视频整轨" : "音频整轨"}分栏，导入后会自动重建整条时间线。`,
          },
        });
        setDropTarget(null);
        return;
      }

      const next = assignDroppedDirectories(videoDirectory, audioDirectory, normalizedDirectories);
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
  }, [audioDirectory, dispatch, dropTarget, videoDirectory]);

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
      const snapshot = await openProject(state.currentProject.root_path);
      dispatch({ type: "HYDRATE_PROJECT", payload: snapshot });
      dispatch({
        type: "SET_NOTICE",
        payload: {
          tone: result.failed.length ? "neutral" : "success",
          message: result.failed.length
            ? `导入完成，成功 ${result.imported.length} 个，失败 ${result.failed.length} 个；系统已自动更新整轨，请检查目录内是否包含受支持媒体文件。`
            : `已导入 ${result.imported.length} 个媒体文件，并自动重建视频/音频整轨。`,
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
      <article className="panel-card span-two">
        <header className="card-header">
          <h2>导入目录并自动生成整轨</h2>
          <span>导入视频目录与外录音频目录后，系统会把整个目录直接视为一条时间线轨道</span>
        </header>
        <form className="form-stack" onSubmit={handleImport}>
          <div className="lane-note-card">
            <strong>这里不再单独勾选素材文件。</strong>
            <span>目录导入完成后，会自动重建“视频整轨”和“音频整轨”，后续字幕搜索和对齐都基于整条轨道。</span>
          </div>
          <div className="media-import-lanes">
            <section className="media-import-lane">
              <header className="result-column-header">
                <div>
                  <h3>视频整轨</h3>
                  <span>目录内所有视频会自动平铺成一条视频轨</span>
                </div>
                <span>{latestVideoTimeline?.items.length ?? 0} 段素材</span>
              </header>
              <div
                className={`drop-zone${dragActive && dropTarget === "video" ? " is-active" : ""}`}
                onDragEnter={() => setDropTarget("video")}
                onDragOver={() => setDropTarget("video")}
                onDragLeave={() => setDropTarget(null)}
              >
                <strong>把视频目录拖到这个分栏</strong>
                <span>也可以直接点按钮选择目录，导入后自动更新整轨。</span>
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
              <div className="path-preview">
                {videoDirectory || "导入后这里会固定为当前视频整轨目录"}
              </div>
            </section>

            <section className="media-import-lane">
              <header className="result-column-header">
                <div>
                  <h3>音频整轨</h3>
                  <span>目录内所有音频会自动平铺成一条音频轨</span>
                </div>
                <span>{latestAudioTimeline?.items.length ?? 0} 段素材</span>
              </header>
              <div
                className={`drop-zone${dragActive && dropTarget === "audio" ? " is-active" : ""}`}
                onDragEnter={() => setDropTarget("audio")}
                onDragOver={() => setDropTarget("audio")}
                onDragLeave={() => setDropTarget(null)}
              >
                <strong>把音频目录拖到这个分栏</strong>
                <span>支持 `wav / m4a / mp3`，导入后自动更新整轨。</span>
              </div>
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
              <div className="path-preview">
                {audioDirectory || "导入后这里会固定为当前音频整轨目录"}
              </div>
            </section>
          </div>
          <div className="button-row">
            <button type="submit" className="primary-button" disabled={busy || !paths.length}>
              {busy ? "导入中..." : "导入目录并自动生成整轨"}
            </button>
          </div>
        </form>
      </article>

      <article className="panel-card span-two">
        <header className="card-header">
          <h3>当前媒体列表</h3>
          <span>{state.mediaFiles.length} 个文件已进入当前整轨工程</span>
        </header>
        <div className="table-wrap table-wrap-scroll">
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
