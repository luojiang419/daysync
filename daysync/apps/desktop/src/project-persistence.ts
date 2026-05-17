const LAST_PROJECT_ROOT_KEY = "daysync.last_project_root";

export function loadLastProjectRoot(): string {
  try {
    return window.localStorage.getItem(LAST_PROJECT_ROOT_KEY) ?? "";
  } catch {
    return "";
  }
}

export function saveLastProjectRoot(rootPath: string): void {
  try {
    if (!rootPath) {
      window.localStorage.removeItem(LAST_PROJECT_ROOT_KEY);
      return;
    }
    window.localStorage.setItem(LAST_PROJECT_ROOT_KEY, rootPath);
  } catch {
    // 忽略无持久化能力的运行环境。
  }
}

export function clearLastProjectRoot(): void {
  try {
    window.localStorage.removeItem(LAST_PROJECT_ROOT_KEY);
  } catch {
    // 忽略无持久化能力的运行环境。
  }
}
