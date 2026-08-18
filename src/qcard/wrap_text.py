"""Bilingual word-wrap with real font metrics, word-boundary and widow guards.

Rules enforced here (V2 §十四):
- CJK breaks anywhere legal; latin NEVER breaks inside a word — only at
  spaces / after hyphens.
- Widow/orphan guard: last line must not be a single very short word
  (en) or 1-2 CJK chars (zh).
- Widths are measured with the actual font, not estimated by char count.
- Escaped-quote residue (&#39;, \\u0027, doubled smart quotes) cleaned
  before wrapping.
"""

from __future__ import annotations

import re
import unicodedata
from typing import List, Optional, Sequence, Tuple

from PIL import ImageFont

_ESCAPE_RESIDUE = [
    (re.compile(r"&#39;|&#x27;"), "'"),
    (re.compile(r"&quot;|&#34;"), '"'),
    (re.compile(r"&amp;"), "&"),
    (re.compile(r"“”|”“"), '"'),  # empty quote pairs glued
]


def clean_escapes(text: str) -> str:
    for pattern, repl in _ESCAPE_RESIDUE:
        text = pattern.sub(repl, text)
    return text


def is_cjk(ch: str) -> bool:
    code = ord(ch)
    return (0x4E00 <= code <= 0x9FFF or 0x3400 <= code <= 0x4DBF or
            0x3040 <= code <= 0x30FF or 0xAC00 <= code <= 0xD7AF or
            0xF900 <= code <= 0xFAFF)


def _has_cjk(text: str) -> bool:
    return any(is_cjk(ch) for ch in text)


# ---------------------------------------------------------------------------
# Tokenization: a latin "word" (with trailing/leading spaces resolved at
# join time) is atomic; a CJK char is atomic; punctuation glues to neighbors.
# ---------------------------------------------------------------------------


def tokenize(text: str) -> List[str]:
    tokens: List[str] = []
    buf = ""
    for ch in text:
        if is_cjk(ch):
            if buf:
                tokens.append(buf)
                buf = ""
            tokens.append(ch)
        elif ch.isspace():
            if buf:
                tokens.append(buf)
                buf = ""
            tokens.append(ch)
        else:
            buf += ch
    if buf:
        tokens.append(buf)
    return tokens


_BREAKABLE_AFTER = re.compile(r"[-/]$")


def _width(font: ImageFont.FreeTypeFont, text: str) -> int:
    return font.getbbox(text)[2] if text else 0


def wrap(text: str, font: ImageFont.FreeTypeFont, max_w: int,
         kind: str = "auto", min_last_en_chars: int = 4,
         min_last_zh_chars: int = 3) -> List[str]:
    """Wrap text within max_w using real font metrics.

    kind: 'en' | 'zh' | 'auto' (per-token detection).
    Returns lines; caller checks len(lines) <= max_lines.
    """
    text = clean_escapes(text).strip()
    if not text:
        return []
    tokens = tokenize(text)
    lines: List[str] = []
    cur = ""
    cur_w = 0

    def commit() -> None:
        nonlocal cur, cur_w
        if cur.strip():
            lines.append(cur.strip())
        cur, cur_w = "", 0

    for tok in tokens:
        tok_w = _width(font, tok)
        if not cur:
            cur, cur_w = tok, tok_w
        elif cur_w + tok_w <= max_w:
            cur += tok
            cur_w += tok_w
        else:
            # Need to break. Latin words never split mid-word: if the token
            # itself is wider than max_w we must still keep it whole (caller
            # treats overlong single tokens as overflow).
            if tok.isspace():
                commit()
                continue
            if _BREAKABLE_AFTER.search(tok) and not _has_cjk(tok):
                # Break after hyphen/slash is legal: emit current + hyphen part.
                cur += tok
                commit()
                continue
            commit()
            cur, cur_w = tok, tok_w
    commit()

    # Widow/orphan guard: rebalance if the last line is starved.
    lines = _fix_widow(lines, font, max_w, kind, min_last_en_chars,
                       min_last_zh_chars)
    return lines


def _fix_widow(lines: List[str], font: ImageFont.FreeTypeFont, max_w: int,
               kind: str, min_en: int, min_zh: int) -> List[str]:
    if len(lines) < 2:
        return lines
    last = lines[-1]
    prev = lines[-2]
    stripped = last.strip()
    latin_words = [w for w in stripped.split() if w]
    is_latinish = not _has_cjk(stripped) and bool(latin_words)
    if is_latinish:
        if len(latin_words) == 1 and len(stripped) < min_en:
            return _pull_last_word_down_or_up(lines, font, max_w)
    else:
        cjk_len = len([c for c in stripped if is_cjk(c)])
        if 0 < cjk_len < min_zh:
            return _pull_last_word_down_or_up(lines, font, max_w)
    if _width(font, prev) < max_w * 0.25 and _width(font, last) > max_w * 0.75:
        return _pull_last_word_down_or_up(lines, font, max_w)
    return lines


def _pull_last_word_down_or_up(lines: List[str], font: ImageFont.FreeTypeFont,
                               max_w: int) -> List[str]:
    """Rebalance the last two lines so neither is starved.

    Strategy: move the first token(s) of the last line up if they fit, else
    move the last token of the previous line down.
    """
    if len(lines) < 2:
        return lines
    last, prev = lines[-1], lines[-2]
    toks = tokenize(last)
    first_tok = next((t for t in toks if not t.isspace()), "")
    if first_tok:
        candidate = prev + (" " if not prev.endswith(" ") and not _has_cjk(first_tok) and not _has_cjk(prev) else "") + first_tok
        if _width(font, candidate) <= max_w:
            new_last = last.replace(first_tok, "", 1).strip()
            if new_last:
                return lines[:-2] + [candidate.strip(), new_last]
            return lines[:-2] + [candidate.strip()]
    # Otherwise pull prev's tail down.
    prev_toks = tokenize(prev)
    tail = ""
    while prev_toks:
        tail = prev_toks.pop() + tail
        if not tail.strip():
            continue
        new_prev = "".join(prev_toks).strip()
        new_last = tail.strip() + " " + last if _has_cjk(tail) or _has_cjk(last) is False else tail.strip() + last
        joined = tail.strip() + (" " if not _has_cjk(tail.strip()) else "") + last
        if _width(font, joined) <= max_w and _width(font, new_prev) > max_w * 0.25:
            return lines[:-2] + [new_prev, joined.strip()]
        if not tail:
            break
    return lines


def layout(text: str, font_path: str, sizes: Sequence[int], max_w: int,
           max_lines: int, spacing: float
           ) -> Tuple[Optional[ImageFont.FreeTypeFont], List[str], int, int]:
    """Try each size (high→low); return (font, lines, line_height, block_h).

    Returns (None, [], 0, 0) when no size in `sizes` fits max_lines —
    caller decides fallback (compact variant / different quote), never
    unlimited shrinking.
    """
    for size in sizes:
        font = ImageFont.truetype(font_path, size)
        lines = wrap(text, font, max_w)
        if len(lines) <= max_lines and all(_width(font, ln) <= max_w for ln in lines):
            line_h = int(size * spacing)
            return font, lines, line_h, line_h * len(lines)
    return None, [], 0, 0
