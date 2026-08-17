# Third-Party Notices

## baoyu-youtube-transcript

- **来源 (Source):** <https://github.com/JimLiu/baoyu-skills>，子目录 `skills/baoyu-youtube-transcript/`
- **用途 (Use):** 仅复制该单个 Skill 完整目录到 `.claude/skills/baoyu-youtube-transcript/`，用于抓取 YouTube 视频元数据与字幕（`meta.json`、`transcript-raw.json`、`transcript-sentences.json`、`imgs/cover.jpg`）。未安装整个 baoyu-skills 插件，未引入其他无关 Skill。
- **版本 (Version):** 上游仓库 commit `6b7a2e417500561a5ecdd0b168332f4142584617`（2026-07-03）；Skill 自身 `version: 1.1.0`（见其 SKILL.md frontmatter）。
- **修改 (Modifications):** 未修改上游核心逻辑；仅额外放入上游仓库根目录的 `LICENSE` 副本到本目录。
- **许可证 (License):** MIT License，Copyright (c) 2026 Jim Liu。全文见同目录 `LICENSE`。

## Python 依赖（运行时）

| 包 | 用途 | 许可证 |
|---|---|---|
| Pillow | 确定性图像渲染（拼贴图、圆角、文字排版） | MIT-CMU |
| PyYAML | 读取 `config/brand.yaml` 与样式 YAML | MIT |
| yt-dlp | 下载 ≤720p 视频流（仅画面，不取音频） | Unlicense |

系统依赖：`ffmpeg` / `ffprobe`（LGPL/GPL 二进制，本仓库不分发）。字体使用系统已安装字体，不复制、不打包字体文件。
