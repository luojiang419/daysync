import { invoke } from "@tauri-apps/api/core";
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

export async function ensureDevApi(): Promise<boolean> {
  if (!isTauriRuntime()) {
    return false;
  }
  return invoke<boolean>("ensure_dev_api");
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
