# quote-strip-studio

把一条公开 YouTube 访谈链接，变成小红书 / 公众号可直接用的「横向视频截图
条带拼贴」金句图（1080×1440，中文版 + 英文原文版 + 可选双语版），并附发布
文案草稿。所有金句可回溯到字幕原文与时间戳。

**产品形态**：Claude Code 项目级 Skill + 确定性本地 CLI。不是 Web App。
运行时脚本零 LLM API 调用 —— 选题、选句、翻译由 Claude Code 会话完成，
脚本只做确定性抓取、渲染、校验。

---

## 1. 安装 / 预检

需要：macOS 或 Linux，Python ≥3.9，ffmpeg/ffprobe，node（bun 可选）。

```bash
cd quote-strip-studio
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
bin/qcard preflight
```

preflight 逐项输出 PASS/WARN/FAIL 与修复提示。必需项全部 PASS 才能继续。
OpenCV 是可选加速（人脸加分选帧），缺失不影响任何功能。

## 2. 首次命令（在 Claude Code 里）

```bash
cd <本目录>
claude
```

然后在会话里：

```text
/native-subtitle-quote-image 'https://www.youtube.com/watch?v=VIDEO_ID' --count 6 --mode pair --style classic --yes
```

注意 URL 用**单引号**包裹（zsh 会把 `?` 当通配符）。

参数：`--count 4-8`（默认 6）；`--mode pair|inline|all`（默认 pair）；
`--style classic`；`--yes` 跳过下载确认。

## 3. 日常一条 URL 的命令

同上 —— 每条新视频就这一个命令。已抓过的视频直接命中本地缓存，不重复联网。

纯 CLI 也可用（不含会话内的选题翻译）：

```bash
bin/qcard fetch 'https://youtu.be/VIDEO_ID'   # 抓字幕，输出 work/<id>/
# 自己填写 work/<id>/angles.json 与 selection.json
bin/qcard validate work/<id>
bin/qcard build work/<id> --mode all --style classic
bin/qcard rerender work/<id> --mode pair       # 只重渲染，不联网
bin/qcard open work/<id>                        # 打开输出目录
```

## 4. 如何看 contact sheet

`work/<id>/frames/contact_sheet.jpg` 是一张网格缩略图：每个候选帧标注
`qXX`、时间戳（毫秒）与自动分数；被拒帧标 ✗ 与原因（近黑/过曝/纯色/重复）；
星号 ★ = 当前选中的帧。想换某条的帧：从 sheet 里挑一个好时间，写进
selection.json 对应 quote 的 `frame_time_sec`，然后 rerender。

## 5. 如何修改 selection.json

打开 `work/<id>/selection.json`：

- 改中文措辞 → `display_zh`（不要比原文更绝对）
- 换/删句子 → 编辑 `quotes[]`（`source_text` 必须仍是字幕连续原文）
- 换帧 → `frame_time_sec` 填秒数（从 contact sheet 取）
- 改完执行：`bin/qcard validate work/<id> && bin/qcard rerender work/<id> --mode pair`

**rerender 不会联网、不会重新抓字幕、不会重新下载视频。**

## 6. 如何只重渲染

```bash
bin/qcard rerender work/<id> --mode pair     # 或 inline / all
```

## 7. 常见错误

| 现象 | 处理 |
|---|---|
| `validate: FAILED … source_text NOT FOUND` | 该句不是字幕连续原文。回到 agent_input.md 重新找到原句粘贴，不要改校验器。 |
| `overflow: text cannot fit…`（退出码 3） | 该句太长。换一条更短的完整句子，不要硬截断。 |
| `Transcripts disabled` | 视频没有任何字幕，本 MVP 不支持（未来可传入本地 SRT）。 |
| `Video unavailable / private / age restricted` | 视频受限，换链接。 |
| `bot detected / IP blocked` | 上游已自动回退仍失败。稍后再试；如需 Cookie 必须你本人明确批准并自设 `YOUTUBE_TRANSCRIPT_COOKIES_FROM_BROWSER`。 |
| 字幕成功但视频下载失败 | angles/selection 保留，输出会明确标记「渲染未完成」，不会伪造截图。 |
| 字体 FAIL | preflight 会列出尝试过的路径；macOS 装 PingFang（系统自带），Linux 装 Noto Sans CJK。 |

## 8. 缓存位置

- `work/<video-id>/transcript/` — 字幕与元数据（复制自上游）
- `.cache/youtube-transcript/` — 上游 Skill 原始缓存（含封面）
- `work/<video-id>/source_video.mp4` — ≤720p 视频（固定文件名）
- `work/<video-id>/frames/candidates|selected/` — 候选帧与选中帧
- `work/<video-id>/outputs/` — 所有成图、manifest、发布文案

## 9. 来源与版权提示

金句图的画面来自原视频帧，文字来自原字幕。发布时：

- 在文案中给出视频标题、频道/嘉宾与原链接（publish_*.md 已包含）
- 尊重原视频版权与平台规则，片段引用应合理、有限
- 中文翻译已在文案中声明「语序为中文阅读调整，原文以视频为准」

## 10. 如何安全删除某条素材

```bash
rm -rf work/<video-id>                    # 删该视频全部产物
rm -rf .cache/youtube-transcript/<频道>    # 删上游字幕缓存
```

`work/` 与 `.cache/` 都在 .gitignore 里，删除不影响代码与其他视频。

---

## 测试

```bash
.venv/bin/python -m pytest
```

26 个测试覆盖：selection 校验（缺字段/找不到原文/时间越界/重复）、文本溢出、
1080×1440 尺寸、圆角蒙版、pair 帧序一致、rerender 零联网、非 ASCII 路径、
无 OpenCV 路径。测试视频由 ffmpeg 现场合成，不含第三方版权素材。

## 第三方组件

见 `THIRD_PARTY_NOTICES.md`（baoyu-youtube-transcript，MIT）。
