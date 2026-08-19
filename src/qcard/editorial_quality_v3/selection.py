"""Independent pack-selection validation."""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Mapping, Tuple

from .common import DIRECT_SUPPORT, SCHEMA_VERSION, Report, _nonempty, similarity
from .density import (locality_flags, matched_anchors, valid_anchor_term)


def validate_selection_audit(
    data: Any, candidate_index: Mapping[str, dict]
) -> Tuple[Report, Dict[str, dict]]:
    report = Report()
    packs_index: Dict[str, dict] = {}
    if not isinstance(data, dict):
        report.error("selection_audit must be an object")
        return report, packs_index
    if data.get("schema_version") != SCHEMA_VERSION:
        report.error(f"selection_audit.schema_version must be {SCHEMA_VERSION!r}")
    packs = data.get("packs")
    if not isinstance(packs, list):
        report.error("selection_audit.packs must be an array")
        return report, packs_index

    used_candidates: Dict[str, str] = {}
    for pos, pack in enumerate(packs):
        if not isinstance(pack, dict):
            report.error(f"packs[{pos}] must be an object")
            continue
        pid = pack.get("pack_id")
        if not _nonempty(pid):
            report.error(f"packs[{pos}].pack_id must be non-empty")
            continue
        pid = str(pid)
        packs_index[pid] = pack
        status = pack.get("status")
        if status not in {"ready", "rejected", "manual_review", "candidate"}:
            report.error(f"{pid}.status invalid: {status!r}")
        core_claim = pack.get("core_claim")
        if not _nonempty(core_claim):
            report.error(f"{pid}.core_claim must be non-empty")
            core_claim = ""
        focus_question = pack.get("focus_question")
        if status == "ready" and not _nonempty(focus_question):
            report.error(f"{pid}.focus_question must be non-empty for a ready pack")
            focus_question = ""
        reader_value = pack.get("reader_value")
        if status == "ready" and not _nonempty(reader_value):
            report.error(f"{pid}.reader_value must be non-empty for a ready pack")

        anchor_terms = pack.get("anchor_terms")
        if not isinstance(anchor_terms, list):
            report.error(f"{pid}.anchor_terms must be an array")
            anchor_terms = []
        clean_anchors = [str(term).strip() for term in anchor_terms if _nonempty(term)]
        if len(clean_anchors) != len(anchor_terms):
            report.error(f"{pid}.anchor_terms must contain only non-empty strings")
        invalid_anchors = [term for term in clean_anchors if not valid_anchor_term(term)]
        if invalid_anchors:
            report.error(f"{pid}.anchor_terms contains generic/invalid terms: {invalid_anchors}")
        if status == "ready" and not 1 <= len(clean_anchors) <= 3:
            report.error(f"{pid}: ready pack needs 1-3 concrete anchor_terms")
        if clean_anchors and not matched_anchors(
            clean_anchors, str(core_claim), str(focus_question)
        ):
            report.error(
                f"{pid}: neither core_claim nor focus_question expresses an anchor_term"
            )

        selected = pack.get("selected")
        if not isinstance(selected, list):
            report.error(f"{pid}.selected must be an array")
            continue
        # Four strong lines beat six weak ones.  Five is the default bilingual
        # maximum borrowed from native-subtitle collage practice.
        if status == "ready" and not 4 <= len(selected) <= 5:
            report.error(f"{pid}: ready pack needs 4-5 selected quotes, found {len(selected)}")

        roles: List[str] = []
        incremental: List[str] = []
        selected_candidates: List[dict] = []
        anchor_coverage: Counter[str] = Counter()
        for idx, item in enumerate(selected):
            tag = f"{pid}.selected[{idx}]"
            if not isinstance(item, dict):
                report.error(f"{tag} must be an object")
                continue
            cid = item.get("candidate_id")
            if not _nonempty(cid) or str(cid) not in candidate_index:
                report.error(f"{tag}.candidate_id {cid!r} not found in candidate_pool")
                continue
            cid = str(cid)
            candidate = candidate_index[cid]
            selected_candidates.append(candidate)
            if status == "ready" and candidate.get("verdict") != "pass":
                report.error(f"{tag}: selected candidate {cid} does not have verdict='pass'")
            if status == "ready" and cid in used_candidates and used_candidates[cid] != pid:
                report.error(
                    f"candidate {cid} reused by ready packs {used_candidates[cid]} and {pid}"
                )
            if status == "ready":
                used_candidates[cid] = pid
            support = item.get("support")
            if status == "ready" and support not in DIRECT_SUPPORT:
                report.error(f"{tag}: support must be direct/essential, got {support!r}")
            role = item.get("role")
            if role not in {"hook", "problem", "mechanism", "evidence", "method", "close"}:
                report.error(f"{tag}.role invalid: {role!r}")
            else:
                roles.append(str(role))
            value = item.get("incremental_value")
            if not _nonempty(value):
                report.error(f"{tag}.incremental_value must be non-empty")
            else:
                incremental.append(str(value))

            candidate_topics = candidate.get("topic_terms")
            if not isinstance(candidate_topics, list):
                candidate_topics = []
            matched = matched_anchors(
                clean_anchors,
                str(candidate.get("exact_source_text", "")),
                str(candidate.get("claim_signature", "")),
                " ".join(str(term) for term in candidate_topics),
            )
            if status == "ready" and clean_anchors and not matched:
                report.error(
                    f"{tag}: candidate {cid} matches none of pack anchor_terms {clean_anchors}"
                )
            for term in matched:
                anchor_coverage[term] += 1

        if status == "ready" and selected:
            if roles and roles[0] != "hook":
                report.error(f"{pid}: first quote role must be hook, got {roles[0]!r}")
            if roles and roles[-1] != "close":
                report.error(f"{pid}: last quote role must be close, got {roles[-1]!r}")
            if len(set(roles)) < 4:
                report.error(f"{pid}: pack needs at least 4 distinct rhetorical roles, got {roles}")

            review = pack.get("selection_review")
            if not isinstance(review, dict) or review.get("verdict") != "pass":
                report.error(f"{pid}: selection_review.verdict must be 'pass'")
            elif review.get("issues"):
                report.error(f"{pid}: passing selection_review must have an empty issues array")

            # Every line must add a different proposition, not merely restate the theme.
            for i, left in enumerate(selected_candidates):
                for right in selected_candidates[i + 1 :]:
                    sim = similarity(
                        str(left.get("claim_signature", "")),
                        str(right.get("claim_signature", "")),
                    )
                    if sim >= 0.70:
                        report.error(
                            f"{pid}: selected claims {left.get('candidate_id')} and "
                            f"{right.get('candidate_id')} are redundant ({sim:.0%})"
                        )
            for i, left in enumerate(incremental):
                for right in incremental[i + 1 :]:
                    sim = similarity(left, right)
                    if sim >= 0.75:
                        report.error(
                            f"{pid}: incremental_value entries repeat the same contribution ({sim:.0%})"
                        )

            # Native-subtitle collages work because the lines form one nearby,
            # chronological argument.  The former dispersion rule pushed agents
            # to assemble survey, school, career and AI fragments into one card.
            for flag in locality_flags(selected_candidates):
                report.error(f"{pid}: source locality failure {flag}")

            if clean_anchors:
                dominant = max(anchor_coverage.values(), default=0)
                minimum = max(3, len(selected_candidates) - 1)
                if dominant < minimum:
                    report.error(
                        f"{pid}: no anchor_term connects enough lines "
                        f"(best coverage {dominant}/{len(selected_candidates)}, need {minimum})"
                    )
    return report, packs_index
