"""Translation-audit and source-binding validation."""
from __future__ import annotations

import re
from typing import Any, Dict, Mapping

from .common import (SCHEMA_VERSION, Report, _LEDGER_KEYS, _NATURALNESS_KEYS,
                     _nonempty, _norm, awkward_zh_flags)

def _pack_quote_index(pack: Mapping[str, Any]) -> Dict[str, dict]:
    quotes = pack.get("quotes")
    if not isinstance(quotes, list):
        return {}
    return {
        str(q.get("quote_id")): q
        for q in quotes
        if isinstance(q, dict) and _nonempty(q.get("quote_id"))
    }


def validate_translation_audit(data: Any, editorial_pack: Any) -> Report:
    report = Report()
    if not isinstance(data, dict):
        report.error("translation_audit must be an object")
        return report
    if data.get("schema_version") != SCHEMA_VERSION:
        report.error(f"translation_audit.schema_version must be {SCHEMA_VERSION!r}")
    if not isinstance(editorial_pack, dict):
        report.error("editorial_pack must be an object")
        return report
    pack_quotes = _pack_quote_index(editorial_pack)
    audit_quotes = data.get("quotes")
    if not isinstance(audit_quotes, list):
        report.error("translation_audit.quotes must be an array")
        return report
    seen: set[str] = set()
    for pos, audit in enumerate(audit_quotes):
        tag = f"translation_audit.quotes[{pos}]"
        if not isinstance(audit, dict):
            report.error(f"{tag} must be an object")
            continue
        qid = audit.get("quote_id")
        if not _nonempty(qid) or str(qid) not in pack_quotes:
            report.error(f"{tag}.quote_id {qid!r} not found in editorial_pack")
            continue
        qid = str(qid)
        if qid in seen:
            report.error(f"duplicate translation audit for {qid}")
            continue
        seen.add(qid)
        quote = pack_quotes[qid]
        source = str(quote.get("exact_source_text", ""))
        zh = str(quote.get("recommended_zh", ""))

        units = audit.get("source_claim_units")
        if not isinstance(units, list) or not units:
            report.error(f"{qid}.source_claim_units must be a non-empty array")
        else:
            for idx, unit in enumerate(units):
                if not isinstance(unit, dict):
                    report.error(f"{qid}.source_claim_units[{idx}] must be an object")
                    continue
                for key in ("source", "meaning_zh"):
                    if not _nonempty(unit.get(key)):
                        report.error(f"{qid}.source_claim_units[{idx}].{key} must be non-empty")
                if unit.get("required") is True and unit.get("status") != "preserved":
                    report.error(
                        f"{qid}.source_claim_units[{idx}] is required but status={unit.get('status')!r}"
                    )

        if not _nonempty(audit.get("back_translation_en")):
            report.error(f"{qid}.back_translation_en must be non-empty")

        ledger = audit.get("fidelity_ledger")
        if not isinstance(ledger, dict):
            report.error(f"{qid}.fidelity_ledger must be an object")
        else:
            for key in _LEDGER_KEYS:
                value = ledger.get(key)
                if not isinstance(value, list):
                    report.error(f"{qid}.fidelity_ledger.{key} must be an array")
                elif value:
                    report.error(f"{qid}.fidelity_ledger.{key} must be empty for a publishable quote")

        checks = audit.get("naturalness_checks")
        if not isinstance(checks, dict):
            report.error(f"{qid}.naturalness_checks must be an object")
        else:
            for key in _NATURALNESS_KEYS:
                if checks.get(key) is not True:
                    report.error(f"{qid}.naturalness_checks.{key} must be true")

        if audit.get("review_verdict") != "pass":
            report.error(f"{qid}.review_verdict must be 'pass'")
        issues = audit.get("issues")
        if not isinstance(issues, list):
            report.error(f"{qid}.issues must be an array")
        elif issues:
            report.error(f"{qid}: passing audit must have no unresolved issues")

        for flag in awkward_zh_flags(source, zh):
            report.error(f"{qid}: known translation regression {flag}")
        hanzi = len(re.findall(r"[\u3400-\u9fff]", zh))
        if hanzi < 6:
            report.error(f"{qid}: recommended_zh is too fragmentary ({hanzi} Han characters)")
        elif hanzi > 42:
            report.warn(f"{qid}: recommended_zh is long ({hanzi} Han characters); verify layout")

    missing = sorted(set(pack_quotes) - seen)
    if missing:
        report.error(f"translation audit missing quote(s): {', '.join(missing)}")
    return report


def validate_pack_binding(
    pack: Mapping[str, Any],
    selection_pack: Mapping[str, Any],
    candidate_index: Mapping[str, dict],
    translation_audit: Mapping[str, Any],
) -> Report:
    """Ensure no selected source was silently swapped during translation."""
    report = Report()
    pack_quotes = sorted(
        _pack_quote_index(pack).values(), key=lambda q: int(q.get("order", 0))
    )
    selected = selection_pack.get("selected")
    if not isinstance(selected, list):
        report.error("selection pack has no selected array")
        return report
    audits = translation_audit.get("quotes") if isinstance(translation_audit, dict) else None
    if not isinstance(audits, list):
        report.error("translation audit has no quotes array")
        return report
    audit_by_qid = {
        str(item.get("quote_id")): item
        for item in audits
        if isinstance(item, dict) and _nonempty(item.get("quote_id"))
    }
    if len(pack_quotes) != len(selected):
        report.error(
            f"editorial_pack has {len(pack_quotes)} quotes but selection_audit has {len(selected)}"
        )
        return report
    for quote, selected_item in zip(pack_quotes, selected):
        qid = str(quote.get("quote_id"))
        cid = str(selected_item.get("candidate_id", ""))
        candidate = candidate_index.get(cid)
        if not candidate:
            report.error(f"{qid}: selected candidate {cid!r} missing")
            continue
        audit = audit_by_qid.get(qid)
        if not audit:
            report.error(f"{qid}: translation audit entry missing")
            continue
        if str(audit.get("candidate_id", "")) != cid:
            report.error(
                f"{qid}: translation audit candidate_id {audit.get('candidate_id')!r} != selected {cid!r}"
            )
        if _norm(str(quote.get("exact_source_text", ""))) != _norm(
            str(candidate.get("exact_source_text", ""))
        ):
            report.error(f"{qid}: exact_source_text changed after candidate selection")
        if quote.get("role") != selected_item.get("role"):
            report.error(
                f"{qid}: role {quote.get('role')!r} != selection role {selected_item.get('role')!r}"
            )
    return report
