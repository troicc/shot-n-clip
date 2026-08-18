"""V1 selection.json → V2 draft pack migration (V2 §十五.1).

Lossless: V1 data is copied into a pack-00 draft; review blocks are seeded
as manual_review (NOT pass) because old translations never went through the
V2 fidelity review. Old files are backed up, never overwritten.
"""

from __future__ import annotations

import json
import os
import shutil
from typing import List

from .models import Selection
from .source_integrity import SourceMap, find_spans

ROLE_BY_V1_REASON = [
    ("hook", "hook"), ("problem", "problem"), ("insight", "mechanism"),
    ("evidence", "evidence"), ("method", "method"), ("close", "close"),
]


def migrate(work_dir: str, source_map: SourceMap) -> str:
    sel_path = os.path.join(work_dir, "selection.json")
    if not os.path.exists(sel_path):
        raise RuntimeError(f"no selection.json in {work_dir} — nothing to "
                           "migrate. Next step: this work dir is already V2.")
    errors: List[str] = []
    selection = Selection.load(sel_path, errors)
    if errors:
        raise RuntimeError("V1 selection.json invalid: " + "; ".join(errors))

    packs_dir = os.path.join(work_dir, "packs", "pack-00")
    os.makedirs(packs_dir, exist_ok=True)

    quotes = []
    for q in selection.quotes:
        spans, err = find_spans(source_map, q.source_text)
        if err:
            spans = [dict(segment_id="s000000", start_sec=q.start_sec,
                          end_sec=q.end_sec)]
        role = "evidence"
        reason = (q.selection_reason or "").lower()
        for key, mapped in ROLE_BY_V1_REASON:
            if key in reason:
                role = mapped
                break
        quotes.append({
            "quote_id": q.id,
            "order": q.order,
            "role": role,
            "source_spans": spans,
            "exact_source_text": q.source_text,
            "context_before": "",
            "context_after": "",
            "display_en": q.display_en,
            "display_en_edits": [],
            "semantic_brief": {
                "claim": "",
                "rhetorical_function": role,
                "tone": "",
                "modality": "absolute",
                "resolved_references": {},
            },
            "faithful_zh": q.display_zh,
            "zh_candidates": [
                {"id": "a", "style": "faithful-natural", "text": q.display_zh},
                {"id": "b", "style": "spoken-compact", "text": q.display_zh},
                {"id": "c", "style": "memorable-restrained", "text": q.display_zh},
            ],
            "recommended_zh": q.display_zh,
            "compact_zh": q.display_zh,
            "editor_choice_reason": "migrated from V1; not re-edited",
            "entity_ids": [],
            "frame_time_sec": q.frame_time_sec,
            "review": {
                "fidelity_score": 0.0,
                "naturalness_score": 0.0,
                "source_confidence": 0.0,
                "ai_tone_risk": 10.0,
                "entity_integrity": "fail",
                "modality_integrity": "fail",
                "verdict": "manual_review",
                "issues": ["migrated from V1 without V2 review — must be "
                           "re-edited and re-reviewed before ready"],
            },
        })

    pack = {
        "schema_version": "2.0",
        "pack": {
            "pack_id": "pack-00",
            "slug": "v1-migration-draft",
            "core_claim": selection.angle.one_sentence_promise,
            "reader_value": selection.angle.target_reader,
        },
        "quotes": quotes,
    }
    out = os.path.join(packs_dir, "editorial_pack.json")
    backup = sel_path + ".v1.bak"
    if not os.path.exists(backup):
        shutil.copyfile(sel_path, backup)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(pack, fh, ensure_ascii=False, indent=2)
    return out
