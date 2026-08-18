"""Immutable source evidence layer (V2 §六).

Builds source_map.json from the raw transcript: stable segment ids,
normalized text for matching, entity slots, caption-kind detection, and
span verification (contiguity rule: gaps ≤ MAX_SPAN_GAP_SEC between
adjacent spans; never stitch distant sentences into a fake quote).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .utils import normalize_text
from .transcript import Snippet, load_raw_snippets, load_meta, META_JSON

MAX_SPAN_GAP_SEC = 1.5          # adjacent spans farther apart = not contiguous
CONTEXT_SEC = 20.0              # ±20s of context around a quote


@dataclass
class SourceMap:
    video_id: str
    source_language: str
    caption_kind: str            # manual | auto | unknown
    segments: List[dict]
    entities: List[dict]
    warnings: List[str]

    def segment_by_id(self, segment_id: str) -> Optional[dict]:
        for seg in self.segments:
            if seg["segment_id"] == segment_id:
                return seg
        return None

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, ensure_ascii=False, indent=2)

    def to_dict(self) -> dict:
        return {
            "schema_version": "2.0",
            "video_id": self.video_id,
            "source_language": self.source_language,
            "caption_kind": self.caption_kind,
            "segments": self.segments,
            "entities": self.entities,
            "warnings": self.warnings,
        }


def detect_caption_kind(transcript_dir: str) -> str:
    meta_path = os.path.join(transcript_dir, META_JSON)
    if not os.path.exists(meta_path):
        return "unknown"
    with open(meta_path, encoding="utf-8") as fh:
        meta = json.load(fh)
    lang = meta.get("language") or {}
    return "auto" if lang.get("isGenerated") else "manual"


def build_source_map(transcript_dir: str) -> SourceMap:
    snippets = load_raw_snippets(transcript_dir)
    if not snippets:
        raise RuntimeError(
            f"no transcript-raw.json under {transcript_dir}. Next step: run "
            "bin/qcard fetch first.")
    meta = load_meta(transcript_dir)
    segments = []
    for i, sn in enumerate(snippets):
        segments.append({
            "segment_id": f"s{i:06d}",
            "start_sec": round(sn.start, 3),
            "end_sec": round(sn.end, 3),
            "raw_text": sn.text,
            "normalized_text": normalize_text(sn.text),
        })
    warnings: List[str] = []
    kind = detect_caption_kind(transcript_dir)
    if kind == "auto":
        warnings.append(
            "captions are auto-generated (ASR): proper nouns, numbers and "
            "rare words carry hallucination risk; suspicious quotes must go "
            "to review_queue with audio clips")
    # Timestamp anomalies.
    for a, b in zip(segments, segments[1:]):
        if b["start_sec"] < a["start_sec"] or a["end_sec"] < a["start_sec"]:
            warnings.append(f"timestamp anomaly near {b['segment_id']}")
    return SourceMap(
        video_id=meta.video_id,
        source_language=meta.language_code or "en",
        caption_kind=kind,
        segments=segments,
        entities=[],
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Span verification
# ---------------------------------------------------------------------------


def find_spans(source_map: SourceMap, exact_text: str
               ) -> Tuple[List[dict], Optional[str]]:
    """Locate exact_text as one or more contiguous spans.

    Returns (spans, error). A span covers consecutive segments whose joined
    normalized text contains the normalized needle. Multi-span quotes are
    accepted only when adjacent spans are ≤ MAX_SPAN_GAP_SEC apart
    (checked at pack-validation level via spans_are_contiguous).
    """
    needle = normalize_text(exact_text)
    if not needle:
        return [], "empty exact_source_text"
    segs = source_map.segments
    # Single segment.
    for seg in segs:
        if needle in seg["normalized_text"]:
            return [dict(segment_id=seg["segment_id"],
                         start_sec=seg["start_sec"],
                         end_sec=seg["end_sec"])], None
    # Consecutive-segment windows up to 12 long.
    for window in range(2, 13):
        for i in range(len(segs) - window + 1):
            chunk = segs[i:i + window]
            joined = "".join(c["normalized_text"] for c in chunk)
            if needle in joined:
                return [dict(segment_id=chunk[0]["segment_id"],
                             start_sec=chunk[0]["start_sec"],
                             end_sec=chunk[-1]["end_sec"],
                             segment_ids=[c["segment_id"] for c in chunk])], None
    return [], "exact_source_text NOT FOUND in contiguous transcript segments"


def spans_are_contiguous(source_map: SourceMap, spans: List[dict]
                         ) -> Tuple[bool, str]:
    """Ordered spans must not have big time gaps between them."""
    if len(spans) <= 1:
        return True, ""
    ordered = sorted(spans, key=lambda s: s["start_sec"])
    for a, b in zip(ordered, ordered[1:]):
        gap = b["start_sec"] - a["end_sec"]
        if gap > MAX_SPAN_GAP_SEC:
            return False, (f"span gap {gap:.2f}s between "
                           f"{a.get('segment_id')} and {b.get('segment_id')} "
                           f"exceeds {MAX_SPAN_GAP_SEC}s — stitching distant "
                           "sentences into one quote is forbidden")
    return True, ""


def context_around(source_map: SourceMap, start_sec: float, end_sec: float
                   ) -> Tuple[str, str]:
    """±CONTEXT_SEC of surrounding raw text (before, after)."""
    lo = start_sec - CONTEXT_SEC
    hi = end_sec + CONTEXT_SEC
    before: List[str] = []
    after: List[str] = []
    for seg in source_map.segments:
        if seg["end_sec"] <= start_sec and seg["end_sec"] >= lo:
            before.append(seg["raw_text"])
        elif seg["start_sec"] >= end_sec and seg["start_sec"] <= hi:
            after.append(seg["raw_text"])
    return " ".join(before), " ".join(after)


def display_en_diff(exact_text: str, display_en: str, edits: List[dict]
                    ) -> Tuple[List[str], bool]:
    """Audit display_en against exact text. Returns (violations, ok).

    Allowed edit operations are whitelisted; every semantic token that
    disappeared or changed must be attributable to an allowed operation.
    We verify conservatively: token multiset diff.
    """
    from collections import Counter
    import re as _re
    allowed_ops = {"capitalization", "punctuation", "remove_filler",
                   "remove_immediate_false_start",
                   "join_adjacent_caption_fragments"}

    def tokens(s: str) -> List[str]:
        return _re.findall(r"[a-zA-Z0-9']+", s.lower())

    src = Counter(tokens(exact_text))
    dsp = Counter(tokens(display_en))
    removed = src - dsp          # tokens present in source, missing in display
    added = dsp - src            # tokens in display not in source

    violations: List[str] = []
    for op in edits:
        if op.get("operation") not in allowed_ops:
            violations.append(f"edit operation {op.get('operation')!r} "
                              "not in whitelist")

    # Every added token must be explained by a recorded edit's `to` field
    # (or be a pure case/punct artifact — impossible for lowercase tokens).
    explained_add = Counter()
    for op in edits:
        for tok in tokens(str(op.get("to", ""))):
            explained_add[tok] += 1
    for tok, n in added.items():
        if explained_add.get(tok, 0) < n:
            violations.append(
                f"display_en adds unexplained token {tok!r} "
                f"(×{n}) — paraphrase/synonym replacement is forbidden")

    # Removed semantic tokens must be covered by an edit's `from` field.
    explained_rm = Counter()
    for op in edits:
        for tok in tokens(str(op.get("from", ""))):
            explained_rm[tok] += 1
    for tok, n in removed.items():
        if explained_rm.get(tok, 0) < n:
            violations.append(
                f"display_en drops unexplained token {tok!r} (×{n}) — "
                "deletions must be logged as remove_filler/false_start edits")

    return violations, not violations
