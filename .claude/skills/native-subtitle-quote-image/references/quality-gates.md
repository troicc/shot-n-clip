# Quality Gates (V2)

## Per-quote review thresholds (fidelity-reviewer output)
| Metric | Gate |
|---|---|
| fidelity_score | ≥ 9.0 |
| naturalness_score | ≥ 8.5 |
| source_confidence | ≥ 8.5 |
| ai_tone_risk | ≤ 2.5 |
| entity_integrity | pass |
| modality_integrity | pass |
| verdict | pass (2 auto-revision rounds max, then manual_review) |

## Pack quality_report gates (status=ready requires ALL)
| Dimension | Min |
|---|---|
| source_integrity | 90 |
| entity_integrity | 100 |
| translation_fidelity | 90 |
| chinese_naturalness | 85 |
| anti_template_quality | 85 |
| pack_coherence | 85 |
| platform_copy_quality | 82 |
| layout_readability | 90 |
| manual_review_items | empty |

## Structural gates (pack_validation)
- exact_source_text locatable to contiguous segments (gap ≤1.5s)
- display_en token diff fully explained by whitelisted edits
- no source-span reuse across ready packs
- core-claim Jaccard < 55% between any two ready packs
- ≤2 quotes per 30s window; ≥4 non-overlapping spans per pack
- every number in source appears in zh
- hedge survival (maybe/often/can/tend to…); negation direction
- zh lint: banned patterns fail; 不是……而是…… ≤1/pack; ending rhythm;
  abstract stacking; judgment-shape ratio
- layout: real-metric wrap, word-boundary breaks, widow guard, min font
  (zh 42 / en 28 / inline zh 32 / inline en 22); overflow → swap quote or
  use compact_zh, never shrink below floor

## Copy gates (copy_validation)
schema ok · no banned patterns · no fabricated first-person · strategy
coverage (xhs) · length windows · every cited number in pack sources ·
recommended_* present

## Stage pipeline (resume via _stage_status.json)
preflight → fetch → source-map(+glossary) → angles/packs → per-pack
[source-audit → zh-editorial → blind review (≤2 revisions) → copy] →
strict validate → frames+render → layout QA → comparison/report
