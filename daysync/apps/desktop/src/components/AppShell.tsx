import { NavLink, Outlet } from "react-router-dom";

import { getApiBaseUrl } from "../api/client";
import { useAppState } from "../state/AppState";

const NAV_ITEMS = [
  { to: "/", label: "项目" },
  { to: "/media", label: "媒体导入" },
  { to: "/timeline", label: "平铺时间线" },
  { to: "/subtitles", label: "字幕同步" },
  { to: "/export", label: "导出" },
];

export function AppShell() {
  const {
    state: { currentProject, healthState, healthMessage, notice },
  } = useAppState();

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-kicker">字幕锚点合板</span>
          <h1>DaySync</h1>
          <p>本地优先的纪录片合板工作台</p>
        </div>

        <nav className="nav-list" aria-label="主导航">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className={`status-card is-${healthState}`}>
          <div className="status-label">API 状态</div>
          <strong>{healthMessage}</strong>
          <span className="status-meta">{getApiBaseUrl()}</span>
        </div>

        {currentProject ? (
          <div className="project-chip">
            <span>当前项目</span>
            <strong>{currentProject.name}</strong>
            <small>{currentProject.root_path}</small>
          </div>
        ) : null}
      </aside>

      <main className="main-panel">
        {notice ? (
          <div className={`notice-banner is-${notice.tone}`} role="status">
            {notice.message}
          </div>
        ) : null}
        <Outlet />
      </main>
    </div>
  );
}
