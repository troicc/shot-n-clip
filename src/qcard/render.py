"""Deterministic collage rendering with Pillow. classic style: 1080x1440, 6 strips."""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import yaml
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .models import Quote, Selection
from .utils import find_cjk_font, find_latin_font, fmt_ts

CANVAS_W = 1080
CANVAS_H = 1440


class OverflowError_(Exception):
    """Raised when text cannot fit at the minimum allowed font size."""


@dataclass
class StyleConfig:
    name: str = "classic"
    corner_radius: int = 48
    strip_gap: int = 3
    gap_color: Tuple[int, int, int] = (12, 12, 14)
    band_alpha: int = 178          # ~70% opacity over 255 -> 62%-76% band
    text_color: Tuple[int, int, int] = (255, 255, 255)
    band_inset_x: int = 0          # band spans the full strip width in classic
    band_shadow_blur: int = 2
    zh_font_range: Tuple[int, int] = (50, 42)      # (max, min) autoshrink window
    en_font_range: Tuple[int, int] = (36, 28)
    inline_zh_font_range: Tuple[int, int] = (38, 32)
    inline_en_font_range: Tuple[int, int] = (28, 22)
    zh_line_spacing: float = 1.18
    en_line_spacing: float = 1.12
    max_lines: int = 2
    inline_default_count: int = 5


def load_style(config_root: str, style_name: str) -> StyleConfig:
    path = os.path.join(config_root, "styles", f"{style_name}.yaml")
    cfg = StyleConfig(name=style_name)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
        for key in ("corner_radius", "strip_gap", "band_alpha", "max_lines",
                    "inline_default_count"):
            if key in raw:
                setattr(cfg, key, raw[key])
        for key in ("zh_font_range", "en_font_range",
                    "inline_zh_font_range", "inline_en_font_range"):
            if key in raw and isinstance(raw[key], list) and len(raw[key]) == 2:
                setattr(cfg, key, (int(raw[key][0]), int(raw[key][1])))
        if "gap_color" in raw:
            cfg.gap_color = tuple(raw["gap_color"])
        if "text_color" in raw:
            cfg.text_color = tuple(raw["text_color"])
        if "band_alpha" in raw and not (0.62 * 255 <= raw["band_alpha"] <= 0.76 * 255):
            # Keep the band in the readable 62%-76% opacity window.
            cfg.band_alpha = int(max(0.62 * 255, min(0.76 * 255, raw["band_alpha"])))
    return cfg


# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------


@dataclass
class FontBook:
    cjk_path: Optional[str]
    latin_path: Optional[str]
    tried: List[str] = field(default_factory=list)


def resolve_fonts() -> FontBook:
    tried: List[str] = []
    cjk = find_cjk_font(tried)
    latin = find_latin_font(tried)
    return FontBook(cjk_path=cjk, latin_path=latin, tried=tried)


def _font(book: FontBook, path: Optional[str], size: int, kind: str) -> ImageFont.FreeTypeFont:
    source = path
    if source is None or not os.path.exists(source):
        raise RuntimeError(
            f"No usable {kind} font found. Tried: {', '.join(book.tried) or '(none)'}. "
            "Next step: install PingFang SC / Noto Sans CJK (for CJK) or "
            "Helvetica / DejaVu (for latin), then re-run.")
    return ImageFont.truetype(source, size)


# ---------------------------------------------------------------------------
# Text layout: wrap + autoshrink with hard floor -> OverflowError_
# ---------------------------------------------------------------------------


def _text_width(font: ImageFont.FreeTypeFont, text: str) -> int:
    return font.getbbox(text)[2] if text else 0


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> List[str]:
    """CJK-aware greedy wrap: CJK breaks anywhere, latin breaks on spaces."""
    lines: List[str] = []
    cur = ""
    for ch in text:
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        if _text_width(font, cur + ch) <= max_w:
            cur += ch
        else:
            if ch.isspace():
                lines.append(cur)
                cur = ""
            elif cur:
                lines.append(cur)
                cur = ch
            else:
                cur = ch
    if cur:
        lines.append(cur)
    # Trim orphan spaces.
    return [ln.strip() for ln in lines if ln.strip()]


def layout_text(text: str, font_path: Optional[str], size_range: Tuple[int, int],
                max_w: int, max_lines: int, spacing: float,
                kind: str, book: FontBook) -> Tuple[ImageFont.FreeTypeFont, List[str], int]:
    """Try sizes high->low; raise OverflowError_ below the floor."""
    hi, lo = size_range
    for size in range(hi, lo - 1, -1):
        font = _font(book, font_path, size, kind)
        lines = wrap_text(text, font, max_w)
        if len(lines) <= max_lines:
            line_h = int(size * spacing)
            return font, lines, line_h * len(lines)
    raise OverflowError_(
        f"text cannot fit in {max_lines} lines at ≥{lo}px {kind} font: "
        f"{text[:60]}{'…' if len(text) > 60 else ''}. "
        "Next step: shorten this quote in selection.json (swap for a shorter "
        "complete sentence — do not truncate mid-idea), then re-run.")


# ---------------------------------------------------------------------------
# Strip compositing
# ---------------------------------------------------------------------------


def cover_crop(img: Image.Image, w: int, h: int) -> Image.Image:
    """Scale to fill then center-crop (cover). Keeps faces/upper body centered."""
    sw, sh = img.size
    scale = max(w / sw, h / sh)
    nw, nh = max(1, int(math.ceil(sw * scale))), max(1, int(math.ceil(sh * scale)))
    img = img.resize((nw, nh), Image.LANCZOS)
    left = (nw - w) // 2
    top = (nh - h) // 2
    return img.crop((left, top, left + w, top + h))


def draw_band_text(strip: Image.Image, lines: List[str], font: ImageFont.FreeTypeFont,
                   line_h: int, cfg: StyleConfig, book: FontBook) -> None:
    """Semi-transparent black band + centered white text, pixel-checked."""
    w, h = strip.size
    text_block_h = line_h * len(lines)
    band_h = text_block_h + int(line_h * 0.55)
    y0 = (h - band_h) // 2
    y0 = max(4, min(y0, h - band_h - 4))  # band must stay inside the strip
    band = Image.new("RGBA", (w, band_h), (0, 0, 0, cfg.band_alpha))
    strip_rgba = strip.convert("RGBA")
    strip_rgba.alpha_composite(band, (0, y0))
    strip.paste(strip_rgba.convert("RGB"), (0, 0))

    draw = ImageDraw.Draw(strip)
    y = y0 + (band_h - text_block_h) // 2
    for ln in lines:
        tw = _text_width(font, ln)
        x = max(0, (w - tw) // 2)
        # Very light shadow for legibility; no neon/gradient.
        if cfg.band_shadow_blur:
            shadow = Image.new("RGBA", strip.size, (0, 0, 0, 0))
            sdraw = ImageDraw.Draw(shadow)
            sdraw.text((x + 1, y + 1), ln, font=font, fill=(0, 0, 0, 110))
            shadow = shadow.filter(ImageFilter.GaussianBlur(cfg.band_shadow_blur))
            strip_rgba = strip.convert("RGBA")
            strip_rgba.alpha_composite(shadow)
            strip.paste(strip_rgba.convert("RGB"), (0, 0))
            draw = ImageDraw.Draw(strip)
        draw.text((x, y), ln, font=font, fill=cfg.text_color)
        y += line_h


def rounded_mask(size: Tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=255)
    return mask


def compose_collage(entries: List[Tuple[Image.Image, str, str]], cfg: StyleConfig,
                    book: FontBook, font_path: Optional[str],
                    size_range: Tuple[int, int], spacing: float,
                    kind: str) -> Image.Image:
    """entries: (frame image, text, quote_id). Equal-height strips, no outer margin."""
    n = len(entries)
    gap = cfg.strip_gap
    strip_h = (CANVAS_H - gap * (n - 1)) // n
    if strip_h < 160:
        raise OverflowError_(f"{n} strips would make each only {strip_h}px tall; "
                             "reduce quote count (inline mode defaults to 5).")
    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), cfg.gap_color)
    y = 0
    for img, text, _qid in entries:
        strip = cover_crop(img, CANVAS_W, strip_h)
        font, lines, block_h = layout_text(
            text, font_path, size_range, int(CANVAS_W * 0.9), cfg.max_lines,
            spacing, kind, book)
        draw_band_text(strip, lines, font, block_h // len(lines), cfg, book)
        canvas.paste(strip, (0, y))
        y += strip_h + gap
    mask = rounded_mask((CANVAS_W, CANVAS_H), cfg.corner_radius)
    out = Image.new("RGB", (CANVAS_W, CANVAS_H), cfg.gap_color)
    out.paste(canvas, (0, 0), mask)
    return out


def compose_inline(entries: List[Tuple[Image.Image, str, str]], selection: Selection,
                   cfg: StyleConfig, book: FontBook) -> Image.Image:
    """Bilingual single card: zh on top of en inside one band, default 5 strips."""
    n = len(entries)
    gap = cfg.strip_gap
    strip_h = (CANVAS_H - gap * (n - 1)) // n
    if strip_h < 200:
        raise OverflowError_(f"{n} inline strips -> {strip_h}px each; use ≤5 quotes.")
    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), cfg.gap_color)
    y = 0
    cjk_font_path = book.cjk_path if book.cjk_path and _has_cjk(entries) else book.latin_path
    for img, zh, en in entries:
        strip = cover_crop(img, CANVAS_W, strip_h)
        font_zh, lines_zh, h_zh = layout_text(
            zh, book.cjk_path or book.latin_path, cfg.inline_zh_font_range,
            int(CANVAS_W * 0.9), cfg.max_lines, cfg.zh_line_spacing, "zh", book)
        font_en, lines_en, h_en = layout_text(
            en, book.latin_path or book.cjk_path, cfg.inline_en_font_range,
            int(CANVAS_W * 0.9), cfg.max_lines, cfg.en_line_spacing, "en", book)
        line_h_zh = h_zh // max(len(lines_zh), 1)
        line_h_en = h_en // max(len(lines_en), 1)
        total_text = h_zh + int(line_h_en * 0.5) + h_en
        band_h = total_text + int(line_h_zh * 0.5)
        w, h = strip.size
        y0 = max(4, min((h - band_h) // 2, h - band_h - 4))
        band = Image.new("RGBA", (w, band_h), (0, 0, 0, cfg.band_alpha))
        strip_rgba = strip.convert("RGBA")
        strip_rgba.alpha_composite(band, (0, y0))
        strip.paste(strip_rgba.convert("RGB"), (0, 0))
        draw = ImageDraw.Draw(strip)
        ty = y0 + int(line_h_zh * 0.25)
        for ln in lines_zh:
            draw.text((max(0, (w - _text_width(font_zh, ln)) // 2), ty), ln,
                      font=font_zh, fill=cfg.text_color)
            ty += line_h_zh
        ty += int(line_h_en * 0.5) - int(line_h_en * 0.35)
        for ln in lines_en:
            draw.text((max(0, (w - _text_width(font_en, ln)) // 2), ty), ln,
                      font=font_en, fill=(235, 235, 235))
            ty += line_h_en
        canvas.paste(strip, (0, y))
        y += strip_h + gap
    mask = rounded_mask((CANVAS_W, CANVAS_H), cfg.corner_radius)
    out = Image.new("RGB", (CANVAS_W, CANVAS_H), cfg.gap_color)
    out.paste(canvas, (0, 0), mask)
    return out


def _has_cjk(entries) -> bool:
    return any(any("一" <= ch <= "鿿" for ch in zh) for _, zh, _ in entries)


# ---------------------------------------------------------------------------
# Public build entry
# ---------------------------------------------------------------------------


def render_outputs(work_dir: str, selection: Selection, cfg: StyleConfig,
                   chosen_frames: Dict[str, str], mode: str,
                   fonts: Optional[FontBook] = None) -> Dict[str, str]:
    """mode: pair | inline | all. Returns {output_name: abs_path}."""
    fonts = fonts or resolve_fonts()
    outputs_dir = os.path.join(work_dir, "outputs")
    os.makedirs(outputs_dir, exist_ok=True)
    produced: Dict[str, str] = {}

    quotes = selection.quotes
    entries_all = []
    for q in quotes:
        path = chosen_frames.get(q.id)
        if not path or not os.path.exists(path):
            raise RuntimeError(
                f"{q.id}: selected frame missing ({path}). Next step: re-run "
                "`bin/qcard build <work-dir>`.")
        entries_all.append((Image.open(path), q, q.id))

    def save(img: Image.Image, name: str) -> None:
        png = os.path.join(outputs_dir, name)
        img.save(png)
        jpg = os.path.join(outputs_dir, name.replace(".png", ".jpg"))
        img.save(jpg, quality=92)
        produced[name] = png
        produced[name.replace(".png", ".jpg")] = jpg

    if mode in ("pair", "all"):
        zh_entries = [(img, q.display_zh, q.id) for img, q, _ in entries_all]
        en_entries = [(img, q.display_en, q.id) for img, q, _ in entries_all]
        save(compose_collage(zh_entries, cfg, fonts, fonts.cjk_path or fonts.latin_path,
                             cfg.zh_font_range, cfg.zh_line_spacing, "zh"), "01_zh.png")
        save(compose_collage(en_entries, cfg, fonts, fonts.latin_path or fonts.cjk_path,
                             cfg.en_font_range, cfg.en_line_spacing, "en"), "02_en.png")
    if mode in ("inline", "all"):
        inline_entries = [(img, q.display_zh, q.display_en) for img, q, _ in entries_all]
        save(compose_inline(inline_entries, selection, cfg, fonts), "03_bilingual.png")

    _write_render_manifest(work_dir, selection, cfg, fonts, produced, chosen_frames,
                           mode)
    return produced


def _write_render_manifest(work_dir: str, selection: Selection, cfg: StyleConfig,
                           fonts: FontBook, produced: Dict[str, str],
                           chosen_frames: Dict[str, str], mode: str) -> None:
    frames_meta = {}
    frames_manifest = os.path.join(work_dir, "frames", "frame_manifest.json")
    if os.path.exists(frames_manifest):
        with open(frames_manifest, encoding="utf-8") as fh:
            frames_meta = json.load(fh).get("frames", {})

    manifest = {
        "schema_version": SELECTION_SCHEMA_VERSION,
        "style": cfg.name,
        "mode": mode,
        "canvas": [CANVAS_W, CANVAS_H],
        "strip_gap": cfg.strip_gap,
        "corner_radius": cfg.corner_radius,
        "band_alpha": cfg.band_alpha,
        "fonts": {
            "cjk": fonts.cjk_path,
            "latin": fonts.latin_path,
        },
        "angle": selection.angle.title_zh,
        "video": {
            "video_id": selection.video_id,
            "title": selection.video_title,
            "channel": selection.channel,
            "url": selection.source_url,
        },
        "quotes": [
            {
                "id": q.id,
                "order": q.order,
                "ts": fmt_ts(q.start_sec, with_ms=True),
                "start_sec": q.start_sec,
                "end_sec": q.end_sec,
                "display_zh": q.display_zh,
                "display_en": q.display_en,
                "frame": frames_meta.get(q.id, {}),
                "frame_source": chosen_frames.get(q.id),
            }
            for q in selection.quotes
        ],
        "outputs": produced,
    }
    path = os.path.join(work_dir, "outputs", "manifest.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)


SELECTION_SCHEMA_VERSION = "1.0"
