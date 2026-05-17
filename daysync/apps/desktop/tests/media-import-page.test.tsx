import { render, screen } from "@testing-library/react";

import { MediaImportPage } from "../src/pages/MediaImportPage";

vi.mock("../src/state/AppState", () => ({
  useAppState: () => ({
    state: {
      currentProject: {
        id: "project-1",
        name: "测试项目",
        root_path: "D:\\projects\\demo",
      },
      mediaFiles: [],
    },
    dispatch: vi.fn(),
  }),
}));

vi.mock("../src/api/client", async () => {
  const actual = await vi.importActual<typeof import("../src/api/client")>("../src/api/client");
  return {
    ...actual,
    importMedia: vi.fn(),
  };
});

vi.mock("../src/api/tauri", () => ({
  chooseDirectory: vi.fn().mockResolvedValue(null),
}));

describe("MediaImportPage", () => {
  it("提供视频目录与外录音频目录两个选择按钮", () => {
    render(<MediaImportPage />);

    expect(screen.getByRole("button", { name: "选择视频目录" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "选择外录音频目录" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "选择文件" })).not.toBeInTheDocument();
  });
});
