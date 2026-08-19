# shot-n-clip / quote-strip-studio

把公开 YouTube 访谈或演讲整理成可发布的小红书 / 微信公众号金句图：中文卡、
英文原文卡、双语卡、来源时间戳、候选帧和两套平台文案。

项目形态是 **Claude Code 项目级 Skill + 确定性本地 CLI**。运行时 Python
不调用 LLM API：Coding Agent 负责理解、候选挖掘、选句、翻译和审稿；本地程序
负责字幕证据、硬质量门禁、截帧和排版。

## V4 的重点

V4 不再把“能塞进去”当成“适合发布”。它新增两组硬约束：

### 1. 紧凑、单主题、按源时间连续的选句

- 候选最多 28 个英文词、180 个源字符和两句话；
- 观点与长例子应拆开，禁止把字幕段落直接塞进一个条带；
- 每个 ready pack 只保留 4–5 条强句；
- 用具体 `anchor_terms` 和 `focus_question` 锁定一个问题；
- 选句按时间升序，相邻不超过 120 秒，首尾最多跨 6 分钟；
- 禁止把调查、学校申请、餐厅故事和 AI 拼成“整场演讲精选”。

### 2. 1440×1920 高可读排版

新任务默认使用 `editorial` 样式：

- 中文优先 Semibold/Medium/Bold 字重；
- 中文/英文各最多两行，字号有硬下限；
- 下部渐变 + 黑色描边，减少大黑条对人物的遮挡；
- JPEG quality 96、4:4:4；
- 自动清理中文数字单位间空格和模型式标点空格。

旧 `classic` 样式保留兼容，但不再推荐用于新双语卡。

## 完整链路

```text
source_map.json
→ editorial_inputs/chunks
→ candidate_pool.json
→ pack_proposals.json
→ selection_audit.json
→ qcard-promote（重建 angle_packs.json）
→ packs/<pack-id>/editorial_pack.json
→ packs/<pack-id>/translation_audit.json
→ V2 + V3 strict validation
→ editorial render
```

`qcard-promote` 很重要：它防止旧的 V2 `angle_packs.json` 继续驱动渲染。`qcard-render-v4` 会再次执行 V3 strict、自动 promote、旧版来源/实体/英文完整性检查和高可读排版，任何一层失败都不会出图。

## 安装

需要 macOS / Linux、Python 3.9+、ffmpeg/ffprobe、yt-dlp，以及 bun 或 npx。

```bash
git clone https://github.com/troicc/shot-n-clip.git
cd shot-n-clip
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e '.[dev]'
bin/qcard preflight
python -m pytest -q
```

安装后有四个命令：`qcard`、`qcard-quality`、`qcard-promote`、`qcard-render-v4`；仓库内也提供对应的 `bin/` 启动脚本。

## 一条链接开始生产

```bash
source .venv/bin/activate
claude
```

在 Claude Code 中输入：

```text
/native-subtitle-quote-image 'https://youtu.be/z-WfDn_0AWE' --packs auto --max-packs 4 --mode all --copy both --quality strict
```

zsh 中必须用单引号包住 YouTube URL。`--max-packs` 是上限，不是配额。

## 手动质量与渲染命令

```bash
bin/qcard-quality prepare work/<video-id>
bin/qcard-quality validate-candidates work/<video-id>
bin/qcard-quality validate-selection work/<video-id>
bin/qcard-promote work/<video-id>
bin/qcard-quality validate-translation work/<video-id> --pack pack-01
bin/qcard-quality validate work/<video-id> --strict
bin/qcard-promote work/<video-id>
bin/qcard-render-v4 work/<video-id> --mode all --style editorial
bin/qcard report work/<video-id>
bin/qcard open work/<video-id>
```

任何文本无法在硬字号下保持两行时，应该换一个更短、完整、忠实的原句，不要继续
缩小字体，也不要裁掉命题限定。

## 产物

```text
work/<video-id>/
├── transcript/
├── source_map.json
├── entity_glossary.json
├── editorial_inputs/
├── candidate_pool.json
├── pack_proposals.json
├── selection_audit.json
├── angle_packs.json
├── review_queue.md
└── packs/
    └── pack-01/
        ├── editorial_pack.json
        ├── translation_audit.json
        ├── publish_xhs.json
        ├── publish_wechat.json
        └── outputs/
            ├── 01_zh.png / .jpg
            ├── 02_en.png / .jpg
            ├── 03_bilingual.png / .jpg
            ├── contact_sheet.jpg
            └── layout_report.json
```

## 反馈闭环

```bash
bin/qcard approve work/<video-id> --pack pack-01
bin/qcard reject work/<video-id> --pack pack-01 \
  --reason unnatural_wording \
  --note '第三句仍有英译中语序，结尾像口号'
```

## 安全与版权

- 未经明确许可，不读取浏览器 Cookie；
- 不提交 API Key、Cookie、个人绝对路径或 `work/` 产物；
- 发布前确认引用范围、署名和平台规则；
- 本项目只生成草稿，不自动发布。

细节见 `docs/V3_USAGE.md` 与 `docs/V4_SELECTION_TYPOGRAPHY.md`。第三方与设计参考见
`THIRD_PARTY_NOTICES.md`。
