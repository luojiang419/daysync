import { convertFileSrc, invoke } from "@tauri-apps/api/core";
import type { DragDropEvent } from "@tauri-apps/api/webview";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import { open } from "@tauri-apps/plugin-dialog";

declare global {
  interface Window {
    __TAURI_INTERNALS__?: unknown;
  }
}

export function isTauriRuntime(): boolean {
  return Boolean(window.__TAURI_INTERNALS__);
}

export type RuntimeErrorPayload = {
  code: string;
  message: string;
  details: Record<string, unknown>;
};

type RuntimeCommandResponse<T> = {
  ok: boolean;
  result?: T;
  error?: RuntimeErrorPayload;
};

export class RuntimeInvocationError extends Error {
  code: string;
  details: Record<string, unknown>;

  constructor(code: string, message: string, details: Record<string, unknown> = {}) {
    super(message);
    this.code = code;
    this.details = details;
  }
}

function unwrapRuntimeResponse<T>(response: RuntimeCommandResponse<T>): T {
  if (response.ok && response.result !== undefined) {
    return response.result;
  }
  const error = response.error;
  throw new RuntimeInvocationError(
    error?.code ?? "RUNTIME_UNAVAILABLE",
    error?.message ?? "未能连接本地运行时，请稍后重试。",
    error?.details ?? {},
  );
}

export async function ensureRuntimeReady<T>(): Promise<T> {
  if (!isTauriRuntime()) {
    throw new RuntimeInvocationError(
      "RUNTIME_UNAVAILABLE",
      "当前环境不是 DaySync 桌面版，本地运行时不可用。",
    );
  }
  const response = await invoke<RuntimeCommandResponse<T>>("ensure_runtime_ready");
  return unwrapRuntimeResponse(response);
}

export async function invokeRuntime<T>(
  method: string,
  payload: Record<string, unknown> = {},
): Promise<T> {
  if (!isTauriRuntime()) {
    throw new RuntimeInvocationError(
      "RUNTIME_UNAVAILABLE",
      "当前环境不是 DaySync 桌面版，本地运行时不可用。",
    );
  }
  const response = await invoke<RuntimeCommandResponse<T>>("invoke_runtime", { method, payload });
  return unwrapRuntimeResponse(response);
}

export async function chooseDirectory(): Promise<string | null> {
  if (!isTauriRuntime()) {
    return null;
  }
  const result = await open({ directory: true, multiple: false });
  return Array.isArray(result) ? (result[0] ?? null) : result;
}

export async function chooseFiles(): Promise<string[]> {
  if (!isTauriRuntime()) {
    return [];
  }
  const result = await open({ multiple: true, filters: [{ name: "Media", extensions: ["mov", "mp4", "wav", "m4a"] }] });
  if (!result) {
    return [];
  }
  return Array.isArray(result) ? result : [result];
}

export async function chooseSubtitleFile(): Promise<string | null> {
  if (!isTauriRuntime()) {
    return null;
  }
  const result = await open({ directory: false, multiple: false, filters: [{ name: "Subtitles", extensions: ["srt"] }] });
  return Array.isArray(result) ? (result[0] ?? null) : result;
}

export async function listenForDirectoryDrops(
  handler: (event: DragDropEvent) => void,
): Promise<() => void> {
  if (!isTauriRuntime()) {
    return () => {};
  }
  return getCurrentWebview().onDragDropEvent((event) => {
    handler(event.payload);
  });
}

export function toMediaAssetUrl(path: string | null | undefined): string | null {
  if (!path || !isTauriRuntime()) {
    return null;
  }
  return convertFileSrc(path);
}
