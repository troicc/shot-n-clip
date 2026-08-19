---
name: native-subtitle-quote-image
description: Source-grounded multi-pack quote-card pipeline with compact candidate selection, chronological theme locality, native Chinese review, and high-clarity editorial rendering.
---

# native-subtitle-quote-image — editorial-quality pipeline

Runtime Python never calls an LLM API. The coding-agent session performs
candidate mining, selection, translation and copy; deterministic tools verify
source evidence, density, theme locality, translation fidelity and rendering.

## Invocation

```text
/native-subtitle-quote-image '<youtube-url>' --packs auto --max-packs 4 --mode all --copy both --quality strict
```

Always single-quote the URL in zsh.

## Default output style

Use the high-clarity renderer for all new work:

```bash
bin/qcard-render-v4 work/<video-id> --mode all --style editorial
```

`editorial` outputs 1440×1920, 4–5 source-ordered lines, lower subtitle
placement with outlined type, and JPEG 4:4:4 export. `classic` remains available
for compatibility.

The useful constraints are inspired by native-subtitle collage practice:
nearby chronological subtitle moments, five points at most, high-resolution 3:4
output, and actual visual review. We do **not** copy embedded subtitles or skip
source/translation validation; this project still redraws verified bilingual
text.

## Pipeline

### 0. Preflight and source

```bash
bin/qcard preflight
bin/qcard fetch '<youtube-url>'
bin/qcard source-map work/<video-id>
bin/qcard-quality prepare work/<video-id>
```

Prefer manual source-language captions. Doubtful ASR names/numbers require
review clips and manual review.

### 1. Mine compact atomic candidates

Invoke `quote-candidate-miner` for every manifest chunk. Save outputs under
`editorial_inputs/candidates/`.

A passing candidate is normally:

- ≤28 English words;
- ≤180 source characters;
- ≤2 sentences;
- one claim, or one complete contrast;
- 1–4 source-grounded `topic_terms`.

Split a compact claim from its anecdote instead of putting both into one strip.

### 2. Pool and propose narrow packs

Invoke `angle-pack-editor` to write `candidate_pool.json` and
`pack_proposals.json`, then:

```bash
bin/qcard-quality validate-candidates work/<video-id>
```

Each proposal uses 1–3 concrete `anchor_terms`, 4–5 candidates, ascending source
time, adjacent gaps ≤120 seconds and total span ≤6 minutes. Do not combine
survey statistics, school admissions, unrelated career stories and AI merely
because the whole talk mentions work.

### 3. Independent selection

Invoke `selection-reviewer`, writing `selection_audit.json`.

```bash
bin/qcard-quality validate-selection work/<video-id>
```

Only ready packs continue. Four strong lines are better than five with a weak
bridge. The previous quote-dispersion rule is removed: nearby source passages
are preferred when they form one continuous expression.

### 4. Source audit and Chinese editing

For every ready pack:

1. `source-auditor` verifies exact source spans and entities.
2. `zh-editor` writes V2 `editorial_pack.json` and V3
   `translation_audit.json`.
3. `fidelity-reviewer` first reads Chinese blind, then checks source fidelity.
4. Maximum two revisions. Bad source returns to selection.

Hard visual budgets:

- recommended Chinese target ≤32 visual units, hard ceiling 38;
- compact Chinese ≤32;
- display English ≤28 words and ≤2 sentences;
- both languages ≤2 rendered lines.

```bash
bin/qcard-quality validate-translation work/<video-id> --pack pack-01
```

### 5. Platform copy and strict validation

Generate Xiaohongshu and WeChat copy only after translation passes.

```bash
bin/qcard-quality validate work/<video-id> --strict
bin/qcard-promote work/<video-id>
```

Never loosen a gate to rescue a chosen line. The V4 renderer also runs the
legacy source/entity/display-English checks, while intentionally ignoring the
obsolete quote-dispersion rule that caused topic-collage packs.

### 6. High-clarity render and visual QA

```bash
bin/qcard-render-v4 work/<video-id> --mode all --style editorial
```

Open every PNG/JPG and `layout_report.json`. Check:

- 1440×1920 and rounded corners;
- 4–5 strips only;
- no third text line in either language;
- no tiny orphan/widow line;
- face remains visible above the lower gradient;
- Chinese is natural without English;
- source moments remain chronological;
- JPG edges are crisp (quality 96, 4:4:4/subsampling 0).

At least one look → fix → rerender cycle is required for a real task.

## Non-negotiable regressions

- No naked `Only 23 percent said yes.`;
- no unresolved `Those that ...`;
- no paragraph-sized Gallup/survey blocks in one strip;
- no pack spanning multiple unrelated sections;
- no unsupported “成功”;
- preserve `maybe`, exact numbers, `artisan` identity and input/output contrast;
- reject `学习自己会发生`, `零刻意努力`, `自动去学`, `影响超自己`;
- do not put the AI jetpack quote inside a fascination-only learning pack;
- no fixed six-line quota.

## Final report and memory

```bash
bin/qcard report work/<video-id>
bin/qcard approve work/<video-id> --pack pack-01
```

Approve only after human visual/editorial review. Record rejections with a
specific reason so future generations learn from actual choices.
