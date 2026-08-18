---
name: native-subtitle-quote-image
description: V2 pipeline — turns one public YouTube interview into MULTIPLE independently publishable theme packs, each with verified source spans, entity-locked natural Chinese (multi-candidate + blind fidelity review), zh/en/bilingual 1080x1440 collages, and Xiaohongshu/WeChat copy. Use for 金句图 / 语录拼贴 / 访谈金句 / quote cards.
---

# native-subtitle-quote-image (V2)

You orchestrate a multi-agent editorial pipeline. Semantic work (angles,
translation, review, copy) happens **in this session** via the project
agents; deterministic work (fetch, evidence maps, validation, rendering)
runs through `bin/qcard`. **Runtime code never calls an LLM API.**

## Invocation

```
/native-subtitle-quote-image '<youtube-url>' --packs auto --max-packs 4 --mode all --copy both --quality strict
```

`--packs auto` (only threshold-passing packs), `--max-packs N` (cap, never a
quota), `--mode pair|inline|all`, `--copy both|xhs|wechat`, `--quality strict`
(enables `validate-editorial --strict`). Always single-quote the URL.

## Orchestration — run stages in order; resume, don't redo

0. **Preflight**: `bin/qcard preflight` — abort on FAIL.
1. **Fetch**: `bin/qcard fetch '<url>'` (cached → no network). Prefer manual
   captions over ASR when both exist (`--list` via the upstream skill if
   unsure).
2. **Evidence layer**: `bin/qcard source-map work/<id>` → `source_map.json`
   + `entity_glossary.json`. Review `needs_review` entities; if the video's
   key people are unresolved, ask the user once or propose an
   `entity_overrides.yaml` addition.
3. **Style memory**: read `config/editorial/approved_examples.jsonl` (last
   20) + `rejected_examples.jsonl` (last 10) as pattern reference only.
4. **Angles → packs**: run the **angle-pack-editor** agent with the FULL
   chunked transcript. Save its JSON as `work/<id>/angle_packs.json`.
   4–10 candidates → dedupe → ≤ max-packs ready. Rejected packs keep
   concrete reasons.
5. **Per ready pack** (in `work/<id>/packs/<pack-id>/`):
   a. **source-auditor** agent → audited spans, ASR flags, entities.
   b. **zh-editor** agent → five-step output per quote (semantic_brief →
      faithful_zh → 3 candidates → editor_choice → compact_zh).
   c. **fidelity-reviewer** agent (blind — don't show it the editor's
      reasons) → scores + verdict. `revise` → send the precise instruction
      back to zh-editor; **max 2 rounds**, then manual_review.
   d. Assemble `editorial_pack.json` (schemas/v2/editorial-pack.schema.json).
   e. **platform-copy-editor** agent → `publish_xhs.json` + 
      `publish_wechat.json` (content_brief first, specific not generic).
6. **Strict validation**: `bin/qcard validate-editorial work/<id> --strict`.
   Fix every ERROR at the file that caused it; never loosen the validator.
7. **Frames + render**: `bin/qcard render-packs work/<id> --mode all`
   (uses cached video; no re-fetch). Produces per-pack `outputs/` with
   01_zh/02_en/03_bilingual + contact_sheet + layout_report.json; exports
   review clips for ASR-suspect quotes and writes `review_queue.md`.
8. **Visual QA**: actually open the images. Check: 1080×1440, rounded
   corners, no mid-word breaks, no widow words, bands inside strips,
   pair pages identical frames/order, inline 5-quote layout. Bad frame →
   set `frame_time_sec` (from contact_sheet) and re-render. At least one
   look→fix→re-render iteration is expected.
9. **Quality reports**: per pack write `quality_report.json` per
   references/quality-gates.md gates (ready only if ALL pass).
10. **Comparison + report**: for an upgraded video, generate
    `comparison_before_after.jpg` + `comparison_report.md` against V1
    outputs; run `bin/qcard report work/<id>`; `bin/qcard open work/<id>`.
11. **Final reply**: list real absolute paths, ready/rejected/manual counts,
    review-queue items, and the day-to-day command. Never just "done".

## Agents (project-level, model: inherit)
`.claude/agents/`: source-auditor · angle-pack-editor · zh-editor ·
fidelity-reviewer · platform-copy-editor — each outputs only its JSON.

## References
- references/editorial-policy.md — non-negotiables + V2 failure handling
- references/translation-workflow.md — five-step zh editorial + examples
- references/platform-copy-policy.md — xhs/wechat copy rules
- references/quality-gates.md — all thresholds in one page
- references/quote-selection.md · layout-spec.md — V1 baselines still apply

## V1 failure handling (unchanged)
No captions → report, no Whisper. Blocked → upstream fallback, no cookie
reads without approval. Subtitle-OK/video-fail → keep packs, report
"渲染未完成". Font missing → print tried paths. Overflow (exit 3) → swap
quote or compact_zh, never shrink below floor.

## User revision loop (still offline)
- re-edit one pack's zh/copy → edit files → `validate-editorial` →
  `render-packs`
- swap a frame → `frame_time_sec` from contact_sheet → re-render
- different angle pack → rebuild that pack from angle_packs.json
- approve/reject style memory:
  `bin/qcard approve work/<id> --pack <pid>`
  `bin/qcard reject work/<id> --pack <pid> --reason ai_cliche`
