---
name: native-subtitle-quote-image
description: V3 editorial pipeline for source-grounded multi-pack quote cards. Mines a broad candidate pool, independently audits selection, performs claim-unit translation review, then renders Chinese/English/bilingual cards and platform copy.
---

# native-subtitle-quote-image — V3 editorial-quality pipeline

The project is a Claude Code skill plus deterministic local tools. Runtime
Python never calls an LLM API. Semantic work happens in the current coding-agent
session; source verification, hard quality gates, frame extraction and rendering
are deterministic.

## Invocation

```text
/native-subtitle-quote-image '<youtube-url>' --packs auto --max-packs 4 --mode all --copy both --quality strict
```

Always single-quote the URL in zsh.

## Why V3 exists

V2 had good schemas but could still approve weak material because one model pass
both chose and justified quotes, reviewer scores were self-reported, and style
lint could not catch semantic inventions such as adding “成功” to a source that
only said input/output. V3 adds three compulsory artifacts:

- `candidate_pool.json` — broad source-verbatim candidates, including rejects;
- `selection_audit.json` — independent line-by-line direct-support/drop/
  competitor review;
- `packs/<id>/translation_audit.json` — claim units, back-translation, empty
  fidelity ledger and native-Chinese checks.

The existing V2 `editorial_pack.json` remains the render contract.

## Pipeline — run in order and resume completed stages

### 0. Preflight and fetch

```bash
bin/qcard preflight
bin/qcard fetch '<youtube-url>'
bin/qcard source-map work/<video-id>
```

Prefer manual source-language captions. Automatic captions are allowed only
with ASR warnings and review clips for doubtful names/numbers.

### 1. Prepare source chunks

```bash
bin/qcard-quality prepare work/<video-id>
```

This writes `editorial_inputs/manifest.json` and ~18k-character transcript
chunks with three-segment boundary overlap. Every manifest chunk must be mined;
do not infer a long video from its opening.

### 2. Broad candidate mining

For every manifest chunk, invoke `quote-candidate-miner`. Save each returned JSON
under:

`work/<video-id>/editorial_inputs/candidates/chunk-XXXX.json`

The miner must preserve exact source spans and explicitly reject bare answers,
setup-only numbers, unresolved pronouns, generic filler and low-confidence ASR.

### 3. Curate pool and propose packs

Invoke `angle-pack-editor` with the manifest and all chunk candidate files. It
must write:

- `candidate_pool.json`
- `pack_proposals.json`

Then run:

```bash
bin/qcard-quality validate-candidates work/<video-id>
```

Fix every error at the source artifact. Never loosen the validator.

### 4. Independent selection review

Invoke `selection-reviewer`. It writes `selection_audit.json` after standalone,
direct-support, incremental-value, drop, competitor and weakest-line tests.

```bash
bin/qcard-quality validate-selection work/<video-id>
```

Only `status=ready` packs continue. A 90-minute video may yield four packs or
none; pack count is a ceiling, never a quota.

### 5. Source audit and Chinese editorial pass

For each ready pack:

1. Run `source-auditor` on the selected candidate spans.
2. Run `zh-editor` per quote. Assemble:
   - the existing V2 `packs/<id>/editorial_pack.json`;
   - V3 `packs/<id>/translation_audit.json`.
3. Run `fidelity-reviewer` blind. Do not show editor self-rationale.
4. Send `revise` issues back to zh-editor, maximum two rounds.
5. `reject_selection` returns the line to selection-reviewer; do not “translate
   around” a weak excerpt.
6. A doubtful source becomes `manual_review`, not a confident quote.

Validate each pack immediately:

```bash
bin/qcard-quality validate-translation work/<video-id> --pack pack-01
```

### 6. Platform copy

Only after translation passes, invoke `platform-copy-editor` and write:

- `publish_xhs.json`
- `publish_wechat.json`

Copy must state the pack's specific tension/mechanism, not praise itself. It may
not invent first-person experience, identities, numbers or outcomes.

### 7. Dual strict validation

Both validators are required:

```bash
bin/qcard validate-editorial work/<video-id> --strict
bin/qcard-quality validate work/<video-id> --strict
```

V2 protects source spans, entities, English edits, modality, copy schema and
layout. V3 protects candidate quality, selection independence, claim coverage,
back-translation, natural Chinese and source/selection/translation binding.

A model-written score never overrides a hard error.

### 8. Render and visual QA

```bash
bin/qcard render-packs work/<video-id> --mode all
```

Actually open every output. Check:

- 1080×1440 and rounded outer corners;
- no English word split;
- no tiny widow line;
- Chinese reads naturally without looking at English;
- pair pages use identical frame order;
- inline bilingual defaults to five quotes;
- selected frame matches the speaker and avoids blinking/transition frames.

Use contact sheet timestamps to pin a better frame, then rerender. At least one
look → fix → rerender cycle is expected for a real demo.

### 9. Final report and style memory

```bash
bin/qcard report work/<video-id>
bin/qcard approve work/<video-id> --pack pack-01
```

Approve only after human review. Rejected packs should be recorded with a
specific reason (`weak_angle`, `literal_translation`, `unnatural_wording`,
`generic_copy`, etc.). The next run reads seed examples plus recent user-approved
and rejected examples.

## Non-negotiable regressions

- Never publish `Only 23 percent said yes.` without the survey question inside
  the contiguous source quote.
- Never turn input/output into “成功的原因/结果” unless success exists in source.
- Reject Chinese such as `学习自己会发生`, `零刻意努力`, `自动去学`,
  `影响超自己`, `对着迷的人`.
- Preserve craft identity in `artisans`, modality in `maybe`, exact numbers,
  names, negation and causal direction.
- Do not select two lines that both merely say “着迷会让学习自动发生”.
- Do not force six lines or four packs.

## Failure handling

No captions → report; no Whisper fallback in this project. YouTube blocked → use
upstream fallbacks, never read browser cookies without user approval. Video
download failure → keep editorial artifacts and report render incomplete. Text
overflow → use a faithful compact variant or replace the quote; never shrink
below the readability floor.
