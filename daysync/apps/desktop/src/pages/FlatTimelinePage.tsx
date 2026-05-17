import { useMemo, useState } from "react";

import { ApiError, createFlatTimeline } from "../api/client";
import type { MediaFile } from "../api/types";
import { useAppState } from "../state/AppState";

type SelectionState = Record<string, boolean>;

export function FlatTimelinePage() {
  const { state, dispatch } = useAppState();
  const [selection, setSelection] = useState<SelectionState>({});
  const [gapMs, setGapMs] = useState(1000);
  const [sortMode, setSortMode] = useState<"filename" | "created_at" | "manual">("filename");
  const [busyType, setBusyType] = useState<"video" | "audio" | null>(null);

  const videoMedia = useMemo(
    () => state.mediaFiles.filter((item) => item.media_type === "video"),
    [state.mediaFiles],
  );
  const audioMedia = useMemo(
    () => state.mediaFiles.filter((item) => item.media_type === "audio"),
    [state.mediaFiles],
  );

  function toggleSelection(mediaId: string) {
    setSelection((current) => ({ ...current, [mediaId]: !current[mediaId] }));
  }

  async function handleGenerate(mediaType: "video" | "audio", files: MediaFile[]) {
    if (!state.currentProject) {
      dispatch({
        type: "SET_NOTICE",
        payload: { tone: "error", message: "请先创建或打开项目。" },
      });
      return;
    }

    const selectedIds = files.filter((file) => selection[file.id]).map((file) => file.id);
    setBusyType(mediaType);
    try {
      const result = await createFlatTimeline(state.currentProject.id, {
        media_type: mediaType,
        media_file_ids: selectedIds,
        sort_mode: sortMode,
        gap_ms: gapMs,
      });
      dispatch({
        type: "ADD_TIMELINE",
        payload: {
          media_type: mediaType,
          flat_timeline_id: result.flat_timeline_id,
          gap_ms: gapMs,
          sort_mode: sortMode,
          items: result.items,
        },
      });
      dispatch({
        type: "SET_NOTICE",
        payload: { tone: "success", message: `${mediaType === "video" ? "视频" : "音频"} flat timeline 已生成。` },
      });
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "生成 flat timeline 失败。";
      dispatch({ type: "SET_NOTICE", payload: { tone: "error", message } });
    } finally {
      setBusyType(null);
    }
  }

  return (
    <section className="page-grid">
      <article className="panel-card">
        <header className="card-header">
          <h2>生成 flat timeline</h2>
          <span>按文件名、创建时间或手动顺序拼接素材</span>
        </header>
        <div className="inline-settings">
          <label>
            <span>排序方式</span>
            <select value={sortMode} onChange={(event) => setSortMode(event.target.value as typeof sortMode)}>
              <option value="filename">filename</option>
              <option value="created_at">created_at</option>
              <option value="manual">manual</option>
            </select>
          </label>
          <label>
            <span>gap_ms</span>
            <input
              type="number"
              min={0}
              value={gapMs}
              onChange={(event) => setGapMs(Number(event.target.value))}
            />
          </label>
        </div>
      </article>

      <MediaSelectionCard
        title="视频素材"
        files={videoMedia}
        selection={selection}
        onToggle={toggleSelection}
        busy={busyType === "video"}
        onGenerate={() => handleGenerate("video", videoMedia)}
      />

      <MediaSelectionCard
        title="外录音频"
        files={audioMedia}
        selection={selection}
        onToggle={toggleSelection}
        busy={busyType === "audio"}
        onGenerate={() => handleGenerate("audio", audioMedia)}
      />

      <article className="panel-card span-two">
        <header className="card-header">
          <h3>已生成的时间线</h3>
          <span>{state.flatTimelines.length} 条</span>
        </header>
        <div className="timeline-list">
          {state.flatTimelines.map((timeline, index) => (
            <div key={`${timeline.flat_timeline_id ?? timeline.id ?? index}`} className="timeline-card">
              <div className="timeline-card-header">
                <strong>{timeline.media_type === "video" ? "视频" : "音频"}时间线</strong>
                <span>gap {timeline.gap_ms ?? 1000} ms</span>
              </div>
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>素材</th>
                      <th>flat_start</th>
                      <th>flat_end</th>
                      <th>source_end</th>
                    </tr>
                  </thead>
                  <tbody>
                    {timeline.items.map((item, itemIndex) => (
                      <tr key={item.id ?? `${timeline.flat_timeline_id}-${itemIndex}`}>
                        <td>{item.filename ?? item.media_file_id}</td>
                        <td>{item.flat_start_ms}</td>
                        <td>{item.flat_end_ms}</td>
                        <td>{item.source_end_ms}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
      </article>
    </section>
  );
}

function MediaSelectionCard({
  title,
  files,
  selection,
  onToggle,
  busy,
  onGenerate,
}: {
  title: string;
  files: MediaFile[];
  selection: SelectionState;
  onToggle: (mediaId: string) => void;
  busy: boolean;
  onGenerate: () => void;
}) {
  const selectedCount = files.filter((file) => selection[file.id]).length;
  return (
    <article className="panel-card">
      <header className="card-header">
        <h3>{title}</h3>
        <span>已选 {selectedCount} / {files.length}</span>
      </header>
      <div className="check-list">
        {files.map((file) => (
          <label key={file.id} className="check-item">
            <input
              type="checkbox"
              checked={Boolean(selection[file.id])}
              onChange={() => onToggle(file.id)}
            />
            <span>{file.filename}</span>
            <small>{file.duration_ms} ms</small>
          </label>
        ))}
      </div>
      <button type="button" className="primary-button" disabled={!selectedCount || busy} onClick={onGenerate}>
        {busy ? "生成中..." : `生成${title}时间线`}
      </button>
    </article>
  );
}
