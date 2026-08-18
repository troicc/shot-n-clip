# Platform Copy Policy (V2)

Copy is written by platform-copy-editor AFTER fidelity review passes.
It summarizes the pack specifically — it never re-praises generically.

## content_brief first (mandatory)
core_claim · reader_value · key_facts (video-specific: names, numbers,
anecdotes) · misread_risk · tone · banned_angles.

## Xiaohongshu
- 6 titles, ≥3 strategies among: direct(直接判断) / question(问题切入) /
  contrast(克制反差); story / number optional.
- recommended_title: exactly one, chosen — don't outsource the choice.
- intro_full 90–180 chars: name the pack's specific tension/mechanism.
  Bad: 「这段访谈太有启发了」. Good: 「Bill Gurley 研究了 100 多份传记后发现：
  持续学习不是成功的输入，而是被着迷推着走的结果」.
- intro_short 40–80 chars.
- 3–6 hashtags, accurate, no #所有人必看.
- source_note with link + timestamp pointer.

## WeChat
- 4 titles, one recommended.
- intro_full 120–260 chars: fuller, more restrained than xhs; not a padded
  xhs title.
- intro_short 60–120 chars.
- quote_contexts: ≤1 sentence of genuinely necessary context per quote
  (who is Danny, what precedes the line) — not the editor's selection notes.
- source_note + 翻译说明 (语序为中文阅读调整，原文以视频为准).

## Banned in copy
- 套话: 值得所有人反复看 / 含金量 / 狠狠共鸣 / 看完通透 / 建议收藏 /
  一针见血 / 发人深省 / 颠覆认知 / 太有启发
- 模板: 真正的X是Y / 这段话告诉我们 / 你一定要明白
- Fabricated first-person (我亲测/我一直都) — the account voice may have
  opinions, not invented experiences.
- Numbers absent from the pack's quotes.
- Consecutive exclamation marks; false scarcity; 所有人都该看.

## Validation
`bin/qcard validate-editorial <work-dir>` runs copy_validation on every
pack's publish_xhs.json / publish_wechat.json: schema, lint, strategy
coverage, length windows, unsupported-number check, recommended-exists.
