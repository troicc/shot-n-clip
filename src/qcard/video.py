"""Video download (≤720p, video-only) via yt-dlp, plus duration probing."""

from __future__ import annotations

import json
import os
import shutil
from typing import Optional, Tuple

from .utils import run_cmd

VIDEO_FILENAME = "source_video.mp4"


def yt_dlp_cmd(venv_dir: Optional[str] = None) -> Optional[str]:
    """Prefer the project venv's yt-dlp (guaranteed recent), then PATH."""
    if venv_dir:
        cand = os.path.join(venv_dir, "bin", "yt-dlp")
        if os.path.exists(cand):
            return cand
    return shutil.which("yt-dlp")


def probe_duration(path: str) -> float:
    result = run_cmd([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path,
    ])
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path}: {result.stderr.strip()}")
    return float(result.stdout.strip())


def download_video(work_dir: str, url: str, venv_dir: Optional[str] = None,
                   max_height: int = 720) -> str:
    """Download best ≤720p video-only stream. Reuses cached file when present."""
    out_path = os.path.join(work_dir, VIDEO_FILENAME)
    if os.path.exists(out_path) and os.path.getsize(out_path) > 10_000:
        return out_path

    binary = yt_dlp_cmd(venv_dir)
    if not binary:
        raise RuntimeError(
            "yt-dlp not found. Next step: run `.venv/bin/pip install -U yt-dlp` "
            "or install yt-dlp system-wide."
        )

    # Fixed filename keeps video-title characters out of the path.
    template = os.path.join(work_dir, "source_video.%(ext)s")
    # Try several player clients: the default web client is frequently
    # bot-blocked; android_vr/android typically still serve progressive/DASH.
    attempts = [
        ["-f", f"bv*[height<={max_height}][ext=mp4]+ba[ext=m4a]/"
               f"bv*[height<={max_height}]+ba/"
               f"b[height<={max_height}][ext=mp4]/b[height<={max_height}]/b",
         "--merge-output-format", "mp4"],
        ["--extractor-args", "youtube:player_client=android_vr",
         "-f", f"b[height<={max_height}][ext=mp4]/b[height<={max_height}]"],
        ["--extractor-args", "youtube:player_client=android,web_safari",
         "-f", f"b[height<={max_height}]"],
    ]
    last_err = ""
    for extra in attempts:
        args = ([binary, "--no-playlist"] + extra +
                ["-o", template, "--no-part", url])
        result = run_cmd(args, timeout=1800)
        if result.returncode == 0 and _find_source(work_dir, out_path):
            return out_path
        last_err = (result.stderr.strip()[-500:] or result.stdout.strip()[-500:])

    raise RuntimeError(
        "yt-dlp download failed with every player-client fallback: " + last_err
        + " | Next step: check the URL, or if YouTube is blocking this IP, retry later."
    )


def _find_source(work_dir: str, out_path: str) -> Optional[str]:
    if os.path.exists(out_path) and os.path.getsize(out_path) > 10_000:
        return out_path
    for name in sorted(os.listdir(work_dir)):
        if name.startswith("source_video.") and os.path.getsize(
                os.path.join(work_dir, name)) > 10_000:
            actual = os.path.join(work_dir, name)
            if name != VIDEO_FILENAME:
                os.replace(actual, out_path)
            return out_path
    return None


def video_resolution(path: str) -> Tuple[int, int]:
    result = run_cmd([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "json", path,
    ])
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path}: {result.stderr.strip()}")
    streams = json.loads(result.stdout).get("streams", [])
    if not streams:
        raise RuntimeError(f"no video stream found in {path}")
    return int(streams[0]["width"]), int(streams[0]["height"])
