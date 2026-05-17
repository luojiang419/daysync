# DaySync

DaySync 是一个本地优先的桌面合板工具，当前工程实现 MVP 0.1 的字幕锚点同步链路：

- 新建和打开项目
- 导入视频与外录音频元数据
- 生成视频/音频 flat timeline
- 导入 SRT 并映射回原始素材
- 统一搜索字幕
- 手动选择锚点计算 offset
- 导出 `sync_report.csv`

## 目录结构

```text
daysync/
├── apps/desktop            # Tauri + React 前端
├── docs/                   # 工程内部说明
├── packages/daysync_core   # Python 核心业务与测试
├── sample_data/            # MVP 测试样例
├── scripts/                # 开发辅助脚本
└── services/api            # FastAPI 本地服务
```

## 开发环境

- Python 3.12+
- Node.js 24+
- pnpm 10+
- Rust 1.95+
- FFmpeg / ffprobe 会自动下载到项目目录，未预装也可直接运行

## 常用命令

```powershell
uv sync
pnpm install
uv run pytest
uv run uvicorn services.api.main:app --reload --host 127.0.0.1 --port 17831
pnpm --filter desktop dev
pnpm --filter desktop test
pnpm --filter desktop tauri dev
uv run python scripts/ensure_ffmpeg.py
```

## FFmpeg 配置

运行时优先读取：

- `DAYSYNC_FFPROBE_BIN`
- `DAYSYNC_FFMPEG_BIN`

如果未设置，会按以下顺序补齐：

1. 项目内 `tools/ffmpeg/windows-x64/current/bin/`
2. 系统 `PATH`
3. 自动下载 Gyan Windows release essentials ZIP 到项目目录
