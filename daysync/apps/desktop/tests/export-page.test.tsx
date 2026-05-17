import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ExportPage } from "../src/pages/ExportPage";
import * as apiClient from "../src/api/client";

const hoisted = vi.hoisted(() => ({
  dispatch: vi.fn(),
  state: {
    currentProject: {
      id: "project-1",
      name: "测试项目",
      root_path: "D:\\projects\\demo",
    },
    projectSettings: {
      subtitle_workspace: {
        video_timeline_id: "",
        audio_timeline_id: "",
        video_srt_path: "",
        audio_srt_path: "",
        query: "",
        cluster_samples: [],
      },
      export_workspace: {
        output_path: "D:\\projects\\demo\\exports\\sync_report.csv",
        status_filter: "all" as const,
        source_filter: "all" as const,
        min_confidence_filter: "0",
      },
    },
    syncResults: [],
  },
}));

vi.mock("../src/state/AppState", () => ({
  useAppState: () => ({
    state: hoisted.state,
    dispatch: hoisted.dispatch,
  }),
}));

vi.mock("../src/api/tauri", () => ({
  chooseDirectory: vi.fn().mockResolvedValue(null),
}));

vi.mock("../src/api/client", async () => {
  const actual = await vi.importActual<typeof import("../src/api/client")>("../src/api/client");
  return {
    ...actual,
    exportCsv: vi.fn(),
    exportFcp7Xml: vi.fn(),
    exportJson: vi.fn(),
    listExportJobs: vi.fn(),
    listReviewQueue: vi.fn(),
    listSyncResults: vi.fn(),
    reviewSyncResult: vi.fn(),
    saveProjectSettings: vi
      .fn()
      .mockResolvedValue({ project_settings: hoisted.state.projectSettings }),
  };
});

describe("ExportPage", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("展示最近导出记录的路径和时间", async () => {
    vi.mocked(apiClient.listReviewQueue).mockResolvedValue({ items: [] });
    vi.mocked(apiClient.listSyncResults).mockResolvedValue({ sync_results: [] });
    vi.mocked(apiClient.listExportJobs).mockResolvedValue({
      items: [
        {
          id: "export-2",
          project_id: "project-1",
          export_type: "fcp7_xml",
          output_path: "D:\\exports\\sync_report_fcp7.xml",
          status: "succeeded",
          row_count: 2,
          error_message: null,
          created_at: "2026-05-17T13:45:04Z",
          completed_at: "2026-05-17T13:45:05Z",
        },
      ],
    });

    render(<ExportPage />);

    expect(screen.getByText("最近导出记录")).toBeInTheDocument();
    expect(await screen.findByText("D:\\exports\\sync_report_fcp7.xml")).toBeInTheDocument();
    expect(screen.getByText(/创建 2026-05-17T13:45:04Z/)).toBeInTheDocument();
    expect(screen.getByText(/完成 2026-05-17T13:45:05Z/)).toBeInTheDocument();

    await waitFor(() => {
      expect(apiClient.listExportJobs).toHaveBeenCalledWith("project-1");
    });
  });

  it("点击导出 JSON 时写入默认 json 路径", async () => {
    const user = userEvent.setup();
    vi.mocked(apiClient.listReviewQueue).mockResolvedValue({ items: [] });
    vi.mocked(apiClient.listSyncResults).mockResolvedValue({ sync_results: [] });
    vi.mocked(apiClient.listExportJobs).mockResolvedValue({ items: [] });
    vi.mocked(apiClient.exportJson).mockResolvedValue({
      output_path: "D:\\projects\\demo\\exports\\sync_report.json",
      item_count: 0,
    });

    render(<ExportPage />);

    await screen.findByText("导出 JSON");
    await user.click(screen.getByRole("button", { name: "导出 JSON" }));

    await waitFor(() => {
      expect(apiClient.exportJson).toHaveBeenCalledWith(
        "project-1",
        "D:\\projects\\demo\\exports\\sync_report.json",
      );
    });
  });
});
