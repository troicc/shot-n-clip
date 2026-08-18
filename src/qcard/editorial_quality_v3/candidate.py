"""Candidate-pool validation."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .common import (PASS_THRESHOLD, SCHEMA_VERSION, Report, _nonempty,
                     detect_context_dependency, similarity, _norm)

def validate_candidate_pool(
    data: Any, source_map: Optional[Mapping[str, Any]] = None
) -> Tuple[Report, Dict[str, dict]]:
    report = Report()
    index: Dict[str, dict] = {}
    if not isinstance(data, dict):
        report.error("candidate_pool must be an object")
        return report, index
    if data.get("schema_version") != SCHEMA_VERSION:
        report.error(f"candidate_pool.schema_version must be {SCHEMA_VERSION!r}")
    candidates = data.get("candidates")
    if not isinstance(candidates, list):
        report.error("candidate_pool.candidates must be an array")
        return report, index
    if len(candidates) < 8:
        report.warn(
            f"candidate pool has only {len(candidates)} items; broad mining normally needs >=8 "
            "before pack construction"
        )

    source_segments: Dict[str, Mapping[str, Any]] = {}
    if source_map is not None:
        raw_segments = source_map.get("segments") if isinstance(source_map, Mapping) else None
        if not isinstance(raw_segments, list):
            report.error("source_map.segments must be an array when source_map is supplied")
        else:
            source_segments = {
                str(seg.get("segment_id")): seg
                for seg in raw_segments
                if isinstance(seg, Mapping) and _nonempty(seg.get("segment_id"))
            }

    for pos, candidate in enumerate(candidates):
        tag = f"candidate[{pos}]"
        if not isinstance(candidate, dict):
            report.error(f"{tag} must be an object")
            continue
        cid = candidate.get("candidate_id")
        if not _nonempty(cid):
            report.error(f"{tag}.candidate_id must be non-empty")
            continue
        tag = str(cid)
        if not re.fullmatch(r"c[0-9]{3,6}", str(cid)):
            report.error(f"{tag}.candidate_id must match c### or longer (got {cid!r})")
        if cid in index:
            report.error(f"duplicate candidate_id {cid!r}")
            continue
        index[str(cid)] = candidate

        required_text = (
            "exact_source_text",
            "context_before",
            "context_after",
            "claim_signature",
            "new_information",
        )
        for key in required_text:
            if not _nonempty(candidate.get(key)):
                report.error(f"{tag}.{key} must be a non-empty string")
        segment_ids = candidate.get("segment_ids")
        if not isinstance(segment_ids, list) or not segment_ids:
            report.error(f"{tag}.segment_ids must be a non-empty array")
            segment_ids = []
        elif len(set(str(x) for x in segment_ids)) != len(segment_ids):
            report.error(f"{tag}.segment_ids contains duplicates")

        if source_segments and segment_ids:
            resolved_segments: List[Mapping[str, Any]] = []
            for sid in segment_ids:
                seg = source_segments.get(str(sid))
                if seg is None:
                    report.error(f"{tag}: segment_id {sid!r} not found in source_map")
                else:
                    resolved_segments.append(seg)
            if resolved_segments:
                resolved_segments.sort(key=lambda seg: float(seg.get("start_sec", 0)))
                for left, right in zip(resolved_segments, resolved_segments[1:]):
                    gap = float(right.get("start_sec", 0)) - float(left.get("end_sec", 0))
                    if gap > 1.5:
                        report.error(
                            f"{tag}: source segments are not contiguous (gap {gap:.2f}s > 1.5s)"
                        )
                joined = " ".join(str(seg.get("raw_text", "")) for seg in resolved_segments)
                if _norm(str(candidate.get("exact_source_text", ""))) not in _norm(joined):
                    report.error(
                        f"{tag}: exact_source_text is not contained in declared source_map segments"
                    )
                declared_start = candidate.get("start_sec")
                declared_end = candidate.get("end_sec")
                actual_start = float(resolved_segments[0].get("start_sec", 0))
                actual_end = float(resolved_segments[-1].get("end_sec", 0))
                if isinstance(declared_start, (int, float)) and abs(float(declared_start) - actual_start) > 0.25:
                    report.error(
                        f"{tag}: start_sec {declared_start} does not match first segment {actual_start}"
                    )
                if isinstance(declared_end, (int, float)) and abs(float(declared_end) - actual_end) > 0.25:
                    report.error(
                        f"{tag}: end_sec {declared_end} does not match last segment {actual_end}"
                    )
        start, end = candidate.get("start_sec"), candidate.get("end_sec")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or end <= start:
            report.error(f"{tag}: start_sec/end_sec must be numeric and end_sec > start_sec")

        source = str(candidate.get("exact_source_text", ""))
        computed_flags = detect_context_dependency(source)
        declared_flags = candidate.get("context_dependency_flags")
        if not isinstance(declared_flags, list):
            report.error(f"{tag}.context_dependency_flags must be an array")
            declared_flags = []
        for flag in computed_flags:
            if flag not in declared_flags:
                report.error(f"{tag}: undeclared context-dependency flag {flag!r}")

        status = candidate.get("standalone_status")
        verdict = candidate.get("verdict")
        if status not in {"independent", "repairable", "reject"}:
            report.error(f"{tag}.standalone_status invalid: {status!r}")
        if verdict not in {"pass", "reject", "manual_review"}:
            report.error(f"{tag}.verdict invalid: {verdict!r}")

        scores = candidate.get("scores")
        if not isinstance(scores, dict):
            report.error(f"{tag}.scores must be an object")
            scores = {}
        for key, threshold in PASS_THRESHOLD.items():
            value = scores.get(key)
            if not isinstance(value, (int, float)):
                report.error(f"{tag}.scores.{key} must be numeric")
            elif not 0 <= float(value) <= 10:
                report.error(f"{tag}.scores.{key} must be within 0..10")
            elif verdict == "pass" and float(value) < threshold:
                report.error(
                    f"{tag}: pass verdict but scores.{key}={value} below {threshold}"
                )

        reasons = candidate.get("rejection_reasons")
        if not isinstance(reasons, list):
            report.error(f"{tag}.rejection_reasons must be an array")
        if verdict == "pass":
            fatal = {
                "bare_yes_no_statistic",
                "bare_reply",
                "unresolved_opening_reference",
                "too_short_to_carry_claim",
            }
            bad = sorted(fatal & set(computed_flags))
            if bad:
                report.error(f"{tag}: pass candidate is not standalone ({', '.join(bad)})")
            if status != "independent":
                report.error(f"{tag}: pass candidate must have standalone_status='independent'")
            if isinstance(reasons, list) and reasons:
                report.error(f"{tag}: pass candidate must not carry rejection_reasons")
            if len(source) > 240:
                report.error(f"{tag}: source text is too long for a quote card ({len(source)} chars)")

    # Candidate-level duplicate claims create bad packs later; catch them early.
    passed = [c for c in index.values() if c.get("verdict") == "pass"]
    for i, left in enumerate(passed):
        for right in passed[i + 1 :]:
            sim = similarity(str(left.get("claim_signature", "")), str(right.get("claim_signature", "")))
            if sim >= 0.84:
                report.warn(
                    f"candidate claims nearly duplicate: {left.get('candidate_id')} vs "
                    f"{right.get('candidate_id')} ({sim:.0%})"
                )
    return report, index
