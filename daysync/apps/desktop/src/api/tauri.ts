import { convertFileSrc, invoke } from "@tauri-apps/api/core";
import type { DragDropEvent } from "@tauri-apps/api/webview";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import { open } from "@tauri-apps/plugin-dialog";

declare global {
  interface Window {
    __TAURI_INTERNALS__?: {
      invoke?: unknown;
    };
  }
}

const TAURI_IPC_WAIT_TIMEOUT_MS = 4000;
const TAURI_IPC_WAIT_INTERVAL_MS = 50;
const RUNTIME_RETRY_ATTEMPTS = 5;
const RUNTIME_RETRY_DELAY_MS = 250;

export function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && typeof window.__TAURI_INTERNALS__?.invoke === "function";
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

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => globalThis.setTimeout(resolve, ms));
}

function toRuntimeUnavailableError(error: unknown): RuntimeInvocationError {
  if (error instanceof RuntimeInvocationError) {
    return error;
  }
  return new RuntimeInvocationError(
    "RUNTIME_UNAVAILABLE",
    "未能连接本地运行时，请稍后重试。",
    { cause: error instanceof Error ? error.message : String(error) },
  );
}

function shouldRetryRuntimeError(error: unknown): boolean {
  if (error instanceof RuntimeInvocationError) {
    return error.code === "RUNTIME_UNAVAILABLE";
  }
  const message = error instanceof Error ? error.message : String(error);
  return message.includes("__TAURI_INTERNALS__") || message.includes("invoke");
}

async function waitForTauriIpc(): Promise<void> {
  const deadline = Date.now() + TAURI_IPC_WAIT_TIMEOUT_MS;

  while (!isTauriRuntime()) {
    if (Date.now() >= deadline) {
      throw new RuntimeInvocationError(
        "RUNTIME_UNAVAILABLE",
        "当前环境不是 DaySync 桌面版，本地运行时不可用。",
        { waited_ms: TAURI_IPC_WAIT_TIMEOUT_MS },
      );
    }
    await sleep(TAURI_IPC_WAIT_INTERVAL_MS);
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

async function executeRuntimeCommand<T>(
  command: "ensure_runtime_ready" | "invoke_runtime",
  payload?: Record<string, unknown>,
): Promise<T> {
  await waitForTauriIpc();

  let lastError: unknown = null;
  for (let attempt = 0; attempt < RUNTIME_RETRY_ATTEMPTS; attempt += 1) {
    try {
      const response = await invoke<RuntimeCommandResponse<T>>(command, payload);
      return unwrapRuntimeResponse(response);
    } catch (error) {
      lastError = error;
      if (!shouldRetryRuntimeError(error) || attempt === RUNTIME_RETRY_ATTEMPTS - 1) {
        throw toRuntimeUnavailableError(error);
      }
      await sleep(RUNTIME_RETRY_DELAY_MS);
    }
  }

  throw toRuntimeUnavailableError(lastError);
}

export async function ensureRuntimeReady<T>(): Promise<T> {
  return executeRuntimeCommand<T>("ensure_runtime_ready");
}

export async function invokeRuntime<T>(
  method: string,
  payload: Record<string, unknown> = {},
): Promise<T> {
  return executeRuntimeCommand<T>("invoke_runtime", { method, payload });
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
