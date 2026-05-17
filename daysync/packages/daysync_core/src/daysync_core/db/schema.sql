PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  root_path TEXT NOT NULL,
  shooting_date TEXT,
  schema_version TEXT NOT NULL DEFAULT '0.1',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  name TEXT NOT NULL,
  start_at TEXT,
  end_at TEXT,
  notes TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS media_files (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  session_id TEXT,
  media_type TEXT NOT NULL CHECK(media_type IN ('video', 'audio')),
  original_path TEXT NOT NULL,
  filename TEXT NOT NULL,
  file_size INTEGER,
  file_hash TEXT,
  duration_ms INTEGER NOT NULL,
  container TEXT,
  has_video INTEGER NOT NULL DEFAULT 0,
  has_audio INTEGER NOT NULL DEFAULT 0,
  created_at_metadata TEXT,
  imported_at TEXT NOT NULL,
  FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
  FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_media_files_project ON media_files(project_id);
CREATE INDEX IF NOT EXISTS idx_media_files_type ON media_files(project_id, media_type);

CREATE TABLE IF NOT EXISTS media_streams (
  id TEXT PRIMARY KEY,
  media_file_id TEXT NOT NULL,
  stream_index INTEGER NOT NULL,
  stream_type TEXT NOT NULL CHECK(stream_type IN ('video', 'audio', 'subtitle', 'other')),
  codec TEXT,
  sample_rate INTEGER,
  channels INTEGER,
  width INTEGER,
  height INTEGER,
  frame_rate_num INTEGER,
  frame_rate_den INTEGER,
  duration_ms INTEGER,
  raw_json TEXT,
  FOREIGN KEY(media_file_id) REFERENCES media_files(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_media_streams_file ON media_streams(media_file_id);

CREATE TABLE IF NOT EXISTS flat_timelines (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  media_type TEXT NOT NULL CHECK(media_type IN ('video', 'audio')),
  name TEXT NOT NULL,
  gap_ms INTEGER NOT NULL DEFAULT 1000,
  sort_mode TEXT NOT NULL DEFAULT 'filename',
  created_at TEXT NOT NULL,
  FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_flat_timelines_project ON flat_timelines(project_id);

CREATE TABLE IF NOT EXISTS flat_timeline_items (
  id TEXT PRIMARY KEY,
  flat_timeline_id TEXT NOT NULL,
  media_file_id TEXT NOT NULL,
  item_index INTEGER NOT NULL,
  flat_start_ms INTEGER NOT NULL,
  flat_end_ms INTEGER NOT NULL,
  source_start_ms INTEGER NOT NULL DEFAULT 0,
  source_end_ms INTEGER NOT NULL,
  gap_after_ms INTEGER NOT NULL DEFAULT 1000,
  FOREIGN KEY(flat_timeline_id) REFERENCES flat_timelines(id) ON DELETE CASCADE,
  FOREIGN KEY(media_file_id) REFERENCES media_files(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_flat_items_timeline ON flat_timeline_items(flat_timeline_id, item_index);
CREATE INDEX IF NOT EXISTS idx_flat_items_time ON flat_timeline_items(flat_timeline_id, flat_start_ms, flat_end_ms);

CREATE TABLE IF NOT EXISTS subtitle_tracks (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  flat_timeline_id TEXT NOT NULL,
  track_type TEXT NOT NULL CHECK(track_type IN ('video_ref', 'external_audio')),
  source_type TEXT NOT NULL CHECK(source_type IN ('srt_import', 'vtt_import', 'json_import', 'local_asr')),
  language TEXT,
  original_path TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
  FOREIGN KEY(flat_timeline_id) REFERENCES flat_timelines(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_subtitle_tracks_project ON subtitle_tracks(project_id, track_type);

CREATE TABLE IF NOT EXISTS subtitles (
  subtitle_pk INTEGER PRIMARY KEY AUTOINCREMENT,
  id TEXT NOT NULL UNIQUE,
  track_id TEXT NOT NULL,
  subtitle_index INTEGER NOT NULL,
  flat_start_ms INTEGER NOT NULL,
  flat_end_ms INTEGER NOT NULL,
  source_media_file_id TEXT,
  source_start_ms INTEGER,
  source_end_ms INTEGER,
  raw_text TEXT NOT NULL,
  normalized_text TEXT NOT NULL,
  asr_confidence REAL,
  mapping_status TEXT NOT NULL DEFAULT 'ok' CHECK(mapping_status IN ('ok', 'warning', 'failed')),
  mapping_warning TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY(track_id) REFERENCES subtitle_tracks(id) ON DELETE CASCADE,
  FOREIGN KEY(source_media_file_id) REFERENCES media_files(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_subtitles_track ON subtitles(track_id, subtitle_index);
CREATE INDEX IF NOT EXISTS idx_subtitles_source_media ON subtitles(source_media_file_id, source_start_ms);
CREATE INDEX IF NOT EXISTS idx_subtitles_time ON subtitles(track_id, flat_start_ms, flat_end_ms);

CREATE VIRTUAL TABLE IF NOT EXISTS subtitles_fts USING fts5(
  raw_text,
  normalized_text,
  content='subtitles',
  content_rowid='subtitle_pk'
);

CREATE TRIGGER IF NOT EXISTS subtitles_ai AFTER INSERT ON subtitles BEGIN
  INSERT INTO subtitles_fts(rowid, raw_text, normalized_text)
  VALUES (new.subtitle_pk, new.raw_text, new.normalized_text);
END;

CREATE TRIGGER IF NOT EXISTS subtitles_ad AFTER DELETE ON subtitles BEGIN
  INSERT INTO subtitles_fts(subtitles_fts, rowid, raw_text, normalized_text)
  VALUES('delete', old.subtitle_pk, old.raw_text, old.normalized_text);
END;

CREATE TRIGGER IF NOT EXISTS subtitles_au AFTER UPDATE ON subtitles BEGIN
  INSERT INTO subtitles_fts(subtitles_fts, rowid, raw_text, normalized_text)
  VALUES('delete', old.subtitle_pk, old.raw_text, old.normalized_text);
  INSERT INTO subtitles_fts(rowid, raw_text, normalized_text)
  VALUES (new.subtitle_pk, new.raw_text, new.normalized_text);
END;

CREATE TABLE IF NOT EXISTS sync_results (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  session_id TEXT,
  video_media_file_id TEXT NOT NULL,
  audio_media_file_id TEXT NOT NULL,
  video_in_ms INTEGER NOT NULL,
  video_out_ms INTEGER NOT NULL,
  audio_in_ms INTEGER NOT NULL,
  audio_out_ms INTEGER NOT NULL,
  offset_ms INTEGER NOT NULL,
  drift_ppm REAL,
  confidence_score REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL CHECK(status IN ('candidate', 'accepted_manual', 'accepted_auto', 'rejected', 'needs_review')),
  source TEXT NOT NULL CHECK(source IN ('manual_anchor', 'auto_text', 'auto_audio', 'imported')),
  video_anchor_subtitle_id TEXT,
  audio_anchor_subtitle_id TEXT,
  confidence_breakdown_json TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
  FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE SET NULL,
  FOREIGN KEY(video_media_file_id) REFERENCES media_files(id) ON DELETE CASCADE,
  FOREIGN KEY(audio_media_file_id) REFERENCES media_files(id) ON DELETE CASCADE,
  FOREIGN KEY(video_anchor_subtitle_id) REFERENCES subtitles(id) ON DELETE SET NULL,
  FOREIGN KEY(audio_anchor_subtitle_id) REFERENCES subtitles(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_sync_results_project ON sync_results(project_id, status);
CREATE INDEX IF NOT EXISTS idx_sync_results_video ON sync_results(video_media_file_id);
CREATE INDEX IF NOT EXISTS idx_sync_results_audio ON sync_results(audio_media_file_id);

CREATE TABLE IF NOT EXISTS review_events (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  sync_result_id TEXT NOT NULL,
  event_type TEXT NOT NULL CHECK(event_type IN ('accepted', 'rejected', 'adjusted', 'commented')),
  old_offset_ms INTEGER,
  new_offset_ms INTEGER,
  note TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
  FOREIGN KEY(sync_result_id) REFERENCES sync_results(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_review_events_result ON review_events(sync_result_id, created_at);

CREATE TABLE IF NOT EXISTS export_jobs (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  export_type TEXT NOT NULL CHECK(export_type IN ('csv', 'fcp7_xml', 'fcpxml', 'otio', 'json')),
  output_path TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('pending', 'running', 'succeeded', 'failed')),
  row_count INTEGER,
  error_message TEXT,
  created_at TEXT NOT NULL,
  completed_at TEXT,
  FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS project_settings (
  project_id TEXT PRIMARY KEY,
  settings_json TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);
