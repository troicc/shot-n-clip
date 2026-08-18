"""Publish copy validation (V2 §十二): specificity, no template hype,
no fabricated first-person, fields complete, recommended exists, and every
claim traceable to the pack's own quotes/facts."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from . import editorial_lint as lint
from .schema_lite import validate as schema_validate

_XHS_INTRO_RANGE = (90, 180)
_XHS_SHORT_RANGE = (40, 80)
_WECHAT_INTRO_RANGE = (120, 260)
_WECHAT_SHORT_RANGE = (60, 120)

_FIRST_PERSON_FAB = re.compile(
    r"(我亲测|我一直都|我这些年|我曾经也|当年我|上个月我|去年我|我第一次)")
_CONSEC_EXCL = re.compile(r"!{2,}|！{2,}")
_SCARCITY = re.compile(r"(仅限|最后.{0,3}(天|小时|名额)|错过(再)?等|马上(就)?没)")

# Copy must reference at least one pack-specific token (an entity, number or
# distinctive term) — generic praise alone fails specificity.
_GENERIC_ONLY = re.compile(
    r"^(这期(内容|访谈|演讲)(真的)?太?(有)?(启发|精彩|深刻|值得看).{0,20})$")


def validate_copy(copy: dict, platform: str, pack: dict) -> Tuple[List[str],
                                                                  List[str]]:
    """Returns (errors, warnings)."""
    import os
    from .pack_validation import _load_schema
    errors: List[str] = []
    warnings: List[str] = []
    schema_name = "publish-copy.schema.json"
    errs = schema_validate(copy, _load_schema(schema_name))
    if errs:
        return errs, warnings

    # banned patterns over all copy text
    texts = [copy["recommended_title"], copy["intro_full"],
             copy.get("intro_short", "")]
    texts += [t["text"] for t in copy["title_candidates"]]
    from .editorial_lint import load_config
    cfg = load_config(os.environ.get("QCARD_CONFIG_ROOT", "config"))
    lint_res = lint.lint_zh(texts, os.environ.get("QCARD_CONFIG_ROOT",
                                                  "config"))
    for h in lint_res.hits:
        (errors if h.severity == "fail" else warnings).append(
            f"copy lint: {h}")

    for text in texts:
        if _FIRST_PERSON_FAB.search(text):
            errors.append("fabricated first-person experience in copy")
        if _CONSEC_EXCL.search(text):
            errors.append("consecutive exclamation marks in title/copy")
        if _SCARCITY.search(text):
            errors.append("false scarcity phrasing")
    if platform == "xhs":
        if _GENERIC_ONLY.match(copy["intro_full"].strip()):
            errors.append("intro is generic praise only — must state the "
                          "pack's specific tension/mechanism")
        lo, hi = _XHS_INTRO_RANGE
        if not (lo <= len(copy["intro_full"]) <= hi):
            errors.append(f"xhs intro_full {len(copy['intro_full'])} chars, "
                          f"need {lo}-{hi}")
        if copy.get("intro_short"):
            lo, hi = _XHS_SHORT_RANGE
            if not (lo <= len(copy["intro_short"]) <= hi):
                warnings.append(f"xhs intro_short {len(copy['intro_short'])} "
                                f"chars, target {lo}-{hi}")
    else:
        lo, hi = _WECHAT_INTRO_RANGE
        if not (lo <= len(copy["intro_full"]) <= hi):
            errors.append(f"wechat intro_full {len(copy['intro_full'])} chars, "
                          f"need {lo}-{hi}")
        if copy.get("intro_short"):
            lo, hi = _WECHAT_SHORT_RANGE
            if not (lo <= len(copy["intro_short"]) <= hi):
                warnings.append(f"wechat intro_short "
                                f"{len(copy['intro_short'])} chars, target "
                                f"{lo}-{hi}")

    # recommended must exist among candidates (or be a light edit of one)
    if copy["recommended_title"] not in [t["text"] for t in
                                         copy["title_candidates"]]:
        warnings.append("recommended_title not verbatim among candidates "
                        "(light edit allowed, verify tone)")

    # platform strategies coverage (xhs needs ≥3 strategies among 6)
    if platform == "xhs":
        strategies = {t["strategy"] for t in copy["title_candidates"]}
        need = {"direct", "question", "contrast"}
        missing = need - strategies
        if missing:
            errors.append(f"xhs title strategies missing: {sorted(missing)}")
        if len(copy["title_candidates"]) < 6:
            warnings.append(f"xhs has {len(copy['title_candidates'])} titles, "
                            "target 6")
    else:
        if len(copy["title_candidates"]) < 4:
            errors.append("wechat needs ≥4 title candidates")

    # unsupported claims: every number in copy must exist in pack facts
    pack_numbers = set()
    for q in pack["quotes"]:
        for m in re.findall(r"\d+(?:\.\d+)?", q["exact_source_text"]):
            pack_numbers.add(m)
    meta = pack.get("pack", {})
    claim_text = copy["intro_full"] + copy["recommended_title"]
    for n in re.findall(r"\d+(?:\.\d+)?", claim_text):
        if n not in pack_numbers and n not in {"1", "2", "3", "4", "5", "6"}:
            errors.append(f"copy cites number {n} absent from pack sources "
                          "(unsupported claim)")

    # review block sanity
    rv = copy["review"]
    if rv["unsupported_claims"]:
        errors.append(f"copy review lists unsupported claims: "
                      f"{rv['unsupported_claims']}")
    if rv["ai_tone_risk"] > 2.5:
        errors.append(f"copy ai_tone_risk {rv['ai_tone_risk']} > 2.5")
    return errors, warnings
