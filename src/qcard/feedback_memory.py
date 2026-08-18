"""Approve/reject style memory (V2 §十三): growing jsonl corpora consumed
as style/error-pattern reference at the start of each Skill run."""

from __future__ import annotations

import json
import os
import time
from typing import Dict, List, Optional

REJECT_REASON_TAGS = [
    "literal_translation", "ai_cliche", "overstated", "entity_error",
    "unnatural_wording", "too_long", "weak_angle", "generic_copy",
]

_APPROVED = "approved_examples.jsonl"
_REJECTED = "rejected_examples.jsonl"


def _append(path: str, record: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def approve(config_root: str, pack: dict, copy: Optional[dict] = None) -> str:
    """Append the user-approved pack (quotes + titles) to approved jsonl."""
    record = {
        "kind": "approved",
        "approved_at": time.strftime("%Y-%m-%d"),
        "video_id": pack.get("video_id", ""),
        "pack_id": pack["pack"]["pack_id"],
        "core_claim": pack["pack"]["core_claim"],
        "quotes": [
            {
                "exact_source_text": q["exact_source_text"],
                "display_en": q["display_en"],
                "recommended_zh": q["recommended_zh"],
                "compact_zh": q["compact_zh"],
            }
            for q in pack["quotes"]
        ],
        "title": (copy or {}).get("recommended_title"),
        "intro": (copy or {}).get("intro_full"),
    }
    path = os.path.join(config_root, "editorial", _APPROVED)
    _append(path, record)
    return path


def reject(config_root: str, pack: dict, reason: str,
           note: str = "") -> str:
    if reason not in REJECT_REASON_TAGS:
        raise ValueError(f"unknown reject reason {reason!r}; valid: "
                         f"{REJECT_REASON_TAGS}")
    record = {
        "kind": "rejected",
        "rejected_at": time.strftime("%Y-%m-%d"),
        "video_id": pack.get("video_id", ""),
        "pack_id": pack["pack"]["pack_id"],
        "reason": reason,
        "note": note,
        "quotes": [
            {"exact_source_text": q["exact_source_text"],
             "recommended_zh": q["recommended_zh"]}
            for q in pack["quotes"]
        ],
    }
    path = os.path.join(config_root, "editorial", _REJECTED)
    _append(path, record)
    return path


def recent(config_root: str, kind: str, n: int) -> List[dict]:
    name = _APPROVED if kind == "approved" else _REJECTED
    path = os.path.join(config_root, "editorial", name)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().splitlines() if ln.strip()]
    out = []
    for ln in lines[-n:]:
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out


def style_brief(config_root: str, approved_n: int = 20,
                rejected_n: int = 10) -> str:
    """Compact brief injected at the start of each Skill run: patterns only,
    never verbatim reuse, never cross-video facts."""
    approved = recent(config_root, "approved", approved_n)
    rejected = recent(config_root, "rejected", rejected_n)
    parts = ["风格参考（仅取模式，不逐字复用，不迁移旧事实）："]
    if approved:
        parts.append(f"- 最近 {len(approved)} 组已批准样本。")
        zh_samples = [q["recommended_zh"] for a in approved
                      for q in a.get("quotes", [])][-8:]
        parts.append("- 已批准中文示例节奏（供语气对齐）：\n  " +
                     "\n  ".join(f"· {s}" for s in zh_samples))
    else:
        parts.append("- 暂无已批准样本：按 voice.zh-CN.yaml 默认风格。")
    if rejected:
        from collections import Counter
        reasons = Counter(r["reason"] for r in rejected)
        parts.append("- 历史拒绝原因分布：" +
                     ", ".join(f"{k}×{v}" for k, v in reasons.most_common()))
        bad = [q["recommended_zh"] for r in rejected
               for q in r.get("quotes", [])][-5:]
        if bad:
            parts.append("- 被拒绝示例（避免同类）：\n  " +
                         "\n  ".join(f"· {s}" for s in bad))
    return "\n".join(parts)
