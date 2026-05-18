import {
  createContext,
  type Dispatch,
  type PropsWithChildren,
  useContext,
  useMemo,
  useReducer,
} from "react";

import type {
  FlatTimeline,
  MediaFile,
  Project,
  ProjectSettings,
  ProjectSnapshot,
  ProjectStats,
  SearchResults,
  SyncResult,
} from "../api/types";

export type HealthState = "idle" | "checking" | "ready" | "error";

export type Notice = {
  tone: "neutral" | "success" | "error";
  message: string;
};

export type AppState = {
  healthState: HealthState;
  healthMessage: string;
  currentProject: Project | null;
  projectSettings: ProjectSettings | null;
  stats: ProjectStats | null;
  mediaFiles: MediaFile[];
  flatTimelines: FlatTimeline[];
  syncResults: SyncResult[];
  searchResults: SearchResults | null;
  selectedVideoSubtitleId: string | null;
  selectedAudioSubtitleId: string | null;
  lastOffsetMs: number | null;
  notice: Notice | null;
};

export const initialState: AppState = {
  healthState: "idle",
  healthMessage: "等待连接本地运行时",
  currentProject: null,
  projectSettings: null,
  stats: null,
  mediaFiles: [],
  flatTimelines: [],
  syncResults: [],
  searchResults: null,
  selectedVideoSubtitleId: null,
  selectedAudioSubtitleId: null,
  lastOffsetMs: null,
  notice: null,
};

export type AppAction =
  | { type: "SET_HEALTH"; payload: { state: HealthState; message: string } }
  | { type: "HYDRATE_PROJECT"; payload: ProjectSnapshot }
  | { type: "SET_NOTICE"; payload: Notice | null }
  | { type: "SET_PROJECT_SETTINGS"; payload: ProjectSettings }
  | { type: "MERGE_MEDIA"; payload: MediaFile[] }
  | { type: "ADD_TIMELINE"; payload: FlatTimeline }
  | { type: "SET_SEARCH_RESULTS"; payload: SearchResults | null }
  | { type: "SELECT_VIDEO_SUBTITLE"; payload: string | null }
  | { type: "SELECT_AUDIO_SUBTITLE"; payload: string | null }
  | { type: "ADD_SYNC_RESULT"; payload: SyncResult }
  | { type: "SET_SYNC_RESULTS"; payload: SyncResult[] };

export function appReducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case "SET_HEALTH":
      return {
        ...state,
        healthState: action.payload.state,
        healthMessage: action.payload.message,
      };
    case "HYDRATE_PROJECT":
      return {
        ...state,
        currentProject: action.payload.project,
        projectSettings: action.payload.project_settings,
        stats: action.payload.stats,
        mediaFiles: action.payload.media_files,
        flatTimelines: action.payload.flat_timelines.map((timeline) => ({
          ...timeline,
          flat_timeline_id: timeline.id ?? timeline.flat_timeline_id,
        })),
        syncResults: action.payload.sync_results,
        searchResults: null,
        selectedVideoSubtitleId: null,
        selectedAudioSubtitleId: null,
        lastOffsetMs: null,
      };
    case "SET_NOTICE":
      return { ...state, notice: action.payload };
    case "SET_PROJECT_SETTINGS":
      return { ...state, projectSettings: action.payload };
    case "MERGE_MEDIA": {
      const mediaById = new Map(state.mediaFiles.map((item) => [item.id, item]));
      action.payload.forEach((item) => mediaById.set(item.id, item));
      return { ...state, mediaFiles: Array.from(mediaById.values()) };
    }
    case "ADD_TIMELINE":
      return {
        ...state,
        flatTimelines: [...state.flatTimelines, action.payload],
      };
    case "SET_SEARCH_RESULTS":
      return {
        ...state,
        searchResults: action.payload,
        selectedVideoSubtitleId: null,
        selectedAudioSubtitleId: null,
      };
    case "SELECT_VIDEO_SUBTITLE":
      return { ...state, selectedVideoSubtitleId: action.payload };
    case "SELECT_AUDIO_SUBTITLE":
      return { ...state, selectedAudioSubtitleId: action.payload };
    case "ADD_SYNC_RESULT":
      return {
        ...state,
        syncResults: [action.payload, ...state.syncResults],
        lastOffsetMs: action.payload.offset_ms,
      };
    case "SET_SYNC_RESULTS":
      return {
        ...state,
        syncResults: action.payload,
        lastOffsetMs: action.payload[0]?.offset_ms ?? state.lastOffsetMs,
      };
    default:
      return state;
  }
}

type AppStateContextValue = {
  state: AppState;
  dispatch: Dispatch<AppAction>;
};

const AppStateContext = createContext<AppStateContextValue | null>(null);

export function AppStateProvider({ children }: PropsWithChildren) {
  const [state, dispatch] = useReducer(appReducer, initialState);
  const value = useMemo(() => ({ state, dispatch }), [state]);
  return <AppStateContext.Provider value={value}>{children}</AppStateContext.Provider>;
}

export function useAppState(): AppStateContextValue {
  const value = useContext(AppStateContext);
  if (!value) {
    throw new Error("useAppState must be used within AppStateProvider");
  }
  return value;
}
