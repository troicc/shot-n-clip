# Translation Workflow (V2) — the five-step per-quote editorial process

Executed by the zh-editor agent; enforced by fidelity-reviewer + validators.

## Step A — semantic_brief (understand BEFORE producing Chinese)
- **claim**: restate the proposition in one plain line (zh or en).
- **rhetorical_function**: hook / problem / mechanism / example / method /
  close — what the sentence DOES in the pack's arc.
- **tone**: 克制 / 幽默 / 强调 / 假设 / 建议 / 叙事 …
- **modality**: absolute / tendential / possible / conditional.
  Source hedges to watch: maybe, perhaps, often, usually, tend to, can,
  might, I think, I fear, I have a hunch. Record each one found.
- **resolved_references**: this/it/he/they → concrete referent from context.
- **key_terms** + **entity_ids** (glossary-locked).

## Step B — faithful_zh (control specimen)
Complete natural translation, no compression. Exists to detect drift: if the
publish candidate asserts more/less than faithful_zh, it's wrong.

## Step C — three publish candidates
| id | style | character |
|----|-------|-----------|
| a | faithful-natural | safest; reads like a good editor |
| b | spoken-compact | tighter, image-strip friendly |
| c | memorable-restrained | a hook, but zero claim-strengthening |

## Step D — editor_choice
Pick recommended_zh; write why the others lost; log edit_operations
(语序调整 / 删口头重复 / 显化省略主语 / 合并字幕碎片 / 标点规整).

## Step E — layout_variants
compact_zh: same proposition, fewer hanzi (target ≤ 24). No mid-idea cuts,
no ellipsis masks.

## Worked examples (from this repo's audit)

**Bad (V1)**: "leave big footprints" → 「着迷的人，会留下很大的脚印。」
- translationese; readers picture literal footprints.
- Fix: resolve the metaphor → influence/impact in natural zh, keep the
  proposition: 「着迷的人，影响会远远超出自己。」(claim-equivalent, no
  strengthening)

**Bad (V1)**: "Uncle Richard" → 「一句话伯乐」
- entity hallucination: a specific recurring person became a generic concept.
- Fix: locked form 「Richard 叔叔」.

**Bad (V1)**: "fascination comes with the mechanism" → 「着迷自带机制」
- word-by-word mirror. Fix: 「着迷会推着你主动去钻研。」

**Good**: "Maybe all the world really needs is many, many more Uncle
Richards." → 「这个世界需要的，也许是一大批 Richard 叔叔。」
- maybe survived (也许); entity kept; no absolutization.

## Modality map (default; adjust register as needed)
maybe→也许 · perhaps→或许 · often→常常 · usually→通常 · tend to→往往 ·
can→可以/会 · might→可能 · I think→我觉得 · I fear→我担心 ·
I have a hunch→我猜
