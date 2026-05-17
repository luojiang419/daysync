import { type FormEvent, useState } from "react";

import { ApiError, createProject, openProject } from "../api/client";
import { chooseDirectory } from "../api/tauri";
import { useAppState } from "../state/AppState";

export function ProjectHomePage() {
  const { state, dispatch } = useAppState();
  const [createForm, setCreateForm] = useState({
    name: "",
    rootPath: "",
    shootingDate: "",
  });
  const [openPath, setOpenPath] = useState("");
  const [busyAction, setBusyAction] = useState<"create" | "open" | null>(null);

  async function pickCreateDirectory() {
    const directory = await chooseDirectory();
    if (directory) {
      setCreateForm((current) => ({ ...current, rootPath: directory }));
    }
  }

  async function pickOpenDirectory() {
    const directory = await chooseDirectory();
    if (directory) {
      setOpenPath(directory);
    }
  }

  async function handleCreateProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusyAction("create");
    dispatch({ type: "SET_NOTICE", payload: null });
    try {
      const snapshot = await createProject({
        name: createForm.name,
        root_path: createForm.rootPath,
        shooting_date: createForm.shootingDate || undefined,
      });
      dispatch({ type: "HYDRATE_PROJECT", payload: snapshot });
      dispatch({
        type: "SET_NOTICE",
        payload: { tone: "success", message: "项目已创建并载入工作台。" },
      });
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "创建项目失败。";
      dispatch({ type: "SET_NOTICE", payload: { tone: "error", message } });
    } finally {
      setBusyAction(null);
    }
  }

  async function handleOpenProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusyAction("open");
    dispatch({ type: "SET_NOTICE", payload: null });
    try {
      const snapshot = await openProject(openPath);
      dispatch({ type: "HYDRATE_PROJECT", payload: snapshot });
      dispatch({
        type: "SET_NOTICE",
        payload: { tone: "success", message: "项目已重新打开。" },
      });
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "打开项目失败。";
      dispatch({ type: "SET_NOTICE", payload: { tone: "error", message } });
    } finally {
      setBusyAction(null);
    }
  }

  return (
    <section className="page-grid">
      <article className="panel-card hero-card">
        <div>
          <span className="eyebrow">MVP 0.1 工作台</span>
          <h2>先把项目根目录和本地 SQLite 固定下来</h2>
          <p>
            DaySync 当前以本地项目为真相源。创建或打开项目后，后续媒体导入、字幕映射、手动锚点和
            CSV 导出都会围绕这个目录运行。
          </p>
        </div>
        {state.currentProject ? (
          <div className="metrics-grid">
            <div className="metric-card">
              <span>媒体数量</span>
              <strong>{state.stats?.media_count ?? 0}</strong>
            </div>
            <div className="metric-card">
              <span>字幕数量</span>
              <strong>{state.stats?.subtitle_count ?? 0}</strong>
            </div>
            <div className="metric-card">
              <span>同步结果</span>
              <strong>{state.stats?.sync_result_count ?? 0}</strong>
            </div>
          </div>
        ) : null}
      </article>

      <article className="panel-card">
        <header className="card-header">
          <h3>新建项目</h3>
          <span>创建 `daysync.project.json` 与 `daysync.sqlite`</span>
        </header>
        <form className="form-stack" onSubmit={handleCreateProject}>
          <label>
            <span>项目名称</span>
            <input
              value={createForm.name}
              onChange={(event) =>
                setCreateForm((current) => ({ ...current, name: event.target.value }))
              }
              placeholder="纪录片样片 2026-01-01"
              required
            />
          </label>
          <label>
            <span>项目根目录</span>
            <div className="inline-field">
              <input
                value={createForm.rootPath}
                onChange={(event) =>
                  setCreateForm((current) => ({ ...current, rootPath: event.target.value }))
                }
                placeholder="D:\\DaySyncProjects\\docu-2026-01-01"
                required
              />
              <button type="button" className="ghost-button" onClick={pickCreateDirectory}>
                选择目录
              </button>
            </div>
          </label>
          <label>
            <span>拍摄日期</span>
            <input
              type="date"
              value={createForm.shootingDate}
              onChange={(event) =>
                setCreateForm((current) => ({ ...current, shootingDate: event.target.value }))
              }
            />
          </label>
          <button type="submit" className="primary-button" disabled={busyAction === "create"}>
            {busyAction === "create" ? "创建中..." : "创建项目"}
          </button>
        </form>
      </article>

      <article className="panel-card">
        <header className="card-header">
          <h3>打开已有项目</h3>
          <span>从 `daysync.project.json` 重新恢复工作区</span>
        </header>
        <form className="form-stack" onSubmit={handleOpenProject}>
          <label>
            <span>项目目录</span>
            <div className="inline-field">
              <input
                value={openPath}
                onChange={(event) => setOpenPath(event.target.value)}
                placeholder="D:\\DaySyncProjects\\docu-2026-01-01"
                required
              />
              <button type="button" className="ghost-button" onClick={pickOpenDirectory}>
                选择目录
              </button>
            </div>
          </label>
          <button type="submit" className="secondary-button" disabled={busyAction === "open"}>
            {busyAction === "open" ? "打开中..." : "打开项目"}
          </button>
        </form>
      </article>
    </section>
  );
}
