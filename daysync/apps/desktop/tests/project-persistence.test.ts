import {
  clearLastProjectRoot,
  loadLastProjectRoot,
  saveLastProjectRoot,
} from "../src/project-persistence";

describe("project persistence", () => {
  afterEach(() => {
    window.localStorage.clear();
  });

  it("可以保存并读取上次项目目录", () => {
    saveLastProjectRoot("D:\\projects\\demo");

    expect(loadLastProjectRoot()).toBe("D:\\projects\\demo");
  });

  it("清除后返回空字符串", () => {
    saveLastProjectRoot("D:\\projects\\demo");
    clearLastProjectRoot();

    expect(loadLastProjectRoot()).toBe("");
  });
});
