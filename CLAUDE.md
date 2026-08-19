# CLAUDE.md — shot-n-clip V4

## Product boundary

Turn a public YouTube interview or talk into source-grounded 3:4 quote cards for
Xiaohongshu and WeChat. The coding-agent session performs semantic work; local
Python performs evidence checks, quality gates, frame extraction and rendering.
Runtime code must not call an LLM API.

## Non-negotiable editorial pipeline

```text
source_map.json
→ editorial_inputs/chunks
→ candidate_pool.json
→ pack_proposals.json
→ selection_audit.json
→ editorial_pack.json + translation_audit.json
→ qcard-promote
→ qcard-render-v4
```

Do not render directly from a stale `angle_packs.json`. New work must use
`bin/qcard-render-v4`, which revalidates V3, promotes the approved selection,
runs the legacy source/entity/display-English integrity checks, then renders.

## Selection rules

1. A passing source candidate is an atomic quote unit: normally ≤28 English
   words, ≤180 source characters and ≤2 spoken sentences.
2. Split a concise claim from its long anecdote. Do not put both in one strip.
3. Reject naked answers/statistics, unresolved pronouns, setup-only lines,
   doubtful ASR and generic filler.
4. Each candidate should carry 1–4 source-grounded `topic_terms`.
5. A ready pack contains 4–5 strong lines in ascending source time.
6. Adjacent quote centres must be ≤120 seconds apart; total pack span ≤6 minutes.
7. Every ready pack defines one `focus_question` and 1–3 concrete
   `anchor_terms`. Every selected line directly answers that question and
   matches an anchor.
8. Do not mix surveys, school admissions, restaurant stories and AI into one
   card merely because the talk broadly concerns work or learning.
9. Four strong lines are better than a fifth weak bridge. Pack count is a
   ceiling, never a quota.

## Translation rules

1. Preserve exact source claim units, qualifiers, negation, causation, numbers,
   identities and names.
2. Chinese must read naturally without the English visible.
3. Recommended Chinese target ≤32 visual units, hard ceiling 38; compact Chinese
   hard ceiling 32. English display text hard ceiling 28 words.
4. Each language must fit at most two lines at the V4 font floor.
5. Reject selection rather than translating around a paragraph-sized or
   context-dependent source span.
6. Keep the fidelity ledger empty for publishable copy: no additions,
   omissions, strengthenings or weakenings.
7. Never publish known regressions such as `学习自己会发生`, `零刻意努力`,
   `自动去学`, `影响超自己`, unsupported `成功`, dropped `maybe`, or lost
   `artisan` identity.

## V4 rendering

Use:

```bash
bin/qcard-render-v4 work/<video-id> --mode all --style editorial
```

V4 output is 1440×1920 with 4–5 strips, system Semibold/Medium/Bold CJK face,
hard font floors, lower gradient, outlined text, PNG plus JPEG quality 96 with
4:4:4 chroma. If text does not fit, replace the quote; do not shrink further.

## Required verification before declaring completion

```bash
python -m pytest -q
bin/qcard-quality validate-candidates work/<video-id>
bin/qcard-quality validate-selection work/<video-id>
bin/qcard-quality validate-translation work/<video-id> --pack pack-01
bin/qcard-quality validate work/<video-id> --strict
bin/qcard-promote work/<video-id>
bin/qcard-render-v4 work/<video-id> --mode all --style editorial
```

Open every PNG/JPG and contact sheet. A real task requires at least one
look → fix → rerender cycle. Never report completion from JSON or tests alone.

## Safety

- Never read browser cookies without explicit user approval.
- Never commit API keys, cookies, personal paths or `work/` outputs.
- Never auto-publish to social platforms.
- Use exact argument arrays for external commands; never interpolate a shell
  command from user-controlled text.
- Preserve copyright/source notes and keep quoted use limited and attributable.
