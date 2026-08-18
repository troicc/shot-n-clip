"""Shared primitives for the deterministic V3 editorial quality gate."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

SCHEMA_VERSION = "3.0"
READY_STATUSES = {"ready", "pass"}
DIRECT_SUPPORT = {"direct", "essential"}
PASS_THRESHOLD = {
    "standalone": 8.0,
    "specificity": 7.0,
    "information_gain": 7.0,
    "source_confidence": 8.5,
    "compression": 6.0,
}

_BARE_YES_NO = re.compile(
    r"^\s*(?:only\s+)?\d+(?:\.\d+)?\s*(?:percent|%)?"
    r"(?:\s+of\s+[^,.!?]{1,36})?\s+"
    r"(?:said|say|answered|responded)\s+(?:yes|no)\s*[.!?]?\s*$",
    re.IGNORECASE,
)
_BARE_REPLY = re.compile(
    r"^\s*(?:yes|no|exactly|absolutely|probably|maybe|of course)\s*[.!?]?\s*$",
    re.IGNORECASE,
)
_UNRESOLVED_OPENING = re.compile(
    r"^\s*(?:this|that|it|they|them|those|these|he|she|which|what)\b",
    re.IGNORECASE,
)
_CONNECTOR_OPENING = re.compile(
    r"^\s*(?:but|and|so|because|therefore|which is why|that's why|then)\b",
    re.IGNORECASE,
)

# These are not generic "AI detectors".  They are concrete regressions seen in
# this project or high-confidence Chinese calques that should be revised.
_AWKWARD_ZH: Sequence[Tuple[str, re.Pattern[str]]] = (
    ("learning_happens_itself", re.compile(r"学习自己会发生")),
    ("zero_effort_calque", re.compile(r"零(?:刻意|有意识|意识)?努力")),
    ("automatic_study_calque", re.compile(r"自动(?:地)?(?:去)?(?:学|学习|钻研)")),
    ("impact_beyond_self_fragment", re.compile(r"影响\s*(?:远)?超自己")),
    ("for_fascinated_people_calque", re.compile(r"对着迷的人")),
    ("study_fascinated_things", re.compile(r"学着迷的东西")),
    ("mechanism_calque", re.compile(r"着迷自带(?:机制|动力)")),
    ("literal_big_footprints", re.compile(r"留下(?:很大)?的脚印")),
    ("should_follow_is", re.compile(r"该追随的是")),
    ("ambivalent_flattened", re.compile(r"本来就没感觉的")),
)

_NATURALNESS_KEYS = (
    "native_without_source",
    "read_aloud",
    "collocation",
    "no_translationese",
    "no_slogan_clipping",
)
_LEDGER_KEYS = ("additions", "omissions", "strengthenings", "weakenings")


@dataclass
class Report:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def merge(self, other: "Report", prefix: str = "") -> None:
        lead = f"{prefix}: " if prefix else ""
        self.errors.extend(lead + item for item in other.errors)
        self.warnings.extend(lead + item for item in other.warnings)

    def to_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "errors": self.errors, "warnings": self.warnings}


def _read_json(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError as exc:
        raise ValueError(f"missing required file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9\u3400-\u9fff]+", "", text.lower())


def _trigrams(text: str) -> set[str]:
    norm = _norm(text)
    if not norm:
        return set()
    if len(norm) < 3:
        return {norm}
    return {norm[i : i + 3] for i in range(len(norm) - 2)}


def similarity(a: str, b: str) -> float:
    left, right = _trigrams(a), _trigrams(b)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def detect_context_dependency(source_text: str) -> List[str]:
    """Return high-confidence reasons a quote cannot stand alone."""
    text = source_text.strip()
    flags: List[str] = []
    if _BARE_YES_NO.match(text):
        flags.append("bare_yes_no_statistic")
    if _BARE_REPLY.match(text):
        flags.append("bare_reply")
    if _UNRESOLVED_OPENING.match(text):
        flags.append("unresolved_opening_reference")
    if _CONNECTOR_OPENING.match(text):
        flags.append("connector_without_setup")
    words = re.findall(r"[A-Za-z0-9']+", text)
    if 0 < len(words) < 4:
        flags.append("too_short_to_carry_claim")
    return flags


def awkward_zh_flags(source_text: str, zh_text: str) -> List[str]:
    flags: List[str] = []
    for name, pattern in _AWKWARD_ZH:
        if pattern.search(zh_text):
            flags.append(name)

    source = source_text.lower()
    # Known concept-injection regression: "success" must not appear from thin air.
    if "success" not in source and "成功" in zh_text:
        flags.append("unsupported_success_concept")

    # Source-anchor preservation regressions.  These are intentionally narrow;
    # the agent's claim-unit ledger handles general semantics.
    if "obsessive" in source and not re.search(r"痴迷|着迷|入迷|近乎痴迷", zh_text):
        flags.append("dropped_obsessive_anchor")
    if "artisan" in source and not re.search(r"手艺|匠|工匠|创作者|专业者", zh_text):
        flags.append("dropped_artisan_anchor")
    if "ambivalent" in source and not re.search(
        r"犹豫|无所谓|不上不下|兴趣寥寥|态度暧昧|拿不准|没那么喜欢", zh_text
    ):
        flags.append("flattened_ambivalent_anchor")
    if "conscious effort" in source and not re.search(r"刻意|有意识|费劲|用力|逼自己", zh_text):
        flags.append("dropped_conscious_effort_anchor")
    if "maybe" in source and not re.search(r"也许|可能|或许", zh_text):
        flags.append("dropped_maybe_modality")
    if ("percent" in source or "%" in source) and not re.search(r"\d+\s*%|百分之\s*\d+", zh_text):
        flags.append("dropped_percentage")
    if "input" in source and "output" in source:
        has_left = bool(re.search(r"输入|投入|起点|前提", zh_text))
        has_right = bool(re.search(r"输出|产出|结果", zh_text))
        if not (has_left and has_right):
            flags.append("lost_input_output_contrast")
    return flags
