import { render, screen } from "@testing-library/react";

import { ProjectHomePage } from "../src/pages/ProjectHomePage";

vi.mock("../src/state/AppState", () => ({
  useAppState: () => ({
    state: {
      currentProject: null,
      stats: null,
    },
    dispatch: vi.fn(),
  }),
}));

vi.mock("../src/api/client", async () => {
  const actual = await vi.importActual<typeof import("../src/api/client")>("../src/api/client");
  return {
    ...actual,
    createProject: vi.fn(),
    openProject: vi.fn(),
    checkHealth: vi.fn(),
    waitForApiReady: vi.fn(),
  };
});

vi.mock("../src/api/tauri", () => ({
  chooseDirectory: vi.fn().mockResolvedValue(null),
  ensureDevApi: vi.fn().mockResolvedValue(false),
}));

describe("ProjectHomePage", () => {
  afterEach(() => {
    window.localStorage.clear();
  });

  it("把拍摄日期改为可选辅助备注", () => {
    render(<ProjectHomePage />);

    expect(screen.getByText("辅助备注（可选）")).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText("例如：2026/05/17 首次整理，或客户给的项目备注"),
    ).toBeInTheDocument();
  });
});
