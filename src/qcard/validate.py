"""Validation of angles.json + selection.json against the local transcript."""

from __future__ import annotations

import os
from typing import List, Tuple

from .models import Quote, Selection, load_angles
from .transcript import find_source_text, load_meta, load_raw_snippets

MIN_QUOTES = 4
MAX_QUOTES = 8
DUPLICATE_THRESHOLD = 0.72  # normalized-char trigram Jaccard


def _trigrams(text: str) -> set:
    return {text[i:i + 3] for i in range(len(text) - 2)} if len(text) > 2 else {text}


def similarity(a: str, b: str) -> float:
    from .utils import normalize_text
    ta, tb = _trigrams(normalize_text(a)), _trigrams(normalize_text(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def validate_work_dir(work_dir: str) -> Tuple[List[str], List[str], Selection]:
    """Returns (errors, warnings, selection). Errors must fail the build."""
    errors: List[str] = []
    warnings: List[str] = []

    selection_path = os.path.join(work_dir, "selection.json")
    selection = Selection.load(selection_path, errors)
    angles = load_angles(os.path.join(work_dir, "angles.json"), errors)
    if errors:
        return errors, warnings, selection

    if selection.schema_version != "1.0":
        errors.append(f"selection.schema_version must be '1.0', got {selection.schema_version!r}")

    # ---- count ----
    n = len(selection.quotes)
    if not (MIN_QUOTES <= n <= MAX_QUOTES):
        errors.append(f"quotes: expected {MIN_QUOTES}-{MAX_QUOTES} entries, found {n}")

    # ---- order + ids ----
    orders = [q.order for q in selection.quotes]
    if orders != sorted(orders):
        errors.append(f"quotes[].order must be ascending, got {orders}")
    ids = [q.id for q in selection.quotes]
    if len(set(ids)) != len(ids):
        errors.append("quotes[].id values must be unique")

    # ---- video timing ----
    meta_path = os.path.join(work_dir, "transcript", "meta.json")
    duration = 0.0
    if os.path.exists(meta_path):
        meta = load_meta(os.path.join(work_dir, "transcript"))
        duration = meta.duration
        if selection.video_id and selection.video_id != meta.video_id:
            errors.append(
                f"selection.video_id {selection.video_id!r} != transcript videoId {meta.video_id!r}")
    else:
        warnings.append("work-dir/transcript/meta.json missing: duration bounds not checked")

    for q in selection.quotes:
        if duration:
            if q.start_sec >= duration or q.end_sec > duration + 0.75:
                errors.append(
                    f"{q.id}: timestamps [{q.start_sec:.1f}, {q.end_sec:.1f}] outside "
                    f"video duration {duration:.1f}s")
        if q.frame_time_sec is not None and duration and not (0 <= q.frame_time_sec < duration):
            errors.append(
                f"{q.id}: frame_time_sec {q.frame_time_sec} outside video duration {duration:.1f}s")

    # ---- source_text verifiability (hard failure) ----
    snippets = load_raw_snippets(os.path.join(work_dir, "transcript"))
    if not snippets and os.path.exists(os.path.join(work_dir, "transcript")):
        errors.append("transcript/transcript-raw.json missing or empty — cannot verify source_text")
    for i, q in enumerate(selection.quotes):
        if not snippets:
            break
        hit = find_source_text(snippets, q.source_text)
        if hit is None:
            errors.append(
                f"{q.id}: source_text NOT FOUND in transcript after normalization — "
                f"cannot fabricate quotes: {q.source_text[:70]}…")
        else:
            # Suggest tighter timing when wildly off (sentence times are estimates).
            t_start, t_end = hit
            if abs(t_start - q.start_sec) > 8.0 or abs(t_end - q.end_sec) > 8.0:
                warnings.append(
                    f"{q.id}: selection times [{q.start_sec:.1f},{q.end_sec:.1f}] differ "
                    f">8s from transcript hit [{t_start:.1f},{t_end:.1f}] — consider fixing")

    # ---- duplicates ----
    for i in range(len(selection.quotes)):
        for j in range(i + 1, len(selection.quotes)):
            sim = similarity(selection.quotes[i].source_text, selection.quotes[j].source_text)
            if sim >= DUPLICATE_THRESHOLD:
                errors.append(
                    f"{selection.quotes[i].id} vs {selection.quotes[j].id}: "
                    f"{sim:.0%} duplicate content — quotes must be distinct")

    # ---- lengths (display) ----
    for q in selection.quotes:
        zh_len = len([c for c in q.display_zh if not c.isspace()])
        if zh_len > 40:
            warnings.append(
                f"{q.id}: display_zh has {zh_len} hanzi (target ≤34, hard cap 40) — "
                "may overflow 2 lines")
        if len(q.display_en) > 110:
            warnings.append(
                f"{q.id}: display_en {len(q.display_en)} chars (target ≤95, hard cap 110)")

    # ---- angle selected is one of the proposed angles ----
    if angles and selection.angle.id not in {a.id for a in angles}:
        errors.append(
            f"selection.angle.id {selection.angle.id!r} not found in angles.json "
            f"({[a.id for a in angles]})")

    return errors, warnings, selection
