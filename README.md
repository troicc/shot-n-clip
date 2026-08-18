# shot-n-clip / quote-strip-studio

把一条公开 YouTube 访谈或演讲，整理成可发布的小红书 / 微信公众号金句图：
中文卡、英文原文卡、双语卡、来源时间戳、候选帧，以及两套平台文案。

项目形态是 **Claude Code 项目级 Skill + 确定性本地 CLI**。运行时 Python
不调用任何 LLM API：Coding Agent 负责理解、选句、翻译和审稿；本地程序负责
字幕证据、硬质量门禁、视频帧和渲染。

## V3 解决的问题

V3 不再让同一个模型直接“选句 → 翻译 → 自评通过”。完整链路是：

```text
source_map.json
→ editorial_inputs/chunks
→ candidate_pool.json
→ pack_proposals.json
→ selection_audit.json
→ packs/<pack-id>/editorial_pack.json
→ packs/<pack-id>/translation_audit.json
→ V2 + V3 strict validation
→ render
```

V3 会阻止：

- `Only 23 percent said yes.` 这类缺少问题的裸答案；
- `Those that ...` 这类缺少先行词的残句；
- 同一张卡用不同措辞重复同一个观点；
- 原文没有“成功”，中文却擅自加入“成功”；
- 丢失 `maybe`、数字、`artisan` 身份或 input/output 对照；
- `学习自己会发生`、`零刻意努力`、`自动去学` 等口号式机翻。

真实回归案例见 `docs/demo/bill-gurley/acceptance.md`。

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

也会安装两个 console script：`qcard` 与 `qcard-quality`。仓库内的
`bin/qcard` / `bin/qcard-quality` 会优先使用 `.venv`，适合日常运行。

## 一条链接开始生产

在仓库根目录启动 Claude Code：

```bash
source .venv/bin/activate
claude
```

然后输入：

```text
/native-subtitle-quote-image 'https://youtu.be/z-WfDn_0AWE' --packs auto --max-packs 4 --mode all --copy both --quality strict
```

zsh 中必须用单引号包住 YouTube URL。

`--max-packs` 是上限，不是配额。只有两组达到质量门槛，就只输出两组；双语卡
默认使用五条，避免为了凑六条牺牲字号或加入弱句。

## V3 确定性质量命令

```bash
bin/qcard-quality prepare work/<video-id>
bin/qcard-quality validate-candidates work/<video-id>
bin/qcard-quality validate-selection work/<video-id>
bin/qcard-quality validate-translation work/<video-id> --pack pack-01
bin/qcard-quality validate work/<video-id> --strict
```

V3 通过后还必须执行原有 V2 校验：

```bash
bin/qcard validate-editorial work/<video-id> --strict
```

两套校验都通过后再渲染：

```bash
bin/qcard render-packs work/<video-id> --mode all
bin/qcard report work/<video-id>
bin/qcard open work/<video-id>
```

## 产物目录

```text
work/<video-id>/
├── transcript/
├── source_map.json
├── entity_glossary.json
├── editorial_inputs/
├── candidate_pool.json
├── pack_proposals.json
├── selection_audit.json
├── review_queue.md
└── packs/
    └── pack-01/
        ├── editorial_pack.json
        ├── translation_audit.json
        ├── publish_xhs.json
        ├── publish_wechat.json
        └── outputs/
            ├── 01_zh.png
            ├── 02_en.png
            ├── 03_bilingual.png
            ├── contact_sheet.jpg
            └── layout_report.json
```

## 修改和重渲染

改中文时同时维护 `editorial_pack.json` 和 `translation_audit.json`，然后重新运行
V3 翻译校验、V2 strict 校验和 `render-packs`。更换画面时从 contact sheet 选择
时间点，写入 `frame_time_sec`，不需要重新抓字幕或下载视频。

认可成品后：

```bash
bin/qcard approve work/<video-id> --pack pack-01
```

不认可时记录具体原因：

```bash
bin/qcard reject work/<video-id> --pack pack-01 \
  --reason unnatural_wording \
  --note '第三句仍有英译中语序，结尾像口号'
```

## 安全与版权边界

- 未经用户明确许可，不读取浏览器 Cookie；
- 不把 API Key、Cookie、个人绝对路径或 `work/` 产物提交到仓库；
- 画面来自原视频帧，发布前应确认引用范围、署名和平台规则；
- 本项目只生成草稿，不自动发布。

更详细的 V3 步骤见 `docs/V3_USAGE.md`。第三方组件见
`THIRD_PARTY_NOTICES.md`。
