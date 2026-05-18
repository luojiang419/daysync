import { useEffect } from "react";
import { createHashRouter, RouterProvider } from "react-router-dom";

import { ApiError, ensureLocalApiReady, openProject } from "./api/client";
import { AppShell } from "./components/AppShell";
import { ExportPage } from "./pages/ExportPage";
import { FlatTimelinePage } from "./pages/FlatTimelinePage";
import { MediaImportPage } from "./pages/MediaImportPage";
import { ProjectHomePage } from "./pages/ProjectHomePage";
import { clearLastProjectRoot, loadLastProjectRoot } from "./project-persistence";
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

function formatRuntimeFailureMessage(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return "未能连接本地运行时，请检查 DaySync 桌面运行时是否完整。";
  }
  const cause = error.details.cause;
  if (typeof cause === "string" && cause.trim()) {
    return `未能连接本地运行时：${cause}`;
  }
  return error.message || "未能连接本地运行时，请检查 DaySync 桌面运行时是否完整。";
}

function App() {
  const { dispatch } = useAppState();

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      dispatch({
        type: "SET_HEALTH",
        payload: { state: "checking", message: "正在连接本地运行时..." },
      });

      try {
          const health = await ensureLocalApiReady();
          if (cancelled) {
            return;
          }
          const lastProjectRoot = loadLastProjectRoot();
          if (lastProjectRoot) {
            try {
              const snapshot = await openProject(lastProjectRoot);
              if (!cancelled) {
                dispatch({ type: "HYDRATE_PROJECT", payload: snapshot });
              }
            } catch {
              clearLastProjectRoot();
              if (!cancelled) {
                dispatch({
                  type: "SET_NOTICE",
                  payload: {
                    tone: "error",
                    message: "上次项目目录已失效，自动恢复记录已清除，请重新打开项目。",
                  },
                });
              }
            }
          }
          const ffmpegMessage = health.ffmpeg.ready
            ? `FFmpeg ${health.ffmpeg.version ?? "unknown"} · ${health.ffmpeg.source ?? "unknown"}`
            : `FFmpeg 未就绪：${health.ffmpeg.error ?? "未知错误"}`;
          dispatch({
            type: "SET_HEALTH",
            payload: {
              state: health.ffmpeg.ready ? "ready" : "error",
              message: `本地运行时已就绪，本会话登记 ${health.registered_projects} 个项目，${ffmpegMessage}`,
            },
          });
          return;
      } catch (error) {
        if (!cancelled) {
          dispatch({
            type: "SET_HEALTH",
            payload: {
              state: "error",
              message: formatRuntimeFailureMessage(error),
            },
          });
        }
        return;
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
