# Editorial Policy (V2)

Non-negotiable principles, in priority order:

1. **真实性高于传播性。** Never invent, enlarge, or rewrite the speaker's
   claims for quotability.
2. **source_text 是证据，不是文案。** It must locate to a contiguous raw
   caption span (adjacent-span gaps ≤ 1.5s). Distant-sentence stitching is
   fabrication.
3. **display_en 只做可审计清理。** Whitelist: capitalization, punctuation,
   remove_filler, remove_immediate_false_start,
   join_adjacent_caption_fragments. Every other token change → hard fail in
   `source_integrity.display_en_diff`.
4. **中文与原命题等价。** Reorder/compress/detranslate freely; add nothing,
   strengthen nothing. maybe/often/can/tend to MUST survive (maybe→也许，
   often→常常， can→可以， tend to→往往).
5. **专名锁定。** entity_glossary resolved forms appear verbatim (Richard
   叔叔, Union Square Cafe). Unresolved entity referenced by a quote → that
   pack cannot be ready.
6. **数字逐项核对。** Every number/percent/year in source appears as the
   same digit in zh.
7. **无 AI 味靠流程，不靠祈祷。** voice profile + 3 candidates + blind
   review + rule lint + human-approved corpus. One prompt is not a control.
8. **pack 不凑数。** Only threshold-passing packs are ready. Rejected packs
   carry concrete reasons.
9. **语义工作只在会话内。** Runtime code never calls an LLM API.
10. **所有 LLM 产物落盘为结构化 JSON 并过本地 validator**；聊天记录不算交付。
11. **不自动发布。** Human approval precedes any publishing.
12. **不读浏览器 Cookie**（除非用户明确批准）。

## Failure handling additions (V2)

| Failure | Action |
|---|---|
| ASR suspicion on a needed quote | keep it, flag `needs_manual_audio_check`, export review clip, list in review_queue.md — never claim verification |
| Entity cannot be resolved | pack status → manual_review; suggest an entity_overrides.yaml entry to the user |
| zh cannot pass review after 2 revision rounds | verdict manual_review; quote stays out of ready |
| 5 quotes can't fit inline at min font | render 5, not 6; never shrink below floor |
