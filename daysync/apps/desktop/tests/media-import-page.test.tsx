import { render, screen } from "@testing-library/react";

import { MediaImportPage } from "../src/pages/MediaImportPage";
import { assignDroppedDirectories, normalizeDroppedDirectories } from "../src/media-import";

vi.mock("../src/state/AppState", () => ({
  useAppState: () => ({
    state: {
      currentProject: {
        id: "project-1",
        name: "测试项目",
        root_path: "D:\\projects\\demo",
      },
      mediaFiles: [],
      flatTimelines: [],
    },
    dispatch: vi.fn(),
  }),
}));

vi.mock("../src/api/client", async () => {
  const actual = await vi.importActual<typeof import("../src/api/client")>("../src/api/client");
  return {
    ...actual,
    importMedia: vi.fn(),
    openProject: vi.fn(),
  };
});

vi.mock("../src/api/tauri", () => ({
  chooseDirectory: vi.fn().mockResolvedValue(null),
  listenForDirectoryDrops: vi.fn().mockResolvedValue(() => {}),
}));

describe("MediaImportPage", () => {
  it("提供视频目录与外录音频目录两个选择按钮", () => {
    render(<MediaImportPage />);

    expect(screen.getByRole("button", { name: "选择视频目录" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "选择外录音频目录" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "选择文件" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "导入目录并自动生成整轨" })).toBeInTheDocument();
    expect(screen.getByText("视频整轨")).toBeInTheDocument();
    expect(screen.getByText("音频整轨")).toBeInTheDocument();
  });

  it("拖入媒体文件时会自动归并到父目录", () => {
    expect(
      normalizeDroppedDirectories([
        "D:\\video\\A001_C001.mov",
        "D:\\audio\\ZOOM0001.wav",
        "D:\\video\\A001_C001.mov",
      ]),
    ).toEqual(["D:\\video", "D:\\audio"]);
  });

  it("拖入目录时会按空位填充视频与音频目录", () => {
    expect(assignDroppedDirectories("", "", ["D:\\video", "D:\\audio"])).toEqual({
      videoDirectory: "D:\\video",
      audioDirectory: "D:\\audio",
      acceptedCount: 2,
      ignoredCount: 0,
    });
  });
});
