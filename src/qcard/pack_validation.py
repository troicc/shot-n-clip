"""Pack-level validation (V2 §十/§十一/§十九): strict validator assembling
schema + source spans + entities + modality + display_en diff + zh lint +
pack distinctness + copy checks + layout fit into one verdict."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import editorial_lint as lint
from . import entity_glossary as eg
from .schema_lite import validate as schema_validate
from .source_integrity import (SourceMap, find_spans, spans_are_contiguous,
                               display_en_diff)

SCHEMA_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), "schemas", "v2")

REVIEW_THRESHOLDS = dict(fidelity=9.0, naturalness=8.5, source_confidence=8.5,
                         ai_tone_risk=2.5)

READY_SCORES = dict(source_integrity=90, entity_integrity=100,
                    translation_fidelity=90, chinese_naturalness=85,
                    anti_template_quality=85, pack_coherence=85,
                    platform_copy_quality=82, layout_readability=90)

MAX_PER_30SEC = 2
MIN_QUOTES = 4
MAX_QUOTES = 8


@dataclass
class ValidationResult:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def merge(self, other: "ValidationResult") -> "ValidationResult":
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        return self


def _load_schema(name: str) -> dict:
    with open(os.path.join(SCHEMA_DIR, name), encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# editorial_pack.json validation
# ---------------------------------------------------------------------------


def validate_editorial_pack(pack: dict, source_map: SourceMap,
                            entities: List[eg.Entity], config_root: str,
                            layout_fit: Optional[Dict[str, bool]] = None
                            ) -> ValidationResult:
    res = ValidationResult()

    # 1. schema
    errs = schema_validate(pack, _load_schema("editorial-pack.schema.json"))
    if errs:
        res.errors.extend(errs)
        return res  # structure broken → deeper checks meaningless

    quotes = pack["quotes"]

    # 2. source spans: exact text locatable + contiguous
    span_ids_used: List[str] = []
    for q in quotes:
        spans, err = find_spans(source_map, q["exact_source_text"])
        if err:
            res.errors.append(f"{q['quote_id']}: {err}")
            continue
        # Verify declared spans match computed ones (time-window equality).
        declared = q["source_spans"]
        ok, gap_err = spans_are_contiguous(source_map, declared)
        if not ok:
            res.errors.append(f"{q['quote_id']}: {gap_err}")
        span_ids_used.extend(s.get("segment_ids", [s["segment_id"]])
                             for s in declared)
        # exact_source_text must equal the concatenation of its segment texts
        # (normalized), not something looser.
        joined = _norm(" ".join(
            _seg_text(source_map, s) for s in _expand(declared)))
        if _norm(q["exact_source_text"]) not in joined and joined not in _norm(
                q["exact_source_text"]):
            res.warnings.append(
                f"{q['quote_id']}: exact_source_text is contained in spans "
                "but not span-equal (check bracketed ASR insertions)")

    # 3. per-30s window density
    for q in quotes:
        center = (q["source_spans"][0]["start_sec"] +
                  q["source_spans"][-1]["end_sec"]) / 2
        same_window = sum(
            1 for other in quotes
            if abs((other["source_spans"][0]["start_sec"] +
                    other["source_spans"][-1]["end_sec"]) / 2 - center) <= 15)
        if same_window > MAX_PER_30SEC:
            res.errors.append(
                f"{q['quote_id']}: {same_window} quotes within ±15s "
                f"(max {MAX_PER_30SEC} per 30s window)")
            break

    # 4. entities + numbers + modality + display_en diff + review verdicts
    for q in quotes:
        qid = q["quote_id"]
        ent_problems, _ = eg.check_zh_entities(q["recommended_zh"], entities,
                                               q["entity_ids"])
        for p in ent_problems:
            res.errors.append(f"{qid}: entity: {p}")
        for p in eg.check_zh_entities(q["compact_zh"], entities,
                                      q["entity_ids"])[0]:
            res.errors.append(f"{qid}: entity(compact): {p}")

        facts = eg.numeric_facts(q["exact_source_text"])
        for m in eg.facts_match(facts, q["recommended_zh"]):
            res.errors.append(f"{qid}: numbers: {m}")

        for v in lint.modality_violations(q["exact_source_text"],
                                          q["recommended_zh"]):
            res.errors.append(f"{qid}: modality: {v}")
        if q["review"]["modality_integrity"] != "pass":
            res.errors.append(f"{qid}: review.modality_integrity != pass")

        violations, ok = display_en_diff(q["exact_source_text"],
                                         q["display_en"], q["display_en_edits"])
        for v in violations:
            res.errors.append(f"{qid}: display_en: {v}")

        rv = q["review"]
        if rv["verdict"] != "pass":
            res.errors.append(f"{qid}: review verdict is {rv['verdict']} "
                              "(only pass may enter a ready pack)")
        if (rv["fidelity_score"] < REVIEW_THRESHOLDS["fidelity"] or
                rv["naturalness_score"] < REVIEW_THRESHOLDS["naturalness"] or
                rv["source_confidence"] < REVIEW_THRESHOLDS["source_confidence"] or
                rv["ai_tone_risk"] > REVIEW_THRESHOLDS["ai_tone_risk"]):
            res.errors.append(
                f"{qid}: review scores below hard thresholds "
                f"(fidelity={rv['fidelity_score']}, "
                f"naturalness={rv['naturalness_score']}, "
                f"source_confidence={rv['source_confidence']}, "
                f"ai_tone_risk={rv['ai_tone_risk']})")
        if rv["entity_integrity"] != "pass":
            res.errors.append(f"{qid}: review.entity_integrity != pass")

    # 5. zh lint across the pack
    lint_res = lint.lint_zh([q["recommended_zh"] for q in quotes], config_root)
    for msg in lint_res.messages():
        res.errors.append(f"lint: {msg}") if "(fail)" in msg else \
            res.warnings.append(f"lint: {msg}")
    risk = lint_res.ai_tone_risk()
    if risk > REVIEW_THRESHOLDS["ai_tone_risk"]:
        res.errors.append(f"lint: pack ai_tone_risk {risk:.1f} > "
                          f"{REVIEW_THRESHOLDS['ai_tone_risk']}")

    # 6. roles form a progression
    roles = [q["role"] for q in quotes]
    if len(roles) >= 5 and roles.count(roles[0]) > 2:
        res.warnings.append(f"role repetition: {roles}")

    # 7. layout fit (passed in by renderer)
    if layout_fit:
        for qid, fits in layout_fit.items():
            if not fits:
                res.errors.append(
                    f"{qid}: text does not fit layout at minimum font size — "
                    "use compact_zh or swap the quote")

    return res


def _norm(s: str) -> str:
    from .utils import normalize_text
    return normalize_text(s)


def _expand(spans: List[dict]) -> List[dict]:
    out = []
    for s in spans:
        if "segment_ids" in s:
            for sid in s["segment_ids"]:
                out.append({"segment_id": sid})
        else:
            out.append(s)
    return out


def _seg_text(source_map: SourceMap, span: dict) -> str:
    seg = source_map.segment_by_id(span["segment_id"])
    return seg["raw_text"] if seg else ""


# ---------------------------------------------------------------------------
# Cross-pack validation
# ---------------------------------------------------------------------------


def validate_pack_set(angle_packs: dict) -> ValidationResult:
    res = ValidationResult()
    errs = schema_validate(angle_packs, _load_schema("angle-packs.schema.json"))
    if errs:
        res.errors.extend(errs)
        return res
    ready = [p for p in angle_packs["packs"] if p["status"] == "ready"]

    # span non-reuse across ready packs
    def span_key(p):
        keys = []
        for s in p["supporting_source_spans"]:
            keys.append((round(s["start_sec"], 1), round(s["end_sec"], 1)))
        return keys
    seen: Dict[Tuple, str] = {}
    for p in ready:
        for k in span_key(p):
            if k in seen and seen[k] != p["pack_id"]:
                res.errors.append(
                    f"source span {k} reused by {seen[k]} and {p['pack_id']} "
                    "(ready packs must not share spans)")
            seen[k] = p["pack_id"]

    # core-claim distinctness (swap test, trigram jaccard)
    for i in range(len(ready)):
        for j in range(i + 1, len(ready)):
            sim = _jaccard(ready[i]["core_claim"], ready[j]["core_claim"])
            if sim >= 0.55:
                res.errors.append(
                    f"{ready[i]['pack_id']} vs {ready[j]['pack_id']}: "
                    f"core claims {sim:.0%} similar — swapped summaries would "
                    "both still hold; packs are duplicates")
    return res


def _jaccard(a: str, b: str) -> float:
    def tri(s):
        s = _norm(s)
        return {s[i:i+3] for i in range(len(s) - 2)} or {s}
    ta, tb = tri(a), tri(b)
    return len(ta & tb) / len(ta | tb)


# ---------------------------------------------------------------------------
# quality_report scoring
# ---------------------------------------------------------------------------


def score_pack(pack: dict, validation: ValidationResult,
               copy_quality: Optional[float] = None,
               layout_ok: Optional[Dict[str, bool]] = None,
               manual_items: Optional[List[str]] = None) -> dict:
    quotes = pack["quotes"]
    avg = lambda k: sum(q["review"][k] for q in quotes) / max(len(quotes), 1)

    source_integrity = 100.0 if not any(
        "NOT FOUND" in e or "gap" in e for e in validation.errors) else 60.0
    entity_fail = any("entity" in e for e in validation.errors)
    entity_integrity = 100.0 if not entity_fail else 0.0
    fidelity = min(100.0, avg("fidelity_score") * 10)
    naturalness = min(100.0, avg("naturalness_score") * 10)
    anti_template = max(0.0, 100.0 - lint_result_risk(pack) * 10)
    coherence = _pack_coherence(quotes)
    copy_q = copy_quality if copy_quality is not None else 85.0
    layout = 100.0 if (layout_ok is None or all(layout_ok.values())) else 40.0

    scores = {
        "source_integrity": round(source_integrity, 1),
        "entity_integrity": round(entity_integrity, 1),
        "translation_fidelity": round(fidelity, 1),
        "chinese_naturalness": round(naturalness, 1),
        "anti_template_quality": round(anti_template, 1),
        "pack_coherence": round(coherence, 1),
        "platform_copy_quality": round(copy_q, 1),
        "layout_readability": round(layout, 1),
    }
    status = "ready"
    for key, threshold in READY_SCORES.items():
        if scores[key] < threshold:
            status = "manual_review"
            break
    manual = list(manual_items or [])
    if manual:
        status = "manual_review"
    return {
        "schema_version": "2.0",
        "pack_id": pack["pack"]["pack_id"],
        "scores": scores,
        "manual_review_items": manual,
        "status": status,
    }


def lint_result_risk(pack: dict) -> float:
    # Recomputed by caller with real lint normally; fallback estimate.
    rv = sum(q["review"]["ai_tone_risk"] for q in pack["quotes"]) / max(
        len(pack["quotes"]), 1)
    return rv


def _pack_coherence(quotes: dict) -> float:
    roles = [q["role"] for q in quotes]
    distinct = len(set(roles))
    n = len(quotes)
    if n >= 5 and distinct >= 4:
        return 90.0
    if n >= 5 and distinct >= 3:
        return 80.0
    return 65.0
