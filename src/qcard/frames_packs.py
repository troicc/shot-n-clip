"""V2 frame pipeline for packs: candidate extraction keyed by quote_id
inside each pack dir, review clips for needs_audio_check quotes, and the
per-pack contact sheet."""

from __future__ import annotations

import json
import os
import shutil
from typing import Dict, List, Optional, Tuple

from PIL import Image

from . import frames as frames_mod
from .context_builder import needs_audio_check
from .models_compat import evidence_for_quote
from .utils import fmt_ts, run_cmd


def ensure_pack_frames(video: str, pack: dict, source_map, work_dir: str,
                       entities: Optional[List] = None) -> Dict[str, str]:
    """Extract/score candidate frames for one pack's quotes.

    Frames land in work/<vid>/packs/<pack>/frames/{candidates,selected}.
    quote_id keys are namespaced (pack quotes are q01.. within the pack).
    """
    pack_id = pack["pack"]["pack_id"]
    pack_dir = os.path.join(work_dir, "packs", pack_id)
    cand_dir = os.path.join(pack_dir, "frames", "candidates")
    sel_dir = os.path.join(pack_dir, "frames", "selected")
    for d in (cand_dir, sel_dir):
        os.makedirs(d, exist_ok=True)

    duration = frames_mod.probe_duration_safe(video)
    chosen: Dict[str, str] = {}
    manifest: Dict[str, dict] = {}

    for q in pack["quotes"]:
        qid = q["quote_id"]
        start = q["source_spans"][0]["start_sec"]
        end = q["source_spans"][-1]["end_sec"]
        if q.get("frame_time_sec") is not None:
            t = q["frame_time_sec"]
            path = os.path.join(cand_dir, f"{qid}_pinned_{t:.3f}.jpg")
            if not (os.path.exists(path) and os.path.getsize(path) > 0):
                if not frames_mod.extract_frame(video, t, path):
                    raise RuntimeError(f"{qid}: pinned frame failed at {t}s")
            dst = os.path.join(sel_dir, f"{qid}.jpg")
            shutil.copyfile(path, dst)
            chosen[qid] = dst
            manifest[qid] = {"t": t, "ts": fmt_ts(t, True), "reason": "pinned"}
            continue
        times = frames_mod.candidate_times(start, end, duration)[:12]
        cands = []
        for t in times:
            path = os.path.join(cand_dir, f"{qid}_{t:.3f}.jpg")
            if not (os.path.exists(path) and os.path.getsize(path) > 0):
                if not frames_mod.extract_frame(video, t, path):
                    continue
            cands.append(frames_mod.FrameCandidate(
                quote_id=qid, t=t, path=path,
                phash=frames_mod.perceptual_hash(Image.open(path))))
        if not cands:
            raise RuntimeError(
                f"{qid}: all candidate extractions failed in "
                f"[{start:.1f},{end:.1f}]")
        ranked = frames_mod.score_candidates(cands)
        best = ranked[0] if ranked else min(
            cands, key=lambda c: abs(c.t - (start + end) / 2))
        dst = os.path.join(sel_dir, f"{qid}.jpg")
        shutil.copyfile(best.path, dst)
        chosen[qid] = dst
        manifest[qid] = {
            "t": best.t, "ts": fmt_ts(best.t, True),
            "reason": f"score {best.score:.2f} (sharp={best.sharpness:.0f}, "
                      f"drange={best.drange:.0f}, flat={best.flat:.2f})",
            "metrics": [c.metric_row() for c in cands],
        }
    _write_pack_contact_sheet(pack, manifest, cand_dir,
                              os.path.join(pack_dir, "frames",
                                           "contact_sheet.jpg"))
    with open(os.path.join(pack_dir, "frames", "frame_manifest.json"), "w",
              encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
    return chosen


def _write_pack_contact_sheet(pack, manifest, cand_dir, out_path) -> None:
    import math
    from PIL import ImageDraw
    cols = 5
    cells = []
    for q in pack["quotes"]:
        qid = q["quote_id"]
        for m in (manifest.get(qid, {}).get("metrics") or []):
            path = os.path.join(cand_dir, f"{qid}_{m['t']:.3f}.jpg")
            if os.path.exists(path):
                cells.append((qid, m, path))
    if not cells:
        return
    rows = math.ceil(len(cells) / cols)
    sheet = Image.new("RGB", (cols * frames_mod.THUMB_W,
                              rows * (frames_mod.THUMB_H + 26)), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    for idx, (qid, m, path) in enumerate(cells):
        r, c = divmod(idx, cols)
        x0, y0 = c * frames_mod.THUMB_W, r * (frames_mod.THUMB_H + 26)
        thumb = Image.open(path).resize((frames_mod.THUMB_W,
                                         frames_mod.THUMB_H), Image.LANCZOS)
        sheet.paste(thumb, (x0, y0))
        star = "★" if abs(m.get("t", -1) - manifest.get(qid, {}).get("t", -2)) < 1e-6 else " "
        label = f"{star}{qid} {m['ts']}"
        if m.get("rejected_reason"):
            label += f" ✗{m['rejected_reason'][:16]}"
        else:
            label += f" s={m.get('score', 0):.2f}"
        draw.text((x0 + 4, y0 + frames_mod.THUMB_H + 2), label,
                  fill=(255, 215, 0) if star == "★" else (200, 200, 200))
    sheet.save(out_path, quality=90)


def export_review_clips(video: str, pack: dict, source_map, work_dir: str,
                        entities=None) -> List[str]:
    """10–25s clips (video-only) for quotes flagged needs_manual_audio_check.

    Listed in review_queue.md by the caller. Never marks anything verified.
    """
    pack_id = pack["pack"]["pack_id"]
    clips_dir = os.path.join(work_dir, "packs", pack_id, "review_clips")
    os.makedirs(clips_dir, exist_ok=True)
    auto = source_map.caption_kind == "auto"
    exported = []
    for q in pack["quotes"]:
        ev = evidence_for_quote(source_map, q["exact_source_text"])
        if isinstance(ev, dict) and ev.get("error"):
            continue
        if not needs_audio_check(ev, auto):
            continue
        qid = q["quote_id"]
        start = max(0.0, q["source_spans"][0]["start_sec"] - 7.0)
        dur = min(25.0, max(10.0, q["source_spans"][-1]["end_sec"] - start + 7.0))
        out = os.path.join(clips_dir, f"{qid}.mp4")
        if not (os.path.exists(out) and os.path.getsize(out) > 1000):
            result = run_cmd(["ffmpeg", "-hide_banner", "-loglevel", "error",
                              "-ss", f"{start:.3f}", "-i", video, "-t",
                              f"{dur:.3f}", "-an", "-c:v", "libx264",
                              "-preset", "fast", "-y", out], timeout=120)
            if result.returncode != 0:
                continue
        exported.append(out)
    return exported
