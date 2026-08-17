# classic Layout Spec

Master: 1080×1440 RGB PNG + quality-92 JPG copy.

## Structure

- N equal-height horizontal video strips (default 6; inline default 5).
- No outer white margin; strips fill the whole canvas.
- Outer corner radius 44–52 px (default 48).
- Strip separators: 2–4 px (default 3) near-black `#0C0C0E`; no card-like gaps.
- Each frame is cover-cropped to the strip (center crop; deterministic — no
  per-strip jitter). Human faces/upper body stay in frame because the crop is
  centered on the source framing.

## Text band

- Semi-transparent black band spanning the strip width, alpha ≈ 62%–76%
  (default 178/255 ≈ 70%) — strong enough to cover burned-in video subtitles.
- White text centered; very light shadow allowed (blur ≤2, alpha ≤110).
  No neon, no gradients, no glow.
- Band vertically centered; must never cross strip top/bottom edges.

## Typography (autoshrink windows, [max, min])

| Context | zh | en | max lines |
|---|---|---|---|
| pair 01_zh | 50→42 px | — | 2 |
| pair 02_en | — | 36→28 px | 2 |
| inline zh | 38→32 px | — | 2 |
| inline en | — | 28→22 px | 2 |

The program computes fit from actual strip height and text width; it steps from
max down to min and **must fail with an overflow error below min** — never
render unreadable text. Fix by swapping the quote for a shorter complete
sentence.

## Fonts

macOS: PingFang SC → Hiragino Sans GB → Heiti SC → Arial Unicode MS.
Linux: Noto Sans CJK → WenQuanYi. Latin: Helvetica → Arial → DejaVu.
Never copy/package/commit font files; the manifest records the paths actually
used.

## Branding

classic: no logo, no QR, no per-strip source line. Attribution lives in the
publish copy (and the optional 04_source page, off by default).

## Pixel-level acceptance checks

- corners show backing color within tolerance (mask did its job)
- separator rows are near gap_color across the full width
- pair outputs byte-identical in the band-free strip regions (same frames/order)
- no text pixel within 8 px of a strip edge
