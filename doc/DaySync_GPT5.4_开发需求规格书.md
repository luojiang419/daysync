# DaySync 全自动合板系统｜GPT5.4 开发需求规格书

**文档版本：** v2.0 / GPT5.4 Development Ready Spec  
**生成日期：** 2026-05-17  
**适用对象：** GPT5.4 / Codex / Cursor / Claude Code 等代码生成模型  
**源文档：** 《全自动合板系统商业软件设计方案 v1.0》与《v1.1 优化版》  
**产品暂定名：** DaySync / 字幕合板助手 / 全自动合板系统  
**核心定位：** 置信度驱动的自动合板与字幕锚点同步系统。

---

## 0. 给代码模型的执行规则

本规格书的目标不是做商业介绍，而是让代码模型可以稳定、准确地生成软件。后续开发时必须遵守：

1. **以本文件为唯一需求源。** 不要根据常识擅自扩展需求。
2. **先实现 MVP，再实现增强功能。** 本地 ASR、音频指纹、完整自动合板、FCPXML、团队协作不属于 MVP 0.1。
3. **所有时间统一使用整数毫秒 `*_ms`。** 不要在数据库主字段中使用浮点秒，避免帧级/毫秒级误差累积。
4. **所有业务实体使用 UUID 字符串作为外部 ID。** SQLite 可以使用自增主键优化 FTS，但 API 层只暴露 UUID。
5. **所有文件路径必须支持中文、空格、特殊字符。** 使用 UTF-8，禁止手写 shell 字符串拼接。
6. **媒体分析必须通过 `ffprobe` / `ffmpeg` 抽象层。** 不允许 UI 直接调用 FFmpeg。
7. **自动合板不得只依赖字幕文本。** 自动通过必须同时满足硬门槛、负证据检查和综合评分。
8. **导出优先保证 CSV 正确。** XML/FCPXML 在 MVP 中不是首要目标。
9. **每个模块必须有单元测试。** 尤其是时间映射、SRT 解析、字幕搜索、offset 聚类。
10. **任何不确定匹配必须进入复核队列。** 不允许低置信度结果自动写入最终导出。

---

## 1. 产品目标与非目标

### 1.1 产品目标

DaySync 是一个本地优先的桌面软件，用于帮助纪录片、采访、综艺、短片、长期跟拍项目在没有统一时间码、没有时码器、视频参考音质量不稳定的情况下，完成视频素材与外录音频素材的合板。

系统通过以下链路工作：

```text
导入视频/音频素材
→ 生成视频平铺时间线和音频平铺时间线
→ 导入或生成字幕
→ 把平铺字幕时间映射回原始素材
→ 搜索字幕锚点
→ 手动或自动计算视频与外录音频 offset
→ 生成 sync result
→ 复核
→ 导出 CSV / XML
```

### 1.2 MVP 0.1 必须完成的目标

MVP 0.1 只证明“字幕锚点合板”成立，范围必须收敛：

```text
必须实现：
- 新建项目 / 拍摄日工程
- 导入视频文件和音频文件元数据
- 生成 flat timeline manifest
- 导入 video_flat.srt 和 audio_flat.srt
- 字幕时间映射回原始素材
- 统一搜索视频字幕和音频字幕
- 用户手动选择一条视频字幕与一条音频字幕
- 计算 offset
- 保存 sync result
- 导出 sync_report.csv
```

### 1.3 MVP 0.1 明确不做

```text
不做：
- 本地 ASR 推理
- 音频指纹
- 波形互相关精对齐
- 完整自动合板
- FCPXML 导出
- 团队协作
- 云端队列
- 模型训练
- 权限系统
```

### 1.4 后续版本目标

| 版本 | 目标 | 核心能力 |
|---|---|---|
| MVP 0.1 | 字幕锚点合板验证 | 导入 SRT、时间映射、手动锚点、CSV |
| MVP 0.2 | 半自动候选推荐 | 上下文窗口、相似度搜索、top candidates |
| MVP 0.3 | 复核队列 | 候选评分、接受/拒绝/微调、复核 UI |
| MVP 0.4 | 基础自动合板 | 多锚点 offset 聚类、正反向验证、自动通过 |
| v1.0 | 专业可用版 | FCP 7 XML、基础波形/VAD、项目恢复 |
| v1.5 | 商业增强版 | 本地 ASR、多模型、音频指纹、漂移检测 |

---

## 2. 推荐技术栈与代码仓库结构

为了减少模型开发时的歧义，本规格书固定 MVP 技术栈如下。

### 2.1 技术栈

```text
Desktop Shell: Tauri v2
Frontend: React + TypeScript + Vite
Backend Engine: Python 3.11+
Backend API: FastAPI local service
Database: SQLite + WAL + FTS5
Media Tools: FFmpeg / ffprobe
Testing: pytest + Vitest
Package Manager: uv 或 poetry for Python, pnpm for frontend
```

说明：

- 算法和媒体处理先用 Python 实现，便于快速验证。
- Tauri 只负责桌面壳和前端 UI，不直接处理媒体算法。
- FastAPI 运行在本地 `127.0.0.1`，由桌面应用启动和管理。
- 后续商业版可逐步把高性能模块迁移到 Rust。

### 2.2 推荐仓库结构

```text
daysync/
├── README.md
├── pyproject.toml
├── package.json
├── apps/
│   └── desktop/
│       ├── src/
│       │   ├── main.tsx
│       │   ├── api/
│       │   ├── components/
│       │   ├── pages/
│       │   └── state/
│       ├── src-tauri/
│       └── tests/
├── services/
│   └── api/
│       ├── main.py
│       ├── routes/
│       └── schemas/
├── packages/
│   └── daysync_core/
│       ├── __init__.py
│       ├── db/
│       ├── media/
│       ├── timeline/
│       ├── subtitles/
│       ├── search/
│       ├── sync/
│       ├── export/
│       └── tests/
├── docs/
├── sample_data/
└── scripts/
```

---

## 3. 领域词汇表

| 术语 | 英文标识 | 定义 |
|---|---|---|
| 项目 | Project | 一个 DaySync 工程，通常对应一个片子或一个客户项目。 |
| 拍摄日 | Shooting Day | 一个拍摄日期，不等同于文件创建自然日。 |
| Session | Session | 拍摄日下的工作单元，例如上午采访、夜戏、多机位段落。 |
| 视频素材 | Video Media | 相机拍摄的视频文件，通常包含机内参考音。 |
| 外录音频 | External Audio | 录音机录制的高质量音频文件。 |
| 平铺时间线 | Flat Timeline | 把多个素材按顺序拼接成一条连续时间线，用于 ASR 和字幕映射。 |
| 平铺时间 | Flat Time | 某条平铺时间线上的时间，单位毫秒。 |
| 素材内时间 | Source Time | 原始媒体文件内部时间，单位毫秒。 |
| 字幕轨 | Subtitle Track | 来自 SRT/VTT/ASR 的字幕集合。 |
| 字幕锚点 | Subtitle Anchor | 可用于定位同步关系的一条或多条字幕上下文。 |
| Offset | Offset | 外录音频时间 - 视频时间，单位毫秒。 |
| Sync Candidate | SyncCandidate | 系统推测的一个视频/音频同步候选。 |
| Sync Result | SyncResult | 用户接受或系统高置信自动通过后的同步结果。 |
| 复核事件 | ReviewEvent | 用户接受、拒绝、微调同步候选的记录。 |

---

## 4. 用户故事与验收标准

### US-001 新建项目

**作为** 剪辑师，  
**我希望** 新建一个本地 DaySync 项目，  
**以便** 管理某个拍摄日或素材批次。

验收标准：

```gherkin
Given 用户选择一个空文件夹
When 用户创建项目并输入项目名与拍摄日期
Then 系统应创建 daysync.project.json
And 系统应创建 daysync.sqlite
And 数据库应启用 WAL 和 foreign_keys
And 项目可以关闭后重新打开
```

### US-002 导入媒体文件

验收标准：

```gherkin
Given 用户已有一个项目
When 用户导入 mov/mp4/wav 文件
Then 系统应调用 ffprobe 读取 duration、stream、codec、sample_rate、frame_rate
And 系统应把文件记录写入 media_files
And 系统应把流信息写入 media_streams
And 不应移动或修改原始素材
```

### US-003 生成平铺时间线

验收标准：

```gherkin
Given 项目中有多个视频素材
When 用户点击生成视频平铺时间线
Then 系统应按 sort_mode 排序素材
And 每个素材之间插入 gap_ms
And 系统应写入 flat_timelines 和 flat_timeline_items
And 每个 item 都应记录 flat_start_ms、flat_end_ms、source_start_ms、source_end_ms
```

### US-004 导入 SRT 并映射回原素材

验收标准：

```gherkin
Given 已存在 flat_timeline_items
When 用户导入 video_flat.srt
Then 系统应解析字幕时间
And 根据 flat_start_ms / flat_end_ms 找到字幕所属素材
And 写入 subtitles.source_media_file_id
And 写入 source_start_ms / source_end_ms
And 如果字幕跨越素材边界或 gap 区域，应标记 mapping_status = warning
```

### US-005 统一字幕搜索

验收标准：

```gherkin
Given 项目中已有视频字幕和音频字幕
When 用户搜索一句话
Then 系统应同时返回 video track 和 audio track 的命中结果
And 每条结果包含 raw_text、source_media_file_id、source_start_ms、flat_start_ms
And 结果按 relevance_score 降序排列
```

### US-006 手动锚点计算 offset

验收标准：

```gherkin
Given 用户选择一条视频字幕和一条音频字幕
When 用户点击一键对齐
Then 系统应计算 offset_ms = audio.source_start_ms - video.source_start_ms
And 创建 sync_result
And sync_result.status = accepted_manual
And 可以导出到 sync_report.csv
```

---

## 5. 核心数据模型

### 5.1 数据建模原则

```text
1. API 层所有 ID 使用 UUID 字符串。
2. 时间字段统一使用整数毫秒。
3. flat timeline 与 source media 必须可以双向映射。
4. 字幕原文 raw_text 和规范化 normalized_text 必须同时保存。
5. sync result 必须支持片段级同步，不只保存整条素材 offset。
6. 用户每一次接受、拒绝、微调都必须记录为 review_event。
```

### 5.2 Project

```ts
type Project = {
  id: string;
  name: string;
  root_path: string;
  shooting_date?: string; // YYYY-MM-DD
  created_at: string;
  updated_at: string;
  schema_version: string;
};
```

### 5.3 MediaFile

```ts
type MediaFile = {
  id: string;
  project_id: string;
  session_id?: string;
  media_type: "video" | "audio";
  original_path: string;
  filename: string;
  file_size: number;
  file_hash?: string;
  duration_ms: number;
  container?: string;
  has_video: boolean;
  has_audio: boolean;
  imported_at: string;
};
```

### 5.4 FlatTimelineItem

```ts
type FlatTimelineItem = {
  id: string;
  flat_timeline_id: string;
  media_file_id: string;
  item_index: number;
  flat_start_ms: number;
  flat_end_ms: number;
  source_start_ms: number; // MVP 默认 0
  source_end_ms: number;   // 默认 media.duration_ms
  gap_after_ms: number;
};
```

### 5.5 Subtitle

```ts
type Subtitle = {
  id: string;
  track_id: string;
  subtitle_index: number;
  flat_start_ms: number;
  flat_end_ms: number;
  source_media_file_id?: string;
  source_start_ms?: number;
  source_end_ms?: number;
  raw_text: string;
  normalized_text: string;
  asr_confidence?: number;
  mapping_status: "ok" | "warning" | "failed";
  mapping_warning?: string;
};
```

### 5.6 SyncResult

MVP 0.1 可以先用单片段结果，但字段必须预留片段级同步能力。

```ts
type SyncResult = {
  id: string;
  project_id: string;
  session_id?: string;
  video_media_file_id: string;
  audio_media_file_id: string;
  video_in_ms: number;
  video_out_ms: number;
  audio_in_ms: number;
  audio_out_ms: number;
  offset_ms: number;
  drift_ppm?: number;
  confidence_score: number;
  status: "candidate" | "accepted_manual" | "accepted_auto" | "rejected" | "needs_review";
  source: "manual_anchor" | "auto_text" | "auto_audio" | "imported";
  video_anchor_subtitle_id?: string;
  audio_anchor_subtitle_id?: string;
  created_at: string;
  updated_at: string;
};
```

---

## 6. 核心算法规格

### 6.1 生成平铺时间线

输入：

```ts
type GenerateFlatTimelineRequest = {
  project_id: string;
  media_type: "video" | "audio";
  media_file_ids: string[];
  sort_mode: "filename" | "created_at" | "manual";
  gap_ms: number; // 默认 1000
};
```

算法：

```text
1. 根据 media_file_ids 和 sort_mode 得到素材顺序。
2. current_ms = 0。
3. 对每个 media_file：
   a. flat_start_ms = current_ms
   b. flat_end_ms = flat_start_ms + media.duration_ms
   c. 写入 flat_timeline_item
   d. current_ms = flat_end_ms + gap_ms
4. 返回 flat_timeline_id 和 items。
```

边界条件：

```text
- duration_ms 为空或 <= 0：拒绝生成，返回 MEDIA_DURATION_INVALID。
- media_type 不一致：拒绝生成，返回 MEDIA_TYPE_MISMATCH。
- gap_ms 不能小于 0。
```

### 6.2 字幕时间映射

输入：SRT 字幕条目：

```text
subtitle.flat_start_ms
subtitle.flat_end_ms
```

映射规则：

```text
找到 item，使：
item.flat_start_ms <= subtitle.flat_start_ms < item.flat_end_ms

source_start_ms = subtitle.flat_start_ms - item.flat_start_ms + item.source_start_ms
source_end_ms = subtitle.flat_end_ms - item.flat_start_ms + item.source_start_ms
```

警告规则：

```text
如果 subtitle.flat_end_ms > item.flat_end_ms：
  mapping_status = warning
  mapping_warning = "subtitle_crosses_media_boundary"

如果 subtitle 落在 gap 区间：
  mapping_status = warning
  mapping_warning = "subtitle_in_gap"

如果找不到 item：
  mapping_status = failed
  mapping_warning = "no_matching_flat_item"
```

### 6.3 文本规范化

目标：提高中文 ASR 文本容错搜索能力。

规范化步骤：

```text
1. 转小写。
2. 去除标点符号。
3. 去除多余空格。
4. 全角转半角。
5. 简繁转换，MVP 可以先预留接口。
6. 数字归一化，MVP 可以先保留原样。
7. 常见语气词可以降权，但不要直接删除原文。
```

函数签名：

```py
def normalize_subtitle_text(text: str) -> str:
    ...
```

必须测试：

```text
"我当时，就觉着这地方不对。" → "我当时就觉着这地方不对"
"  Hello，世界！ " → "hello世界"
```

### 6.4 字幕搜索

MVP 搜索策略：

```text
1. 使用 SQLite FTS5 搜索 normalized_text。
2. 如果 FTS 无结果，使用 LIKE fallback。
3. 返回前 20 条。
4. 同时搜索 video subtitle track 和 audio subtitle track。
```

返回字段：

```ts
type SubtitleSearchResult = {
  subtitle_id: string;
  track_type: "video_ref" | "external_audio";
  raw_text: string;
  normalized_text: string;
  source_media_file_id?: string;
  source_start_ms?: number;
  source_end_ms?: number;
  flat_start_ms: number;
  flat_end_ms: number;
  relevance_score: number;
};
```

### 6.5 手动锚点 offset 计算

输入：

```ts
type ManualSyncRequest = {
  project_id: string;
  video_subtitle_id: string;
  audio_subtitle_id: string;
};
```

计算：

```text
offset_ms = audio_subtitle.source_start_ms - video_subtitle.source_start_ms
video_in_ms = 0
audio_in_ms = offset_ms
```

如果 `offset_ms < 0`，说明外录音频锚点早于视频锚点，导出时需要对视频或音频入点做裁切处理。MVP 只保存结果，不强制生成 XML。

### 6.6 多锚点 offset 聚类，MVP 0.4

输入：多个 anchor pair 产生的 offset_ms 列表。

算法：

```text
1. 对 offsets 排序。
2. 使用 median 作为中心。
3. 计算每个 offset 与 median 的绝对偏差。
4. inliers = 偏差 <= tolerance_ms 的 offsets。
5. 如果 inlier_ratio >= min_inlier_ratio，则聚类通过。
6. final_offset_ms = median(inliers)。
```

默认参数：

```text
tolerance_ms = 500
min_inlier_ratio = 0.6
min_anchor_count = 3
```

### 6.7 两阶段置信度策略，MVP 0.4+

自动通过必须满足硬门槛：

```text
- 正反向候选一致。
- 至少 3 个锚点支持同一 offset cluster。
- 第一候选分数明显高于第二候选。
- 没有强负证据。
```

强负证据：

```text
- offset 分散严重。
- 同一句字幕当天出现多次且上下文不唯一。
- 字幕跨越多个素材边界。
- 视频参考音质量过低且无音频证据。
- 同一个视频被多个互相冲突的音频片段匹配。
```

综合评分字段：

```ts
type ConfidenceBreakdown = {
  text_similarity: number;
  context_similarity: number;
  offset_cluster_stability: number;
  reverse_match_consistency: number;
  candidate_margin: number;
  vad_similarity?: number;
  waveform_similarity?: number;
  negative_evidence_count: number;
  final_score: number;
};
```

---

## 7. API 契约

### 7.1 创建项目

`POST /api/projects`

Request:

```json
{
  "name": "纪录片样片 2026-01-01",
  "root_path": "/Users/me/DaySyncProjects/docu-2026-01-01",
  "shooting_date": "2026-01-01"
}
```

Response:

```json
{
  "project": {
    "id": "uuid",
    "name": "纪录片样片 2026-01-01",
    "root_path": "/Users/me/DaySyncProjects/docu-2026-01-01",
    "shooting_date": "2026-01-01"
  }
}
```

### 7.2 导入媒体

`POST /api/projects/{project_id}/media/import`

Request:

```json
{
  "paths": ["/media/A001_C001.mov", "/media/ZOOM0001.wav"],
  "session_id": null
}
```

Response:

```json
{
  "imported": [
    {
      "id": "uuid",
      "media_type": "video",
      "filename": "A001_C001.mov",
      "duration_ms": 123456,
      "has_video": true,
      "has_audio": true
    }
  ],
  "failed": []
}
```

### 7.3 生成平铺时间线

`POST /api/projects/{project_id}/flat-timelines`

Request:

```json
{
  "media_type": "video",
  "media_file_ids": ["uuid1", "uuid2"],
  "sort_mode": "filename",
  "gap_ms": 1000
}
```

Response:

```json
{
  "flat_timeline_id": "uuid",
  "items": [
    {
      "media_file_id": "uuid1",
      "flat_start_ms": 0,
      "flat_end_ms": 10000,
      "source_start_ms": 0,
      "source_end_ms": 10000
    }
  ]
}
```

### 7.4 导入字幕

`POST /api/projects/{project_id}/subtitles/import`

Request:

```json
{
  "flat_timeline_id": "uuid",
  "track_type": "video_ref",
  "source_type": "srt_import",
  "path": "/subtitles/video_flat.srt",
  "language": "zh-CN"
}
```

Response:

```json
{
  "track_id": "uuid",
  "imported_count": 120,
  "warning_count": 2,
  "failed_count": 0
}
```

### 7.5 搜索字幕

`GET /api/projects/{project_id}/subtitles/search?q=关键词&limit=20`

Response:

```json
{
  "query": "关键词",
  "video_results": [],
  "audio_results": []
}
```

### 7.6 手动同步

`POST /api/projects/{project_id}/sync/manual-anchor`

Request:

```json
{
  "video_subtitle_id": "uuid-video-subtitle",
  "audio_subtitle_id": "uuid-audio-subtitle"
}
```

Response:

```json
{
  "sync_result": {
    "id": "uuid",
    "offset_ms": 574180,
    "status": "accepted_manual",
    "confidence_score": 1.0
  }
}
```

### 7.7 导出 CSV

`POST /api/projects/{project_id}/exports/csv`

Request:

```json
{
  "output_path": "/exports/sync_report.csv"
}
```

Response:

```json
{
  "output_path": "/exports/sync_report.csv",
  "row_count": 12
}
```

---

## 8. UI 页面规格

### 8.1 页面结构

MVP 前端只需要四个主页面：

```text
1. ProjectHomePage
2. MediaImportPage
3. FlatTimelinePage
4. SubtitleSearchAndSyncPage
5. ExportPage
```

### 8.2 ProjectHomePage

功能：

```text
- 创建项目
- 打开已有项目
- 显示项目路径、拍摄日期、素材数量、字幕数量、同步结果数量
```

### 8.3 MediaImportPage

功能：

```text
- 选择视频/音频文件
- 展示导入状态
- 展示媒体元数据
- 显示错误：不支持格式、读取失败、duration 缺失
```

### 8.4 FlatTimelinePage

功能：

```text
- 选择视频素材生成 video flat timeline
- 选择音频素材生成 audio flat timeline
- 设置排序方式和 gap_ms
- 展示每个 item 的 flat_start_ms、flat_end_ms、source filename
```

### 8.5 SubtitleSearchAndSyncPage

功能：

```text
- 导入 video_flat.srt
- 导入 audio_flat.srt
- 顶部统一搜索框
- 左侧显示视频字幕结果
- 右侧显示音频字幕结果
- 用户选择左右各一条字幕后点击“一键对齐”
- 显示 offset_ms
- 保存 sync result
```

### 8.6 ExportPage

功能：

```text
- 显示 sync_results 表格
- 导出 sync_report.csv
- 显示导出路径和导出时间
```

---

## 9. CSV 导出规格

`sync_report.csv` 必须包含以下列：

```csv
sync_result_id,status,source,confidence_score,video_file,video_in_ms,video_out_ms,audio_file,audio_in_ms,audio_out_ms,offset_ms,video_anchor_text,audio_anchor_text,created_at
```

示例：

```csv
sync_result_id,status,source,confidence_score,video_file,video_in_ms,video_out_ms,audio_file,audio_in_ms,audio_out_ms,offset_ms,video_anchor_text,audio_anchor_text,created_at
abc,accepted_manual,manual_anchor,1.0,A001_C001.mov,0,123456,ZOOM0001.wav,574180,697636,574180,我们到了这里,我们到了这里,2026-05-17T10:00:00Z
```

---

## 10. 错误码规范

| 错误码 | HTTP 状态 | 含义 |
|---|---:|---|
| PROJECT_NOT_FOUND | 404 | 项目不存在 |
| PROJECT_PATH_INVALID | 400 | 项目路径不可写或不存在 |
| MEDIA_FILE_NOT_FOUND | 404 | 媒体文件不存在 |
| MEDIA_TYPE_MISMATCH | 400 | 媒体类型不匹配 |
| MEDIA_DURATION_INVALID | 400 | 媒体时长无效 |
| FFMPEG_NOT_FOUND | 500 | 找不到 ffmpeg/ffprobe |
| SUBTITLE_PARSE_FAILED | 400 | 字幕解析失败 |
| SUBTITLE_MAPPING_FAILED | 400 | 字幕无法映射到平铺时间线 |
| ANCHOR_SUBTITLE_INVALID | 400 | 用户选择的锚点字幕无效 |
| SYNC_RESULT_NOT_FOUND | 404 | 同步结果不存在 |
| EXPORT_FAILED | 500 | 导出失败 |

错误响应格式：

```json
{
  "error": {
    "code": "SUBTITLE_PARSE_FAILED",
    "message": "Failed to parse SRT file at line 32",
    "details": {}
  }
}
```

---

## 11. 模块拆分与职责边界

### 11.1 `daysync_core.media`

职责：

```text
- 调用 ffprobe
- 判断媒体类型
- 提取 duration、codec、streams
- 计算可选 file_hash
- 写入 media_files / media_streams
```

不得做：字幕解析、同步算法、导出。

### 11.2 `daysync_core.timeline`

职责：

```text
- 生成 flat_timeline
- 管理 flat_timeline_items
- 提供 flat time 与 source time 的双向映射
```

### 11.3 `daysync_core.subtitles`

职责：

```text
- 解析 SRT/VTT
- 文本规范化
- 字幕导入
- 字幕到素材时间的映射
```

### 11.4 `daysync_core.search`

职责：

```text
- FTS5 索引
- 搜索字幕
- 排序与高亮，MVP 可以不做高亮
```

### 11.5 `daysync_core.sync`

职责：

```text
- 手动锚点 offset 计算
- 保存 sync_result
- 后续实现自动候选、正反向验证、offset 聚类
```

### 11.6 `daysync_core.export`

职责：

```text
- 导出 sync_report.csv
- 后续导出 FCP 7 XML / FCPXML / OTIO
```

---

## 12. 测试规格

### 12.1 必须有的单元测试

```text
test_srt_parse_basic
- 输入标准 SRT
- 输出正确 start_ms、end_ms、text

test_flat_timeline_generation
- 输入两个 10s 媒体，gap=1000ms
- item1: 0-10000
- item2: 11000-21000

test_subtitle_mapping_ok
- 字幕 12000-13000ms 应映射到第二个素材 source 1000-2000ms

test_subtitle_mapping_cross_boundary_warning
- 字幕跨越 item 结束时间，应 warning

test_normalize_chinese_text
- 去标点、空格、大小写

test_manual_anchor_offset
- video source_start=10000, audio source_start=584180
- offset=574180

test_csv_export
- sync_result 可导出指定列
```

### 12.2 集成测试数据

`sample_data/` 应包含：

```text
sample_data/
├── media/
│   ├── video_001.mov 或 mock_video_001.json
│   ├── video_002.mov 或 mock_video_002.json
│   └── audio_001.wav 或 mock_audio_001.json
├── subtitles/
│   ├── video_flat.srt
│   └── audio_flat.srt
└── expected/
    └── sync_report.csv
```

如果 CI 环境没有真实媒体文件，可以用 mock ffprobe JSON 测试核心逻辑。

---

## 13. 开发任务顺序

### Phase 0：工程骨架

```text
DYS-000 初始化 monorepo
DYS-001 创建 Python package daysync_core
DYS-002 创建 FastAPI 服务
DYS-003 创建 Tauri + React 前端
DYS-004 SQLite 初始化与迁移机制
```

### Phase 1：项目与媒体

```text
DYS-101 创建项目
DYS-102 打开项目
DYS-103 导入媒体并解析 ffprobe
DYS-104 媒体列表 UI
```

### Phase 2：平铺时间线

```text
DYS-201 生成 flat timeline
DYS-202 flat time/source time 映射函数
DYS-203 flat timeline UI 表格
```

### Phase 3：字幕

```text
DYS-301 SRT parser
DYS-302 文本规范化
DYS-303 导入字幕并映射
DYS-304 字幕 FTS5 索引
DYS-305 字幕搜索 API 和 UI
```

### Phase 4：手动同步与导出

```text
DYS-401 手动锚点 offset 计算
DYS-402 sync_result 保存
DYS-403 sync results UI
DYS-404 CSV 导出
DYS-405 端到端测试
```

### Phase 5：半自动增强

```text
DYS-501 上下文窗口构建
DYS-502 字幕相似度评分
DYS-503 自动推荐候选 top N
DYS-504 正反向验证
DYS-505 多锚点 offset 聚类
DYS-506 复核队列
```

---

## 14. 给 GPT5.4 的开发 Prompt 模板

后续每次让 GPT5.4 写代码时，建议使用下面模板，避免模型一次性生成过多不可控代码。

```text
你是 DaySync 项目的资深全栈工程师。请严格按照《DaySync 全自动合板系统｜GPT5.4 开发需求规格书》实现任务。

当前任务：DYS-XXX：{任务名称}

限制：
1. 只实现本任务，不实现未来功能。
2. 所有时间字段使用整数毫秒。
3. API 层 ID 使用 UUID 字符串。
4. 必须包含单元测试。
5. 不允许引入规格书未列出的重型依赖。
6. 修改前先列出涉及的文件。
7. 输出完整代码或 patch。

验收标准：
{复制对应任务的验收标准}

请开始实现。
```

---

## 15. 未来增强功能进入条件

以下功能只有在 MVP 0.1 完成并通过端到端测试后才允许开发：

```text
本地 ASR：需要先完成字幕导入、字幕搜索、同步结果保存。
波形精对齐：需要先完成手动 offset 和 sync_result。
自动合板：需要先完成候选推荐、正反向验证、多锚点聚类。
FCP 7 XML：需要先完成 CSV 导出并验证字段完整。
FCPXML：需要先有至少 3 个真实剪辑软件导入测试样例。
漂移检测：需要至少支持 3 个以上锚点的同一素材同步结果。
```

---

## 16. 最小可交付定义

MVP 0.1 只有在以下全部完成后才算完成：

```text
- 可以新建和重新打开项目。
- 可以导入至少 2 个视频和 1 个音频文件。
- 可以生成视频 flat timeline 和音频 flat timeline。
- 可以导入 video_flat.srt 和 audio_flat.srt。
- 字幕能正确映射回原始素材。
- 可以搜索一句字幕，并在视频/音频两侧返回结果。
- 用户可以选择一条视频字幕和一条音频字幕计算 offset。
- sync_result 被保存到 SQLite。
- 可以导出 sync_report.csv。
- 所有核心逻辑有自动化测试。
```

---

## 17. 重要设计约束总结

```text
1. DaySync 的核心是时间映射，不是 ASR。
2. MVP 的核心是字幕锚点合板，不是全自动。
3. 自动结果必须可解释、可复核、可撤销。
4. SQLite 是项目真相源，缓存文件可以重建。
5. 导出文件只是结果表达，不应成为内部主数据。
6. 所有跨文件边界字幕必须警告。
7. 任何低置信度匹配不能自动进入最终结果。
```

---

## 18. 附录：推荐开发优先级

最高优先级：

```text
1. 数据库 schema
2. 项目创建/打开
3. 媒体导入与 ffprobe 抽象
4. flat timeline 映射
5. SRT 导入与映射
6. 字幕搜索
7. 手动 offset
8. CSV 导出
```

中优先级：

```text
1. UI 体验优化
2. 项目恢复
3. 批量导入错误处理
4. 字幕跨边界提示
5. 自动候选 top N
```

低优先级：

```text
1. 本地 ASR
2. 多模型引擎
3. 音频指纹
4. FCPXML
5. 团队协作
6. 云端队列
```
