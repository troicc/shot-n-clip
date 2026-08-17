"""Shared helpers: safe subprocess, normalization, timestamps, fonts."""

from __future__ import annotations

import re
import shutil
import subprocess
import unicodedata
from typing import Iterable, List, Optional, Sequence

# ---------------------------------------------------------------------------
# Safe subprocess: always argument arrays, never an interpolated shell string.
# ---------------------------------------------------------------------------


def run_cmd(args: Sequence[str], timeout: int = 600) -> subprocess.CompletedProcess:
    """Run an external command with an argument array. No shell interpolation."""
    return subprocess.run(
        list(args),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def which(name: str) -> Optional[str]:
    return shutil.which(name)


# ---------------------------------------------------------------------------
# Text normalization (used by source_text verification).
# ---------------------------------------------------------------------------

_PUNCT_MAP = {
    "，": ",", "。": ".", "！": "!", "？": "?", "；": ";", "：": ":",
    "（": "(", "）": ")", "【": "[", "】": "]", "“": '"', "”": '"',
    "‘": "'", "’": "'", "—": "-", "–": "-", "～": "~", "　": " ",
    "&gt;": ">", "&lt;": "<", "&amp;": "&", "&quot;": '"', "&#39;": "'",
}


def normalize_text(text: str) -> str:
    """Aggressive but meaning-preserving normalization for substring matching.

    Lowercase, strip accents/diacritics from latin, fold CJK punctuation to
    ASCII, unify whitespace, drop non-word characters. Two renderings of the
    same spoken sentence (YouTube ASR vs. human-cleaned) should collide.
    """
    if not text:
        return ""
    for k, v in _PUNCT_MAP.items():
        text = text.replace(k, v)
    text = unicodedata.normalize("NFKC", text)
    # Strip combining marks left over after NFKC (é -> e, etc.)
    text = "".join(ch for ch in unicodedata.normalize("NFD", text)
                   if unicodedata.category(ch) != "Mn")
    text = text.lower()
    # Remove everything that is not a letter/digit/CJK char.
    text = re.sub(r"[^\w一-鿿぀-ヿ가-힯]+", "", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Timestamps.
# ---------------------------------------------------------------------------


def fmt_ts(seconds: float, with_ms: bool = False) -> str:
    """Seconds -> HH:MM:SS(.mmm)."""
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds - h * 3600 - m * 60
    if with_ms:
        return f"{h:02d}:{m:02d}:{int(s):02d}.{int(round((s - int(s)) * 1000)):03d}"
    return f"{h:02d}:{m:02d}:{int(s):02d}"


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


# ---------------------------------------------------------------------------
# Font discovery. Never copy or ship font files; find what the OS provides.
# ---------------------------------------------------------------------------

_MAC_CJK = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/System/Library/Fonts/Supplemental/STHeiti Light.ttc",
]
_LINUX_CJK = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/wenquanyi/wqy-microhei/wqy-microhei.ttc",
    "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc",
]

_MAC_LATIN = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/SFNS.ttf",  # renders latin fine at small sizes
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Helvetica.ttf",
]
_LINUX_LATIN = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
]

import sys  # noqa: E402  (kept local to the font section on purpose)


def _first_existing(paths: Iterable[str]) -> Optional[str]:
    for p in paths:
        if p and os_path_exists(p):
            return p
    return None


def os_path_exists(path: str) -> bool:
    import os
    return os.path.exists(path)


def find_cjk_font(tried: Optional[List[str]] = None) -> Optional[str]:
    candidates = _MAC_CJK if sys.platform == "darwin" else _LINUX_CJK
    found = _first_existing(candidates)
    if tried is not None:
        tried.extend(candidates)
    return found


def find_latin_font(tried: Optional[List[str]] = None) -> Optional[str]:
    candidates = _MAC_LATIN if sys.platform == "darwin" else _LINUX_LATIN
    found = _first_existing(candidates)
    if tried is not None:
        tried.extend(candidates)
    return found
