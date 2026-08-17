# CLAUDE.md — quote-strip-studio

## 产品边界

把一条公开 YouTube 访谈变成 1080×1440 的「横向视频截图条带拼贴」金句图
（中文版 / 英文版 / 双语版），供小红书和公众号使用。形态是
**Claude Code 项目级 Skill + 确定性本地 CLI**，不是 Web App。
不做：Web UI、数据库、登录、队列、爬榜、定时发布、自动发布、AI 生图、Whisper。

## 不可违反的规则

1. **运行时代码（src/qcard/**）绝不调用任何 LLM API。** 选题、选句、翻译、文案
   由当前 Claude/GLM 会话完成；脚本只做确定性任务。
2. **未经用户明确批准，绝不读取 Safari/Chrome Cookie。**
   `YOUTUBE_TRANSCRIPT_COOKIES_FROM_BROWSER` 只能由用户自己设置。
3. **金句真实性**：每条 `source_text` 必须能在本地字幕中按连续原文定位；
   中文翻译不得比原话更夸张/绝对，不得补充原文没有的事实；不得捏造。
   「找不到原文」在 validate 里是硬失败，不许放宽。
4. 画面必须来自原视频帧（yt-dlp ≤720p + ffmpeg），版式只用 Pillow 等确定性库。
5. 不得把 API Key、Cookie、浏览器资料、个人绝对路径写进仓库。
   `work/` 产物不提交。
6. 任何**发布动作**（发小红书/公众号）必须由用户明确触发；本仓库只生成草稿。
7. 遇 YouTube 阻断：先用上游 Skill 自带的客户端轮换 + yt-dlp 回退；仍失败就
   报告原因，不要自作主张升级权限。
8. 每次只安装任务所需的最小依赖；第三方脚本先读关键文件再运行；禁 `curl | bash`。
9. shell 中 YouTube URL 一律单引号包裹；外部命令一律参数数组，不拼 shell 字符串。

## 修改渲染器后必须跑

```bash
.venv/bin/python -m pytest            # 全部 26 个测试
bin/qcard preflight                   # 必须 PASS
```

涉及字幕定位/校验改动：加/改 `tests/test_validation.py` 用例；
涉及版式/帧选择改动：加/改 `tests/test_render.py` 用例。

## 目录速览

- `bin/qcard` — CLI（preflight/fetch/validate/build/rerender/open）
- `src/qcard/` — 渲染与校验逻辑
- `.claude/skills/native-subtitle-quote-image/` — 本项目 Skill（编排说明）
- `.claude/skills/baoyu-youtube-transcript/` — 上游字幕 Skill（勿改核心逻辑）
- `config/styles/classic.yaml` — 版式参数
- `work/<video-id>/` — 每条视频的全部产物（缓存：字幕/视频/帧/输出）
- `.cache/youtube-transcript/` — 上游 Skill 的原始缓存

## 日常命令

```text
/native-subtitle-quote-image 'https://www.youtube.com/watch?v=…' --count 6 --mode pair --style classic --yes
```

改字后只重渲染（不联网）：`bin/qcard rerender work/<id> --mode pair`。
