"""Deterministic editorial-density, locality, and theme checks.

These rules are intentionally conservative for a bilingual 3:4 card.  They do
not decide whether an idea is interesting; they prevent paragraph-sized source
spans, topic-collage packs, and visually unreadable translations from being
labelled ready.
"""
from __future__ import annotations

import math
import re
import unicodedata
from typing import Iterable, List, Sequence

MAX_SOURCE_CHARS = 180
MAX_SOURCE_WORDS = 28
MAX_SOURCE_SENTENCES = 2
MAX_PACK_SPAN_SEC = 360.0
MAX_ADJACENT_GAP_SEC = 120.0
MAX_ZH_VISUAL_UNITS = 38.0
WARN_ZH_VISUAL_UNITS = 32.0
MAX_COMPACT_ZH_VISUAL_UNITS = 32.0

# Too broad to prove a coherent theme.  Terms such as "learning", "career",
# "fascination", "AI", "craft", or a proper name are acceptable.
_GENERIC_ANCHORS = {
    "people", "person", "thing", "things", "life", "world", "good", "bad",
    "better", "success", "change", "idea", "ideas", "something", "someone",
    "everyone", "everything", "today", "really", "important", "problem",
}

_SENTENCE_END = re.compile(r"[.!?。！？]+(?=\s|$)")
_EN_WORD = re.compile(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*")
_CJK = re.compile(r"[\u3400-\u9fff]")
_LATIN_RUN = re.compile(r"[A-Za-z0-9]+(?:[._/+%-][A-Za-z0-9]+)*")


def english_word_count(text: str) -> int:
    return len(_EN_WORD.findall(text or ""))


def sentence_count(text: str) -> int:
    stripped = (text or "").strip()
    if not stripped:
        return 0
    count = len(_SENTENCE_END.findall(stripped))
    return max(1, count)


def source_density_flags(text: str) -> List[str]:
    """Return deterministic reasons a source span is too dense for one strip."""
    value = (text or "").strip()
    flags: List[str] = []
    if len(value) > MAX_SOURCE_CHARS:
        flags.append("source_too_many_characters")
    if english_word_count(value) > MAX_SOURCE_WORDS:
        flags.append("source_too_many_words")
    sentence_total = sentence_count(value)
    if sentence_total > MAX_SOURCE_SENTENCES:
        flags.append("multi_sentence_paragraph")

    # A terse thesis followed by a long anecdote is usually two card units.
    # The real failed output combined “Passion doesn't invoke work.” with the
    # Cincinnati Reds / 3.5-hour beer example, producing a subtitle paragraph.
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", value) if part.strip()]
    if len(sentences) == 2:
        first_words = english_word_count(sentences[0])
        total_words = english_word_count(value)
        if first_words <= 9 and total_words > 18:
            flags.append("thesis_plus_example_overload")

    numeric_facts = re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?%?", value)
    if len(numeric_facts) >= 3:
        flags.append("too_many_numeric_facts")
    return flags


def _ascii_fold(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    return value.lower()


def _stem(value: str) -> str:
    word = re.sub(r"[^a-z0-9]+", "", _ascii_fold(value))
    for suffix in ("ations", "ation", "ments", "ment", "ingly", "edly", "ing", "ers", "er", "ed", "es", "s"):
        if len(word) - len(suffix) >= 5 and word.endswith(suffix):
            word = word[: -len(suffix)]
            break
    return word


def normalize_anchor(term: str) -> str:
    value = " ".join(_ascii_fold(term).split())
    return value.strip(" ,.;:!?\"'()[]{}")


def valid_anchor_term(term: str) -> bool:
    norm = normalize_anchor(term)
    if not norm or len(norm) < 2:
        return False
    if norm in _GENERIC_ANCHORS:
        return False
    return bool(re.search(r"[a-z0-9\u3400-\u9fff]", norm))


def anchor_matches(term: str, text: str) -> bool:
    """Loose source-side match that handles fascination/fascinated, learn/learning."""
    term_norm = normalize_anchor(term)
    text_fold = _ascii_fold(text)
    if not term_norm:
        return False
    if " " in term_norm:
        return term_norm in " ".join(text_fold.split())
    stem = _stem(term_norm)
    if not stem:
        return False
    words = [_stem(w) for w in _EN_WORD.findall(text_fold)]
    if any(w == stem or (len(stem) >= 5 and (w.startswith(stem) or stem.startswith(w))) for w in words):
        return True
    # CJK or mixed-script anchors: normalized substring.
    compact_term = re.sub(r"\s+", "", term_norm)
    compact_text = re.sub(r"\s+", "", text_fold)
    return bool(compact_term and compact_term in compact_text)


def matched_anchors(anchor_terms: Sequence[str], *texts: str) -> List[str]:
    haystack = " ".join(texts)
    return [term for term in anchor_terms if anchor_matches(term, haystack)]


def zh_visual_units(text: str) -> float:
    """Approximate horizontal typographic load across two Chinese lines.

    Han/Kana/Hangul count as one full unit, latin runs and numbers as roughly
    half-width, punctuation as a small fraction.  This is not a font metric;
    it is a fast content gate before rendering with real font metrics.
    """
    value = unicodedata.normalize("NFKC", text or "")
    units = 0.0
    consumed = [False] * len(value)
    for match in _LATIN_RUN.finditer(value):
        run = match.group(0)
        units += max(1.0, len(run) * 0.55)
        for i in range(match.start(), match.end()):
            consumed[i] = True
    for index, ch in enumerate(value):
        if consumed[index] or ch.isspace():
            continue
        if _CJK.match(ch) or 0x3040 <= ord(ch) <= 0x30FF or 0xAC00 <= ord(ch) <= 0xD7AF:
            units += 1.0
        elif unicodedata.category(ch).startswith("P"):
            units += 0.35
        else:
            units += 0.65
    return round(units, 2)


def ordered_times(candidates: Sequence[dict]) -> List[float]:
    result: List[float] = []
    for candidate in candidates:
        start = candidate.get("start_sec")
        end = candidate.get("end_sec")
        if isinstance(start, (int, float)) and isinstance(end, (int, float)):
            result.append((float(start) + float(end)) / 2.0)
    return result


def locality_flags(candidates: Sequence[dict]) -> List[str]:
    """Check source-order continuity inspired by native subtitle collages."""
    centres = ordered_times(candidates)
    if len(centres) != len(candidates) or len(centres) < 2:
        return []
    flags: List[str] = []
    if any(right <= left for left, right in zip(centres, centres[1:])):
        flags.append("quotes_not_in_source_order")
        return flags
    if centres[-1] - centres[0] > MAX_PACK_SPAN_SEC:
        flags.append("pack_source_span_too_wide")
    if any(right - left > MAX_ADJACENT_GAP_SEC for left, right in zip(centres, centres[1:])):
        flags.append("adjacent_quote_gap_too_wide")
    return flags
