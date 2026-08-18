"""V2 pack renderer: per-pack 01_zh / 02_en / 03_bilingual + layout_report.

Differences from V1 render.py:
- uses wrap_text (word-boundary + widow guards, real font metrics)
- per-strip: measure lines first, then pick font size; hard floor via
  style config; falls back to compact_zh when full text overflows
- inline mode defaults to 5 quotes; 6 allowed only if every strip passes
  the readability floor
- writes layout_report.json with per-quote font/lines/box metrics
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .render import CANVAS_H, CANVAS_W, FontBook, StyleConfig, resolve_fonts
from .wrap_text import layout as wrap_layout, wrap as wrap_only

MIN_STRIP_H = 170


def load_style(config_root: str, style_name: str) -> StyleConfig:
    from .render import load_style as _load
    return _load(config_root, style_name)


# ---------------------------------------------------------------------------
# Strip composition (per-strip band sized to measured text block)
# ---------------------------------------------------------------------------


def _fit(text: str, font_path: Optional[str], sizes: List[int], max_w: int,
         max_lines: int, spacing: float, kind: str, book: FontBook
         ) -> Tuple[Optional[ImageFont.FreeTypeFont], List[str], int, int]:
    if not font_path:
        raise RuntimeError(
            f"no {kind} font available; tried: {', '.join(book.tried)}")
    return wrap_layout(text, font_path, sizes, max_w, max_lines, spacing)


def compose_strip(img: Image.Image, zh_lines_info, en_lines_info,
                  cfg: StyleConfig) -> Image.Image:
    """zh_lines_info/en_lines_info: (font, lines, line_h, block_h) or None."""
    from .render import cover_crop
    w = img.width
    parts = [x for x in (zh_lines_info, en_lines_info) if x]
    total_text = sum(p[3] for p in parts)
    gap_between = int((en_lines_info[2] if en_lines_info else 0) * 0.45) \
        if zh_lines_info and en_lines_info else 0
    band_h = total_text + gap_between + int(parts[0][2] * 0.55) if parts else 0
    h = img.height
    if band_h > h - 8:
        raise OverflowError_(
            f"text band {band_h}px exceeds strip height {h}px")
    y0 = max(4, min((h - band_h) // 2, h - band_h - 4))
    band = Image.new("RGBA", (w, band_h), (0, 0, 0, cfg.band_alpha))
    strip = img.convert("RGBA")
    strip.alpha_composite(band, (0, y0))
    strip = strip.convert("RGB")

    draw = ImageDraw.Draw(strip)
    y = y0 + (band_h - total_text - gap_between) // 2
    for part in parts:
        font, lines, line_h, _block = part
        for ln in lines:
            tw = font.getbbox(ln)[2] if ln else 0
            x = max(0, (w - tw) // 2)
            # light shadow only
            draw.text((x + 1, y + 1), ln, font=font, fill=(0, 0, 0, 110))
            color = cfg.text_color if part is parts[0] else (235, 235, 235)
            draw.text((x, y), ln, font=font, fill=color)
            y += line_h
        if part is not parts[0]:
            pass
        elif len(parts) > 1:
            y += gap_between
    return strip


class OverflowError_(Exception):
    pass


# ---------------------------------------------------------------------------
# Pack render
# ---------------------------------------------------------------------------


def render_pack(work_dir: str, pack: dict, cfg: StyleConfig,
                chosen_frames: Dict[str, str], mode: str,
                fonts: Optional[FontBook] = None,
                outputs_dir: Optional[str] = None,
                max_inline: int = 6, inline_default: int = 5
                ) -> Dict[str, object]:
    fonts = fonts or resolve_fonts()
    pack_id = pack["pack"]["pack_id"]
    out_dir = outputs_dir or os.path.join(work_dir, "packs", pack_id, "outputs")
    os.makedirs(out_dir, exist_ok=True)

    quotes = pack["quotes"]
    if mode == "inline" or mode == "all":
        inline_quotes = quotes[:inline_default] if len(quotes) > inline_default \
            else quotes
        # allow 6 only when a dry-run fit succeeds for every strip
        if len(quotes) == inline_default + 1:
            if all(_dry_fit(q, cfg, fonts, 6) for q in quotes):
                inline_quotes = quotes
    else:
        inline_quotes = quotes

    layout_report: Dict[str, dict] = {}
    produced: Dict[str, str] = {}

    entries: List[Tuple[Image.Image, dict]] = []
    for q in quotes:
        path = chosen_frames.get(q["quote_id"])
        if not path or not os.path.exists(path):
            raise RuntimeError(
                f"{q['quote_id']}: frame missing ({path}). Next step: run "
                "frame extraction for this pack first.")
        entries.append((Image.open(path), q))

    def save(img: Image.Image, name: str) -> None:
        p = os.path.join(out_dir, name)
        img.save(p)
        img.save(p.replace(".png", ".jpg"), quality=92)
        produced[name] = p

    if mode in ("pair", "all"):
        zh_img = _collage([(im, q["quote_id"], q["recommended_zh"],
                            q["compact_zh"]) for im, q in entries],
                          cfg, fonts, fonts.cjk_path,
                          list(range(cfg.zh_font_range[0],
                                     cfg.zh_font_range[1] - 1, -1)),
                          cfg.zh_line_spacing, "zh", layout_report)
        save(zh_img, "01_zh.png")
        en_img = _collage([(im, q["quote_id"], q["display_en"],
                            q["display_en"]) for im, q in entries],
                          cfg, fonts, fonts.latin_path,
                          list(range(cfg.en_font_range[0],
                                     cfg.en_font_range[1] - 1, -1)),
                          cfg.en_line_spacing, "en", layout_report)
        save(en_img, "02_en.png")
    if mode in ("inline", "all"):
        bi_img = _inline_collage([(im, q) for im, q in
                                  [(im, q) for im, q in entries if q in inline_quotes]],
                                 cfg, fonts, layout_report)
        save(bi_img, "03_bilingual.png")

    report_path = os.path.join(out_dir, "layout_report.json")
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump({"pack_id": pack_id, "mode": mode,
                   "layout": layout_report}, fh, ensure_ascii=False, indent=2)
    produced["layout_report.json"] = report_path

    fit_ok = {qid.rsplit(":", 1)[0]: info.get("fits", True)
              for qid, info in layout_report.items()}
    return {"produced": produced, "layout_report": layout_report,
            "fit_ok": fit_ok, "out_dir": out_dir}


def _dry_fit(q: dict, cfg: StyleConfig, fonts: FontBook, n_quotes: int) -> bool:
    strip_h = (CANVAS_H - cfg.strip_gap * (n_quotes - 1)) // n_quotes
    if strip_h < MIN_STRIP_H:
        return False
    zh = _try_text(q["recommended_zh"], q["compact_zh"], fonts.cjk_path,
                   list(range(cfg.inline_zh_font_range[0],
                              cfg.inline_zh_font_range[1] - 1, -1)),
                   int(CANVAS_W * 0.9), cfg)
    return zh is not None


def _try_text(primary: str, fallback: str, font_path: Optional[str],
              sizes: List[int], max_w: int, cfg: StyleConfig,
              max_lines: int = 2, spacing: Optional[float] = None
              ) -> Optional[Tuple[str, ImageFont.FreeTypeFont, List[str], int, int]]:
    spacing = spacing or cfg.zh_line_spacing
    if font_path is None:
        return None
    for text in (primary, fallback):
        if not text:
            continue
        font, lines, line_h, block = wrap_layout(text, font_path, sizes,
                                                 max_w, max_lines, spacing)
        if font is not None:
            return (text, font, lines, line_h, block)
    return None


def _collage(entries, cfg, fonts, font_path, sizes, spacing, kind,
             layout_report) -> Image.Image:
    from .render import cover_crop, rounded_mask
    n = len(entries)
    strip_h = (CANVAS_H - cfg.strip_gap * (n - 1)) // n
    if strip_h < MIN_STRIP_H:
        raise OverflowError_(
            f"{n} strips → {strip_h}px each (< {MIN_STRIP_H}); reduce quote "
            "count for this mode")
    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), cfg.gap_color)
    y = 0
    used_compact: Dict[str, bool] = {}
    for img, qid, primary, fallback in entries:
        strip_img = cover_crop(img, CANVAS_W, strip_h)
        result = _try_text(primary, fallback, font_path, sizes,
                           int(CANVAS_W * 0.9), cfg, 2, spacing)
        if result is None:
            raise OverflowError_(
                f"{qid}: neither primary nor compact text fits at minimum "
                f"font size {min(sizes)}px — swap this quote for a shorter "
                "faithful sentence")
        text, font, lines, line_h, block = result
        used_compact[qid] = text is not primary
        strip = compose_strip(strip_img, (font, lines, line_h, block), None,
                              cfg)
        canvas.paste(strip, (0, y))
        layout_report[f"{qid}:{kind}"] = {
            "kind": kind,
            "font": font.path if hasattr(font, "path") else "",
            "font_size": font.size,
            "lines": len(lines),
            "text": text,
            "used_compact": text is not primary,
            "fits": True,
        }
        y += strip_h + cfg.strip_gap
    mask = rounded_mask((CANVAS_W, CANVAS_H), cfg.corner_radius)
    out = Image.new("RGB", (CANVAS_W, CANVAS_H), cfg.gap_color)
    out.paste(canvas, (0, 0), mask)
    return out


def _inline_collage(entries, cfg, fonts, layout_report) -> Image.Image:
    from .render import cover_crop, rounded_mask
    n = len(entries)
    strip_h = (CANVAS_H - cfg.strip_gap * (n - 1)) // n
    if strip_h < 200:
        raise OverflowError_(
            f"{n} inline strips → {strip_h}px each; use ≤5 quotes")
    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), cfg.gap_color)
    y = 0
    for img, q in entries:
        strip_img = cover_crop(img, CANVAS_W, strip_h)
        zh = _try_text(q["recommended_zh"], q["compact_zh"], fonts.cjk_path,
                       list(range(cfg.inline_zh_font_range[0],
                                  cfg.inline_zh_font_range[1] - 1, -1)),
                       int(CANVAS_W * 0.9), cfg, 2, cfg.zh_line_spacing)
        en = _try_text(q["display_en"], q["display_en"], fonts.latin_path,
                       list(range(cfg.inline_en_font_range[0],
                                  cfg.inline_en_font_range[1] - 1, -1)),
                       int(CANVAS_W * 0.9), cfg, 2, cfg.en_line_spacing)
        if zh is None or en is None:
            raise OverflowError_(
                f"{q['quote_id']}: bilingual strip cannot fit zh+en at "
                "minimum sizes — use 5 quotes or shorten")
        strip = compose_strip(strip_img, (zh[1], zh[2], zh[3], zh[4]),
                              (en[1], en[2], en[3], en[4]), cfg)
        canvas.paste(strip, (0, y))
        layout_report[f"{q['quote_id']}:inline"] = {
            "kind": "inline",
            "zh": {"font_size": zh[1].size, "lines": len(zh[2]),
                   "used_compact": zh[0] is not q["recommended_zh"]},
            "en": {"font_size": en[1].size, "lines": len(en[2])},
            "fits": True,
        }
        y += strip_h + cfg.strip_gap
    mask = rounded_mask((CANVAS_W, CANVAS_H), cfg.corner_radius)
    out = Image.new("RGB", (CANVAS_W, CANVAS_H), cfg.gap_color)
    out.paste(canvas, (0, 0), mask)
    return out


def render_outputs_v1(work_dir, selection, cfg, chosen, mode, fonts=None):
    """Back-compat shim delegating to the V1 renderer (unchanged behavior)."""
    from .render import render_outputs
    return render_outputs(work_dir, selection, cfg, chosen, mode, fonts)
