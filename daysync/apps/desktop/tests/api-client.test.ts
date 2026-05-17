import { ApiError, checkHealth } from "../src/api/client";

describe("api client", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("返回健康检查数据", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        text: async () => JSON.stringify({ status: "ok", registered_projects: 2 }),
      }),
    );

    const result = await checkHealth();
    expect(result.status).toBe("ok");
    expect(result.registered_projects).toBe(2);
  });

  it("把后端错误解包成 ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        text: async () =>
          JSON.stringify({
            error: {
              code: "PROJECT_PATH_INVALID",
              message: "路径不可写",
              details: { root_path: "D:\\test" },
            },
          }),
      }),
    );

    await expect(checkHealth()).rejects.toMatchObject({
      code: "PROJECT_PATH_INVALID",
      message: "路径不可写",
    } satisfies Partial<ApiError>);
  });
});
