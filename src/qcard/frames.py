"""Frame sampling, deterministic quality scoring, best-frame selection, contact sheet.

Timing caveat honored here: transcript-sentence times are proportionally
estimated upstream, so every quote window is sampled at multiple offsets and
additionally padded ±2s — we never trust one absolute timestamp.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter

from .models import Selection
from .utils import clamp, fmt_ts, run_cmd

try:
    import cv2  # type: ignore
    import numpy as _np
    HAS_OPENCV = True
except Exception:  # pragma: no cover - optional accelerator
    cv2 = None
    _np = None
    HAS_OPENCV = False

THUMB_W = 320
THUMB_H = 180


# ---------------------------------------------------------------------------
# Candidate times
# ---------------------------------------------------------------------------


def candidate_times(start: float, end: float, duration: float) -> List[float]:
    """Sample ≥5 offsets inside [start, end], ±2s padding, clamped to duration."""
    span = max(end - start, 0.0)
    mid = start + span / 2
    times = []
    if span >= 0.8:
        times = [start + 0.2 * span, start + 0.4 * span, mid, start + 0.6 * span,
                 end - 0.2 * span]
    else:
        times = [start, mid, end, mid - 0.6, mid + 0.6]
    # ±2s padding for sentence-timing drift, kept near the window.
    times += [start - 1.0, start - 2.0, end + 1.0, end + 2.0, mid - 0.6, mid + 0.6]
    out: List[float] = []
    for t in times:
        t = round(clamp(t, 0.0, max(duration - 0.05, 0.0)), 3)
        if 0 <= t < duration and t not in out:
            out.append(t)
    out.sort()
    return out


# ---------------------------------------------------------------------------
# Extraction via ffmpeg (argument arrays only)
# ---------------------------------------------------------------------------


def extract_frame(video: str, t: float, out_path: str, width: int = 1280) -> bool:
    result = run_cmd([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{t:.3f}",
        "-i", video, "-frames:v", "1", "-vf", f"scale={width}:-2",
        "-q:v", "2", "-y", out_path,
    ], timeout=60)
    return result.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0


# ---------------------------------------------------------------------------
# Deterministic quality metrics (pure Pillow; no OpenCV required)
# ---------------------------------------------------------------------------


def _gray(img: Image.Image) -> Image.Image:
    return img.convert("L")


def sharpness_score(gray: Image.Image) -> float:
    """Edge variance via a light 3x3 Laplacian approximation — higher is sharper."""
    edges = gray.filter(ImageFilter.FIND_EDGES)
    hist = edges.histogram()
    total = sum(hist)
    mean = sum(i * c for i, c in enumerate(hist)) / max(total, 1)
    variance = sum(((i - mean) ** 2) * c for i, c in enumerate(hist)) / max(total, 1)
    return variance


def brightness_stats(gray: Image.Image) -> Tuple[float, float]:
    """(mean brightness 0-255, dynamic range 0-255)."""
    hist = gray.histogram()
    total = sum(hist) or 1
    mean = sum(i * c for i, c in enumerate(hist)) / total
    lo = next((i for i, c in enumerate(hist) if c), 0)
    hi = next((i for i in range(255, -1, -1) if hist[i]), 0)
    return mean, hi - lo


def perceptual_hash(img: Image.Image) -> str:
    small = _gray(img).resize((8, 8), Image.LANCZOS)
    pixels = list(small.getdata())
    mean = sum(pixels) / len(pixels)
    bits = "".join("1" if p > mean else "0" for p in pixels)
    return format(int(bits, 2), "016x") if bits else "0" * 16


def hash_distance(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def flat_area_ratio(img: Image.Image) -> float:
    """Share of the image covered by near-uniform color blocks (poster frames etc.)."""
    small = img.convert("RGB").resize((64, 36))
    colors = small.getcolors(maxcolors=64 * 36 + 1) or []
    if not colors:
        return 0.0
    colors.sort(reverse=True)
    top = sum(c for c, _ in colors[:3]) / (64 * 36)
    return top


@dataclass
class FrameCandidate:
    quote_id: str
    t: float
    path: str
    phash: str = ""
    sharpness: float = 0.0
    brightness: float = 0.0
    drange: float = 0.0
    flat: float = 0.0
    face_bonus: float = 0.0
    score: float = 0.0
    rejected_reason: str = ""

    def metric_row(self) -> Dict:
        return {
            "t": self.t, "ts": fmt_ts(self.t, with_ms=True),
            "sharpness": round(self.sharpness, 1), "brightness": round(self.brightness, 1),
            "drange": round(self.drange, 1), "flat": round(self.flat, 3),
            "face_bonus": round(self.face_bonus, 3),
            "score": round(self.score, 2),
            "rejected_reason": self.rejected_reason,
        }


def _opencv_face_bonus(img: Image.Image) -> float:
    """Optional accelerator: +score when a reasonably-sized face is present."""
    if not HAS_OPENCV:
        return 0.0
    cascade = getattr(_opencv_face_bonus, "_cascade", None)
    if cascade is None:
        cascade_path = getattr(cv2, "data", None)
        if not cascade_path:
            _opencv_face_bonus._cascade = False
            return 0.0
        cascade = cv2.CascadeClassifier(
            os.path.join(cascade_path.haarcascades, "haarcascade_frontalface_default.xml"))
        _opencv_face_bonus._cascade = cascade
    if cascade is False or cascade.empty():
        return 0.0
    import numpy as np
    arr = np.array(img.convert("RGB"))[:, :, ::-1]
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4,
                                     minSize=(int(img.width * 0.08), int(img.height * 0.08)))
    best = 0.0
    for (x, y, w, h) in faces:
        rel = (w * h) / (img.width * img.height)
        best = max(best, min(rel * 2.5, 1.0))  # 8%-40% face area is ideal
    return best


def score_candidates(cands: List[FrameCandidate]) -> List[FrameCandidate]:
    """Reject junk deterministically, then rank what survives."""
    if not cands:
        return cands
    # Perceptual-duplicate rejection: nearest neighbor in time.
    for i, c in enumerate(cands):
        for other in cands:
            if other is c or not other.phash:
                continue
            if abs(other.t - c.t) <= 2.5 and hash_distance(c.phash, other.phash) <= 3:
                # Keep the earlier one of a duplicate pair.
                if other.t < c.t:
                    c.rejected_reason = "duplicate of nearby frame"
                break
    survivors = []
    for c in cands:
        g = _gray(Image.open(c.path))
        c.sharpness = sharpness_score(g)
        c.brightness, c.drange = brightness_stats(g)
        img = Image.open(c.path)
        c.flat = flat_area_ratio(img)
        c.face_bonus = _opencv_face_bonus(img)
        if c.rejected_reason:
            continue
        if c.brightness < 12:
            c.rejected_reason = "near-black"
            continue
        if c.brightness > 243:
            c.rejected_reason = "near-white"
            continue
        if c.drange < 30:
            c.rejected_reason = "no dynamic range (flat/solid)"
            continue
        if c.flat > 0.965:
            c.rejected_reason = "large flat color area"
            continue
        max_sharp = max((x.sharpness for x in cands if x.sharpness > 0), default=1.0)
        c.score = (
            0.45 * (c.sharpness / max_sharp)
            + 0.20 * min(c.drange / 255.0, 1.0)
            + 0.15 * c.face_bonus
            + 0.20 * (1.0 - abs(c.brightness - 128.0) / 128.0)
        )
        survivors.append(c)
    survivors.sort(key=lambda c: c.score, reverse=True)
    return survivors


# ---------------------------------------------------------------------------
# Selection + persistence
# ---------------------------------------------------------------------------


def ensure_frames(video: str, selection: Selection, work_dir: str,
                  max_per_quote: int = 12) -> Tuple[Dict[str, str], Dict[str, List[Dict]]]:
    """Extract candidate frames per quote, score, pick best.

    Returns (chosen: quote_id -> frame path, metrics) and writes
    frames/candidates/*, frames/selected/*, contact_sheet.jpg.
    """
    duration = probe_duration_safe(video)
    frames_dir = os.path.join(work_dir, "frames")
    cand_dir = os.path.join(frames_dir, "candidates")
    sel_dir = os.path.join(frames_dir, "selected")
    for d in (cand_dir, sel_dir):
        os.makedirs(d, exist_ok=True)

    chosen: Dict[str, str] = {}
    metrics: Dict[str, List[Dict]] = {}
    manifest_frames: Dict[str, Dict] = {}

    for q in selection.quotes:
        qid = q.id
        metrics[qid] = []
        # User-pinned frame time wins outright.
        if q.frame_time_sec is not None:
            t = round(clamp(float(q.frame_time_sec), 0.0, max(duration - 0.05, 0.0)), 3)
            path = os.path.join(cand_dir, f"{qid}_pinned_{t:.3f}.jpg")
            if not (os.path.exists(path) and os.path.getsize(path) > 0):
                if not extract_frame(video, t, path):
                    raise RuntimeError(
                        f"{qid}: could not extract pinned frame at {t}s. "
                        "Next step: adjust frame_time_sec in selection.json.")
            chosen[qid] = path
            manifest_frames[qid] = {
                "t": t, "ts": fmt_ts(t, with_ms=True), "path": path,
                "reason": "pinned by user via frame_time_sec", "metrics": None,
            }
            continue

        times = candidate_times(q.start_sec, q.end_sec, duration)[:max_per_quote]
        cands: List[FrameCandidate] = []
        failures = 0
        for t in times:
            path = os.path.join(cand_dir, f"{qid}_{t:.3f}.jpg")
            if not (os.path.exists(path) and os.path.getsize(path) > 0):
                if not extract_frame(video, t, path):
                    failures += 1  # single-candidate failure never aborts the quote
                    continue
            cands.append(FrameCandidate(quote_id=qid, t=t, path=path,
                                        phash=perceptual_hash(Image.open(path))))
        if not cands:
            raise RuntimeError(
                f"{qid}: every candidate extraction failed in "
                f"[{q.start_sec:.1f}, {q.end_sec:.1f}]. Next step: verify the video "
                "file plays and the quote times are inside its duration.")
        ranked = score_candidates(cands)
        for c in cands:
            metrics[qid].append(c.metric_row())
        if not ranked:  # everything rejected: fall back to mid-window frame
            mid = round((q.start_sec + q.end_sec) / 2, 3)
            fallback = next((c for c in cands if abs(c.t - mid) < 0.75),
                            min(cands, key=lambda c: abs(c.t - mid)))
            ranked = [fallback]
        best = ranked[0]
        dst = os.path.join(sel_dir, f"{qid}.jpg")
        shutil.copyfile(best.path, dst)
        chosen[qid] = dst
        manifest_frames[qid] = {
            "t": best.t, "ts": fmt_ts(best.t, with_ms=True), "path": dst,
            "reason": "highest deterministic quality score "
                      f"(sharp={best.sharpness:.0f}, drange={best.drange:.0f}, "
                      f"flat={best.flat:.2f}, face={best.face_bonus:.2f})",
            "metrics": metrics[qid],
        }

    write_contact_sheet(selection, manifest_frames, cand_dir,
                        os.path.join(frames_dir, "contact_sheet.jpg"))
    _write_frame_manifest(work_dir, manifest_frames, metrics)
    return chosen, metrics


def probe_duration_safe(video: str) -> float:
    from .video import probe_duration
    return probe_duration(video)


def _write_frame_manifest(work_dir: str, frames: Dict[str, Dict],
                          metrics: Dict[str, List[Dict]]) -> None:
    path = os.path.join(work_dir, "frames", "frame_manifest.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"frames": frames, "all_candidate_metrics": metrics}, fh,
                  ensure_ascii=False, indent=2)


def write_contact_sheet(selection: Selection, manifest_frames: Dict[str, Dict],
                        cand_dir: str, out_path: str, cols: int = 5) -> None:
    """Grid of every candidate labeled qXX + timestamp + score for human review."""
    cells = []
    label_pad = 26
    cell_h = THUMB_H + label_pad
    for q in selection.quotes:
        for m in (manifest_frames.get(q.id, {}).get("metrics") or []):
            path = os.path.join(cand_dir, f"{q.id}_{m['t']:.3f}.jpg")
            if os.path.exists(path):
                cells.append((q.id, m, path))
    if not cells:
        return
    rows = math.ceil(len(cells) / cols)
    sheet = Image.new("RGB", (cols * THUMB_W, rows * cell_h), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    for idx, (qid, m, path) in enumerate(cells):
        r, c = divmod(idx, cols)
        x0, y0 = c * THUMB_W, r * cell_h
        try:
            thumb = Image.open(path).resize((THUMB_W, THUMB_H), Image.LANCZOS)
        except Exception:
            continue
        sheet.paste(thumb, (x0, y0))
        mark = "★" if abs(m.get("t", -1) - manifest_frames.get(qid, {}).get("t", -2)) < 1e-6 else " "
        color = (255, 215, 0) if mark == "★" else (200, 200, 200)
        txt = f"{mark}{qid} {m['ts']}"
        rejected = m.get("rejected_reason") or ""
        if rejected:
            txt += f" ✗{rejected[:18]}"
        else:
            txt += f" s={m.get('score', 0):.2f}"
        draw.text((x0 + 4, y0 + THUMB_H + 2), txt, fill=color)
        if m.get("path") is None and not rejected:
            pass
    sheet.save(out_path, quality=90)
