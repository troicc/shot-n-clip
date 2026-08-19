"""High-clarity editorial renderer for Chinese/English quote cards.

The layout borrows the useful production constraints of native-subtitle
collages—3:4 high-resolution output, five nearby source moments, lower subtitle
placement, and 4:4:4 JPEG export—while continuing to render source-grounded
Chinese/English text deterministically.
"""
from __future__ import annotations

import json
import math
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import yaml
from PIL import Image, ImageDraw, ImageFont


class EditorialOverflowError(Exception):
    pass


@dataclass(frozen=True)
class FontFace:
    path: str
    index: int = 0
    name: str = ""


@dataclass
class EditorialStyle:
    canvas: Tuple[int, int] = (1440, 1920)
    corner_radius: int = 64
    strip_gap: int = 6
    gap_color: Tuple[int, int, int] = (8, 8, 10)
    max_width_ratio: float = 0.86
    crop_center_y: float = 0.38
    gradient_alpha: int = 220
    gradient_extra_px: int = 34
    zh_font_range: Tuple[int, int] = (72, 60)
    en_font_range: Tuple[int, int] = (46, 36)
    inline_zh_font_range: Tuple[int, int] = (62, 50)
    inline_en_font_range: Tuple[int, int] = (38, 30)
    zh_line_spacing: float = 1.16
    en_line_spacing: float = 1.16
    block_gap_px: int = 12
    bottom_padding_px: int = 22
    zh_stroke_width: int = 2
    en_stroke_width: int = 1
    jpg_quality: int = 96
    inline_default_count: int = 5


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_editorial_style(name: str = "editorial") -> EditorialStyle:
    style = EditorialStyle()
    path = _project_root() / "config" / "styles" / f"{name}.yaml"
    if not path.exists():
        return style
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if isinstance(raw.get("canvas"), list) and len(raw["canvas"]) == 2:
        style.canvas = (int(raw["canvas"][0]), int(raw["canvas"][1]))
    scalar_fields = (
        "corner_radius", "strip_gap", "gradient_alpha", "gradient_extra_px",
        "block_gap_px", "bottom_padding_px", "zh_stroke_width",
        "en_stroke_width", "jpg_quality", "inline_default_count",
    )
    for key in scalar_fields:
        if key in raw:
            setattr(style, key, int(raw[key]))
    float_fields = ("max_width_ratio", "crop_center_y", "zh_line_spacing", "en_line_spacing")
    for key in float_fields:
        if key in raw:
            setattr(style, key, float(raw[key]))
    tuple_fields = (
        "zh_font_range", "en_font_range", "inline_zh_font_range",
        "inline_en_font_range", "gap_color",
    )
    for key in tuple_fields:
        value = raw.get(key)
        if isinstance(value, list) and len(value) in (2, 3):
            setattr(style, key, tuple(int(x) for x in value))
    return style


_CJK_PATHS = (
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
)
_LATIN_PATHS = (
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/SFNS.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)


def _face_score(family: str, style: str, kind: str) -> int:
    text = f"{family} {style}".lower()
    score = 0
    if kind == "cjk":
        if any(name in text for name in ("pingfang sc", "noto sans cjk", "hiragino sans gb")):
            score += 20
        if any(weight in text for weight in ("semibold", "medium", "demibold", "bold")):
            score += 12
        if "light" in text or "thin" in text:
            score -= 20
    else:
        if any(name in text for name in ("helvetica", "sf pro", "arial", "dejavu sans")):
            score += 20
        if any(weight in text for weight in ("medium", "regular", "book")):
            score += 8
        if "light" in text or "thin" in text:
            score -= 15
    return score


def _best_face(paths: Iterable[str], kind: str) -> FontFace:
    best: Optional[Tuple[int, FontFace]] = None
    tried: List[str] = []
    for path in paths:
        if not os.path.exists(path):
            tried.append(path)
            continue
        # TTC collections may expose several weights.  Scan safely rather than
        # assuming a platform-specific index for PingFang/Helvetica.
        found_any = False
        for index in range(16):
            try:
                font = ImageFont.truetype(path, 24, index=index)
                family, style = font.getname()
                found_any = True
            except OSError:
                if found_any:
                    break
                continue
            face = FontFace(path=path, index=index, name=f"{family} {style}".strip())
            score = _face_score(family, style, kind)
            if best is None or score > best[0]:
                best = (score, face)
        if best and best[0] >= 30:
            break
    if best is None:
        raise RuntimeError(f"No usable {kind} font found. Tried: {', '.join(tried)}")
    return best[1]


def resolve_editorial_fonts() -> Tuple[FontFace, FontFace]:
    return _best_face(_CJK_PATHS, "cjk"), _best_face(_LATIN_PATHS, "latin")


def _font(face: FontFace, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(face.path, size, index=face.index)


def normalize_zh_typography(text: str) -> str:
    value = unicodedata.normalize("NFKC", text or "")
    value = value.replace("\u00a0", " ")
    value = re.sub(r"[ \t\r\n]+", " ", value).strip()
    value = re.sub(r"\s+([，。！？；：、）》」』】])", r"\1", value)
    value = re.sub(r"([（《「『【])\s+", r"\1", value)
    value = re.sub(r"([\u3400-\u9fff])\s+([\u3400-\u9fff])", r"\1\2", value)
    value = re.sub(
        r"(?<=\d)\s+(?=(?:年|月|日|岁|小时|分钟|秒|%|％|元|美元|人|个|次))",
        "",
        value,
    )
    value = re.sub(r"(?<=[%％])\s+(?=[\u3400-\u9fff])", "", value)
    value = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=\d)", "", value)
    value = re.sub(r"(?<=\d)\s+(?=[\u3400-\u9fff])", "", value)
    value = re.sub(r"([，。！？；：])\s+(?=[\u3400-\u9fff])", r"\1", value)
    value = re.sub(r"(?<=[\u3400-\u9fff%％”])\s*,\s*", "，", value)
    value = re.sub(r"(?<=[\u3400-\u9fff%％”])\s*:\s*", "：", value)
    value = re.sub(r"(?<=[\u3400-\u9fff%％”])\s*;\s*", "；", value)
    value = re.sub(r"\s+([,.;:!?])", r"\1", value)
    value = re.sub(r"([“‘])\s+", r"\1", value)
    value = re.sub(r"\s+([”’])", r"\1", value)
    # Convert paired ASCII quotes without touching apostrophes inside latin words.
    if value.count('"') >= 2:
        opening = True
        converted = []
        for ch in value:
            if ch == '"':
                converted.append('“' if opening else '”')
                opening = not opening
            else:
                converted.append(ch)
        value = ''.join(converted)
    value = re.sub(r"([“‘])\s+", r"\1", value)
    value = re.sub(r"\s+([”’])", r"\1", value)
    return value


def _is_cjk(ch: str) -> bool:
    code = ord(ch)
    return (0x3400 <= code <= 0x9FFF or 0x3040 <= code <= 0x30FF or
            0xAC00 <= code <= 0xD7AF or 0xF900 <= code <= 0xFAFF)


def _tokens(text: str) -> List[str]:
    tokens: List[str] = []
    buf = ""
    for ch in text:
        if _is_cjk(ch):
            if buf:
                tokens.append(buf)
                buf = ""
            tokens.append(ch)
        elif ch.isspace():
            if buf:
                tokens.append(buf)
                buf = ""
            tokens.append(" ")
        else:
            buf += ch
    if buf:
        tokens.append(buf)
    return tokens


def _width(font: ImageFont.FreeTypeFont, text: str) -> int:
    if not text:
        return 0
    box = font.getbbox(text)
    return box[2] - box[0]


def _join_token(cur: str, token: str) -> str:
    if token == " ":
        return cur if not cur or cur.endswith(" ") else cur + " "
    return cur + token


_CLOSING = set("，。！？；：、）》」』】,.!?;:%")
_OPENING = set("（《「『【(")


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int,
              kind: str) -> List[str]:
    value = normalize_zh_typography(text) if kind == "zh" else " ".join((text or "").split())
    lines: List[str] = []
    current = ""
    for token in _tokens(value):
        candidate = _join_token(current, token)
        if not current or _width(font, candidate.rstrip()) <= max_width:
            current = candidate
            continue
        if current.strip():
            lines.append(current.strip())
        current = "" if token == " " else token
    if current.strip():
        lines.append(current.strip())

    # Keep closing punctuation off the beginning of a line and opening marks
    # off the end where a one-character rebalance is possible.
    for i in range(1, len(lines)):
        if lines[i] and lines[i][0] in _CLOSING:
            punct = lines[i][0]
            candidate = lines[i - 1] + punct
            if _width(font, candidate) <= max_width:
                lines[i - 1] = candidate
                lines[i] = lines[i][1:].lstrip()
        if lines[i - 1] and lines[i - 1][-1] in _OPENING:
            mark = lines[i - 1][-1]
            lines[i - 1] = lines[i - 1][:-1].rstrip()
            lines[i] = mark + lines[i]

    lines = [line for line in lines if line]
    if len(lines) >= 2:
        last = lines[-1]
        if kind == "en" and len(last.split()) == 1 and len(last) <= 5:
            prev_words = lines[-2].split()
            if len(prev_words) > 1:
                moved = prev_words[-1]
                candidate = f"{moved} {last}"
                new_prev = " ".join(prev_words[:-1])
                if _width(font, candidate) <= max_width and new_prev:
                    lines[-2], lines[-1] = new_prev, candidate
        if kind == "zh" and sum(1 for ch in last if _is_cjk(ch)) <= 2:
            prev = lines[-2]
            if len(prev) > 2:
                moved = prev[-1]
                candidate = moved + last
                new_prev = prev[:-1]
                if _width(font, candidate) <= max_width:
                    lines[-2], lines[-1] = new_prev, candidate
    return lines


def fit_text(primary: str, fallback: str, face: FontFace,
             size_range: Tuple[int, int], max_width: int, kind: str,
             line_spacing: float, max_lines: int = 2
             ) -> Tuple[str, ImageFont.FreeTypeFont, List[str], int, int, bool]:
    for text, used_fallback in ((primary, False), (fallback, True)):
        if not text:
            continue
        for size in range(size_range[0], size_range[1] - 1, -1):
            font = _font(face, size)
            lines = wrap_text(text, font, max_width, kind)
            if 0 < len(lines) <= max_lines and all(_width(font, line) <= max_width for line in lines):
                line_h = round(size * line_spacing)
                return text, font, lines, line_h, line_h * len(lines), used_fallback
    raise EditorialOverflowError(
        f"{kind} text cannot fit in {max_lines} lines at the readability floor; "
        "replace the source quote instead of shrinking the font"
    )


def cover_crop(image: Image.Image, width: int, height: int, center_y: float) -> Image.Image:
    sw, sh = image.size
    scale = max(width / sw, height / sh)
    nw, nh = max(1, math.ceil(sw * scale)), max(1, math.ceil(sh * scale))
    resized = image.resize((nw, nh), Image.Resampling.LANCZOS)
    left = max(0, (nw - width) // 2)
    available_y = max(0, nh - height)
    top = max(0, min(available_y, round(available_y * center_y)))
    return resized.crop((left, top, left + width, top + height))


def _gradient(width: int, height: int, max_alpha: int) -> Image.Image:
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    start = max(0, round(height * 0.18))
    denom = max(1, height - start - 1)
    for y in range(start, height):
        t = (y - start) / denom
        alpha = round(max_alpha * (t ** 0.72))
        draw.line((0, y, width, y), fill=(0, 0, 0, alpha))
    return overlay


def compose_strip(frame: Image.Image, zh_info, en_info,
                  style: EditorialStyle) -> Tuple[Image.Image, dict]:
    width, height = frame.size
    parts = [part for part in (zh_info, en_info) if part is not None]
    text_h = sum(part[4] for part in parts)
    gap = style.block_gap_px if len(parts) == 2 else 0
    gradient_h = min(height, text_h + gap + style.bottom_padding_px * 2 + style.gradient_extra_px)

    strip = frame.convert("RGBA")
    gradient = _gradient(width, gradient_h, style.gradient_alpha)
    strip.alpha_composite(gradient, (0, height - gradient_h))
    draw = ImageDraw.Draw(strip)
    y = height - style.bottom_padding_px - text_h - gap
    detail: dict = {"gradient_height": gradient_h}
    for index, info in enumerate(parts):
        text, font, lines, line_h, block_h, used_fallback = info
        kind = "zh" if info is zh_info else "en"
        fill = (255, 255, 255, 255) if kind == "zh" else (238, 238, 238, 255)
        stroke_width = style.zh_stroke_width if kind == "zh" else style.en_stroke_width
        for line in lines:
            x = (width - _width(font, line)) // 2
            draw.text(
                (x, y), line, font=font, fill=fill,
                stroke_width=stroke_width, stroke_fill=(0, 0, 0, 235),
            )
            y += line_h
        detail[kind] = {
            "font": getattr(font, "path", ""),
            "font_size": font.size,
            "lines": lines,
            "text": text,
            "used_fallback": used_fallback,
        }
        if index == 0 and len(parts) == 2:
            y += gap
    return strip.convert("RGB"), detail


def _rounded(image: Image.Image, radius: int, background: Tuple[int, int, int]) -> Image.Image:
    mask = Image.new("L", image.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, image.width - 1, image.height - 1), radius=radius, fill=255)
    result = Image.new("RGB", image.size, background)
    result.paste(image, (0, 0), mask)
    return result


def _save(image: Image.Image, output_dir: Path, stem: str,
          style: EditorialStyle) -> Dict[str, str]:
    png = output_dir / f"{stem}.png"
    jpg = output_dir / f"{stem}.jpg"
    image.save(png, optimize=True)
    image.save(jpg, quality=style.jpg_quality, subsampling=0, optimize=True)
    return {png.name: str(png), jpg.name: str(jpg)}


def _render_mode(entries: Sequence[Tuple[Image.Image, dict]], mode: str,
                 style: EditorialStyle, cjk: FontFace, latin: FontFace
                 ) -> Tuple[Image.Image, Dict[str, dict]]:
    count = len(entries)
    if not 4 <= count <= 5:
        raise EditorialOverflowError(
            f"editorial style needs 4-5 strong quotes, found {count}; "
            "do not pad the pack with weak lines"
        )
    width, height = style.canvas
    strip_h = (height - style.strip_gap * (count - 1)) // count
    max_width = round(width * style.max_width_ratio)
    canvas = Image.new("RGB", (width, height), style.gap_color)
    report: Dict[str, dict] = {}
    y = 0
    for frame, quote in entries:
        crop = cover_crop(frame, width, strip_h, style.crop_center_y)
        zh_info = en_info = None
        if mode in {"zh", "bilingual"}:
            zh_info = fit_text(
                normalize_zh_typography(str(quote.get("recommended_zh", ""))),
                normalize_zh_typography(str(quote.get("compact_zh", ""))),
                cjk,
                style.zh_font_range if mode == "zh" else style.inline_zh_font_range,
                max_width,
                "zh",
                style.zh_line_spacing,
            )
        if mode in {"en", "bilingual"}:
            en_text = str(quote.get("display_en") or quote.get("exact_source_text") or "")
            en_info = fit_text(
                en_text, en_text, latin,
                style.en_font_range if mode == "en" else style.inline_en_font_range,
                max_width,
                "en",
                style.en_line_spacing,
            )
        strip, detail = compose_strip(crop, zh_info, en_info, style)
        canvas.paste(strip, (0, y))
        report[str(quote.get("quote_id"))] = detail
        y += strip_h + style.strip_gap
    return _rounded(canvas, style.corner_radius, style.gap_color), report


def render_pack(work_dir: str, pack: dict, chosen_frames: Dict[str, str],
                mode: str, outputs_dir: Optional[str] = None,
                style_name: str = "editorial") -> Dict[str, object]:
    style = load_editorial_style(style_name)
    cjk, latin = resolve_editorial_fonts()
    pack_id = str(pack["pack"]["pack_id"])
    output_dir = Path(outputs_dir or Path(work_dir) / "packs" / pack_id / "outputs")
    output_dir.mkdir(parents=True, exist_ok=True)

    quotes = sorted(pack.get("quotes", []), key=lambda q: int(q.get("order", 0)))
    entries: List[Tuple[Image.Image, dict]] = []
    for quote in quotes:
        qid = str(quote.get("quote_id"))
        path = chosen_frames.get(qid)
        if not path or not os.path.exists(path):
            raise RuntimeError(f"{qid}: frame missing ({path})")
        image = Image.open(path).convert("RGB")
        entries.append((image, quote))

    requested = {
        "pair": ("zh", "en"),
        "inline": ("bilingual",),
        "all": ("zh", "en", "bilingual"),
    }[mode]
    produced: Dict[str, str] = {}
    layout: Dict[str, dict] = {
        "style": style_name,
        "canvas": list(style.canvas),
        "cjk_face": {"path": cjk.path, "index": cjk.index, "name": cjk.name},
        "latin_face": {"path": latin.path, "index": latin.index, "name": latin.name},
        "modes": {},
    }
    stems = {"zh": "01_zh", "en": "02_en", "bilingual": "03_bilingual"}
    for render_mode in requested:
        image, mode_report = _render_mode(entries, render_mode, style, cjk, latin)
        produced.update(_save(image, output_dir, stems[render_mode], style))
        layout["modes"][render_mode] = mode_report

    report_path = output_dir / "layout_report.json"
    report_path.write_text(json.dumps(layout, ensure_ascii=False, indent=2), encoding="utf-8")
    produced[report_path.name] = str(report_path)
    return {
        "produced": produced,
        "layout_report": layout,
        "fit_ok": {str(q.get("quote_id")): True for q in quotes},
        "out_dir": str(output_dir),
    }
