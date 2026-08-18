# CLAUDE.md — shot-n-clip V3

## 产品边界

把公开 YouTube 访谈 / 演讲变成 1080×1440 金句卡：中文、英文、双语、候选帧
和小红书 / 微信文案。形态是 **Claude Code 项目级 Skill + 确定性本地 CLI**，
不是 Web App。

不做：登录、数据库、爬榜、定时发布、自动发布、AI 生图、默认 Whisper。

## 不可违反的规则

1. `src/qcard/**` 运行时代码绝不调用 LLM API。语义工作由当前 Coding Agent 完成。
2. 未经用户明确批准，绝不读取 Safari / Chrome Cookie。
3. 每条候选必须绑定 `source_map.json` 中连续片段；找不到原文是硬失败。
4. 先建立 `candidate_pool.json`，再提 Pack；主题 Agent 不得批准自己的选句。
5. `selection-reviewer` 独立生成 `selection_audit.json`，执行 standalone、direct-support、
   incremental-value、drop、competitor 与 weakest-line 测试。
6. 每个 ready Pack 必须有 `translation_audit.json`：必需 claim units 全部 preserved；
   additions / omissions / strengthenings / weakenings 全空；五项自然中文检查全 true。
7. 模型自填分数不能覆盖确定性错误。V2 与 V3 两套 strict validator 都必须通过。
8. 不强行凑六句或四个 Pack；双语卡默认五句，保持可读字号。
9. 画面必须来自原视频帧；外部命令使用参数数组，不拼 shell 字符串。
10. API Key、Cookie、浏览器资料、个人绝对路径和 `work/` 产物不得进入仓库。
11. 发布动作必须由用户明确触发；本仓库只生成草稿。
12. 遇阻断先用上游字幕 Skill 的客户端轮换与 yt-dlp 回退，不自行升级权限。

## V3 回归底线

- 不发布缺少调查问题的 `Only 23 percent said yes.`；
- 不发布缺少先行词的 `Those that ...` 残句；
- 不把 input/output 擅自翻成“成功的原因/结果”；
- 保留 `maybe`、数字、专名、否定、因果与 `artisan` 身份；
- 拒绝 `学习自己会发生`、`零刻意努力`、`自动去学`、`影响超自己`、
  `对着迷的人` 等已知坏表达；
- 同一个 Pack 不允许两句只是在重复“着迷会让学习自动发生”。

## 标准流程

```bash
bin/qcard preflight
bin/qcard fetch '<youtube-url>'
bin/qcard source-map work/<id>
bin/qcard-quality prepare work/<id>
```

随后按 Skill 调用 candidate miner、angle editor、selection reviewer、source auditor、
zh editor、blind fidelity reviewer 和 platform copy editor，生成：

```text
candidate_pool.json
pack_proposals.json
selection_audit.json
packs/<id>/editorial_pack.json
packs/<id>/translation_audit.json
publish_xhs.json
publish_wechat.json
```

最终必须运行：

```bash
bin/qcard-quality validate work/<id> --strict
bin/qcard validate-editorial work/<id> --strict
bin/qcard render-packs work/<id> --mode all
python -m pytest -q
```

## 目录速览

- `bin/qcard` — V1/V2 抓取、来源、视频、帧、渲染与报告 CLI
- `bin/qcard-quality` — V3 候选、选句、翻译审计 CLI
- `src/qcard/editorial_quality_v3/` — 确定性 V3 质量门禁
- `.claude/agents/` — 按职责拆分的语义 Agent
- `.claude/skills/native-subtitle-quote-image/` — V3 编排说明
- `schemas/v2/`、`schemas/v3/` — 双层契约
- `docs/demo/bill-gurley/acceptance.md` — 真实视频回归标准
- `work/<video-id>/` — 本地素材与产物，不提交

## 日常命令

```text
/native-subtitle-quote-image '<youtube-url>' --packs auto --max-packs 4 --mode all --copy both --quality strict
```
