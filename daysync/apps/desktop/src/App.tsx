import { useEffect } from "react";
import { createHashRouter, RouterProvider } from "react-router-dom";

import { checkHealth } from "./api/client";
import { ensureDevApi } from "./api/tauri";
import { AppShell } from "./components/AppShell";
import { ExportPage } from "./pages/ExportPage";
import { FlatTimelinePage } from "./pages/FlatTimelinePage";
import { MediaImportPage } from "./pages/MediaImportPage";
import { ProjectHomePage } from "./pages/ProjectHomePage";
import { SubtitleSearchAndSyncPage } from "./pages/SubtitleSearchAndSyncPage";
import { useAppState } from "./state/AppState";

const router = createHashRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <ProjectHomePage /> },
      { path: "media", element: <MediaImportPage /> },
      { path: "timeline", element: <FlatTimelinePage /> },
      { path: "subtitles", element: <SubtitleSearchAndSyncPage /> },
      { path: "export", element: <ExportPage /> },
    ],
  },
]);

function App() {
  const { dispatch } = useAppState();

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      dispatch({
        type: "SET_HEALTH",
        payload: { state: "checking", message: "正在连接本地 API..." },
      });

      try {
        await ensureDevApi();
      } catch {
        // 开发模式下没有 Tauri runtime 时忽略自动拉起。
      }

      for (let attempt = 0; attempt < 6; attempt += 1) {
        try {
          const health = await checkHealth();
          if (cancelled) {
            return;
          }
          const ffmpegMessage = health.ffmpeg.ready
            ? `FFmpeg ${health.ffmpeg.version ?? "unknown"} · ${health.ffmpeg.source ?? "unknown"}`
            : `FFmpeg 未就绪：${health.ffmpeg.error ?? "未知错误"}`;
          dispatch({
            type: "SET_HEALTH",
            payload: {
              state: health.ffmpeg.ready ? "ready" : "error",
              message: `API 已连接，本会话登记 ${health.registered_projects} 个项目，${ffmpegMessage}`,
            },
          });
          return;
        } catch {
          await new Promise((resolve) => setTimeout(resolve, attempt === 0 ? 300 : 700));
        }
      }

      if (!cancelled) {
        dispatch({
          type: "SET_HEALTH",
          payload: {
            state: "error",
            message: "未连接到本地 API，请检查 DaySync 本地运行时是否完整，或在开发环境手动启动 uvicorn。",
          },
        });
      }
    }

    void bootstrap();

    return () => {
      cancelled = true;
    };
  }, [dispatch]);

  return <RouterProvider router={router} />;
}

export default App;
