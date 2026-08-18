"""Stage-scoped context material (V2 §十六: never ship the full transcript
to every agent). Each stage gets only what it needs, keyed by segment ids."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .source_integrity import SourceMap, context_around, find_spans

STAGE_STATUS = "_stage_status.json"

# Known proper-noun bait in ASR captions (extend per language).
_SUSPICIOUS_TOKENS = ["Magnus", "Seinfeld", "Gurley", "McConaughey", "Wharton",
                      "Gallup", "Zagat", "Gramercy", "Madison", "Shack"]
_NUMBERISH = "0123456789"


@dataclass
class StageStatus:
    """Cheap resume support: each finished stage is recorded once."""
    work_dir: str
    data: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, work_dir: str) -> "StageStatus":
        path = os.path.join(work_dir, STAGE_STATUS)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                return cls(work_dir=work_dir, data=json.load(fh))
        return cls(work_dir=work_dir)

    def done(self, stage: str) -> bool:
        return self.data.get(stage) == "done"

    def mark(self, stage: str) -> None:
        self.data[stage] = "done"
        self._flush()

    def _flush(self) -> None:
        with open(os.path.join(self.work_dir, STAGE_STATUS), "w",
                  encoding="utf-8") as fh:
            json.dump(self.data, fh, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Stage contexts
# ---------------------------------------------------------------------------


def index_for_angles(source_map: SourceMap, chunk_chars: int = 60_000
                     ) -> List[Dict]:
    """Chunked transcript digest for the angle stage only.

    Each chunk: {index, segment_range, time_range, text}. angle-pack-editor
    reads all chunks (it must see the whole video) but nothing else does.
    """
    chunks = []
    buf: List[dict] = []
    size = 0
    for seg in source_map.segments:
        buf.append(seg)
        size += len(seg["raw_text"])
        if size >= chunk_chars:
            chunks.append(_chunk_obj(buf))
            buf, size = [], 0
    if buf:
        chunks.append(_chunk_obj(buf))
    return chunks


def _chunk_obj(buf: List[dict]) -> Dict:
    return {
        "segment_range": [buf[0]["segment_id"], buf[-1]["segment_id"]],
        "time_range": [buf[0]["start_sec"], buf[-1]["end_sec"]],
        "text": "\n".join(f"[{s['segment_id']} {s['start_sec']:.1f}] {s['raw_text']}"
                          for s in buf),
    }


def evidence_pack_for_quote(source_map: SourceMap, exact_text: str
                            ) -> Optional[Dict]:
    """Everything zh-editor / fidelity-reviewer need for ONE quote:
    spans, exact text, ±20s context, plus suspicion flags."""
    spans, err = find_spans(source_map, exact_text)
    if err:
        return {"error": err}
    start = min(s["start_sec"] for s in spans)
    end = max(s["end_sec"] for s in spans)
    before, after = context_around(source_map, start, end)
    ok, gap_err = (True, "")
    from .source_integrity import spans_are_contiguous
    ok, gap_err = spans_are_contiguous(source_map, spans)
    return {
        "exact_source_text": exact_text,
        "source_spans": spans,
        "context_before": before,
        "context_after": after,
        "caption_kind": source_map.caption_kind,
        "suspected_asr_issues": _suspicions(exact_text),
        "spans_contiguous": ok,
        "gap_error": gap_err,
    }


def _suspicions(text: str) -> List[str]:
    flags = []
    for tok in _SUSPICIOUS_TOKENS:
        if tok.lower() in text.lower():
            flags.append(f"proper noun '{tok}' — verify spelling via entity glossary")
    if any(ch in _NUMBERISH for ch in text):
        flags.append("contains digits — verify against audio before publish")
    return flags


def needs_audio_check(evidence: Dict, auto_captions: bool) -> bool:
    if not auto_captions:
        return False
    return bool(evidence.get("suspected_asr_issues")) or not evidence.get(
        "spans_contiguous", True)
