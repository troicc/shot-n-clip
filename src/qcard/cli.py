"""qcard CLI: preflight | fetch | validate | build | rerender | open."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from typing import List, Optional

from . import frames as frames_mod
from . import render as render_mod
from . import transcript as transcript_mod
from . import video as video_mod
from .models import SELECTION_SCHEMA_VERSION, Selection
from .publish_copy import write_all as write_publish_copy
from .validate import validate_work_dir

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORK_ROOT = os.path.join(PROJECT_ROOT, "work")
CONFIG_ROOT = os.path.join(PROJECT_ROOT, "config")
SKILL_DIR = os.path.join(PROJECT_ROOT, ".claude", "skills", "baoyu-youtube-transcript")
TRANSCRIPT_CACHE_ROOT = os.path.join(PROJECT_ROOT, ".cache", "youtube-transcript")

VIDEO_ID_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?[^#]*v=|embed/|v/|shorts/)|youtu\.be/)([a-zA-Z0-9_-]{11})"
    r"|^([a-zA-Z0-9_-]{11})$"
)


class QCardError(RuntimeError):
    pass


def extract_video_id(url_or_id: str) -> str:
    m = VIDEO_ID_RE.search(url_or_id.strip())
    if not m:
        raise QCardError(
            f"could not extract an 11-char YouTube video id from {url_or_id!r}. "
            "Next step: pass a full watch/shorts/youtu.be URL or the bare id.")
    return m.group(1) or m.group(2)


def bun_cmd() -> Optional[List[str]]:
    from .utils import which
    if which("bun"):
        return ["bun"]
    if which("npx"):
        return ["npx", "-y", "bun"]
    return None


# ---------------------------------------------------------------------------
# preflight
# ---------------------------------------------------------------------------


def cmd_preflight(_args: argparse.Namespace) -> int:
    from .utils import find_cjk_font, find_latin_font, which

    rows = []

    def check(name: str, ok: bool, warn: bool, detail: str, hint: str = "") -> None:
        status = "PASS" if ok else ("WARN" if warn else "FAIL")
        rows.append((status, name, detail, hint))

    py = sys.version_info
    check("python", py >= (3, 9), py >= (3, 9),
          f"{py.major}.{py.minor}.{py.micro}",
          "install Python ≥3.9")

    for tool in ("ffmpeg", "ffprobe"):
        path = which(tool)
        check(tool, bool(path), False, path or "not found",
              "brew install ffmpeg" if sys.platform == "darwin" else "use your package manager")

    ytdlp = video_mod.yt_dlp_cmd(os.path.join(PROJECT_ROOT, ".venv")) or which("yt-dlp")
    check("yt-dlp", bool(ytdlp), False, ytdlp or "not found",
          ".venv/bin/pip install -U yt-dlp")

    b = bun_cmd()
    check("bun/npx", bool(b), False, " ".join(b) if b else "not found",
          "brew install oven-sh/bun/bun (or keep npx)")

    tried: List[str] = []
    cjk = find_cjk_font(tried)
    check("font-cjk", bool(cjk), False, cjk or "not found",
          f"tried: {', '.join(tried)}")

    tried_l: List[str] = []
    latin = find_latin_font(tried_l)
    check("font-latin", bool(latin), False, latin or "not found",
          f"tried: {', '.join(tried_l)}")

    opencv = frames_mod.HAS_OPENCV
    rows.append(("WARN" if not opencv else "PASS", "opencv (optional)",
                 "missing — frame picking still works, no face bonus", ""))

    fails = [r for r in rows if r[0] == "FAIL"]
    for status, name, detail, hint in rows:
        line = f"[{status}] {name}: {detail}"
        if status != "PASS" and hint:
            line += f"  → {hint}"
        print(line)
    if fails:
        print(f"\npreflight: {len(fails)} FAIL — fix the items above, then re-run.")
        return 2
    print("\npreflight: all required checks passed.")
    return 0


# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------


def run_transcript_skill(url: str, out_dir: str) -> None:
    """Invoke the upstream baoyu-youtube-transcript skill CLI (argument array)."""
    b = bun_cmd()
    if not b:
        raise QCardError(
            "neither bun nor npx found — cannot run the transcript skill. "
            "Next step: brew install oven-sh/bun/bun")
    script = os.path.join(SKILL_DIR, "scripts", "main.ts")
    if not os.path.exists(script):
        raise QCardError(f"upstream skill script missing: {script}")
    os.makedirs(out_dir, exist_ok=True)
    args = b + [script, url, "--output-dir", out_dir]
    result = subprocess.run(args, capture_output=True, text=True, timeout=900)
    if result.returncode != 0:
        raise QCardError(
            "transcript skill failed: "
            + (result.stderr.strip()[-1500:] or result.stdout.strip()[-800:]))
    # The skill prints the transcript file path on success.


def cmd_fetch(args: argparse.Namespace) -> int:
    url = args.url
    video_id = extract_video_id(url)
    work_dir = os.path.join(WORK_ROOT, video_id)
    transcript_dir = os.path.join(work_dir, "transcript")

    cached_meta = os.path.join(transcript_dir, "meta.json")
    cached_raw = os.path.join(transcript_dir, "transcript-raw.json")

    if not (os.path.exists(cached_meta) and os.path.exists(cached_raw)):
        # First fetch: run upstream skill into the shared cache, then copy in.
        run_transcript_skill(url, TRANSCRIPT_CACHE_ROOT)
        src = _locate_upstream_output(video_id, TRANSCRIPT_CACHE_ROOT)
        os.makedirs(transcript_dir, exist_ok=True)
        import shutil
        for name in ("meta.json", "transcript-raw.json", "transcript-sentences.json"):
            s = os.path.join(src, name)
            if os.path.exists(s):
                shutil.copyfile(s, os.path.join(transcript_dir, name))
        img_src = os.path.join(src, "imgs", "cover.jpg")
        if os.path.exists(img_src):
            os.makedirs(os.path.join(transcript_dir, "imgs"), exist_ok=True)
            shutil.copyfile(img_src, os.path.join(transcript_dir, "imgs", "cover.jpg"))
    else:
        print(f"cache hit: {transcript_dir} (no network)")

    meta = transcript_mod.load_meta(transcript_dir)
    # Language sanity: prefer source language; en source -> en, zh source -> zh.
    lang = meta.language_code
    if lang not in ("en", "zh", "zh-Hans", "zh-CN") and not args.languages:
        print(f"note: transcript language is {lang!r}; re-run fetch with "
              "--languages en,zh if you want a different track.")

    if args.languages:
        requested = args.languages
        if lang not in requested:
            run_transcript_skill(url + " --languages " + requested, TRANSCRIPT_CACHE_ROOT)

    agent = transcript_mod.write_agent_input(
        work_dir, transcript_dir, meta, f"https://www.youtube.com/watch?v={video_id}")
    os.makedirs(os.path.join(work_dir, "frames", "candidates"), exist_ok=True)
    os.makedirs(os.path.join(work_dir, "frames", "selected"), exist_ok=True)
    os.makedirs(os.path.join(work_dir, "outputs"), exist_ok=True)

    print(json.dumps({
        "work_dir": os.path.abspath(work_dir),
        "agent_input": os.path.abspath(agent),
        "video_id": video_id,
        "title": meta.title,
        "channel": meta.channel,
        "duration_sec": meta.duration,
        "transcript_language": meta.language_code,
        "transcript_dir": os.path.abspath(transcript_dir),
    }, ensure_ascii=False, indent=2))
    return 0


def _locate_upstream_output(video_id: str, cache_root: str) -> str:
    index_path = os.path.join(cache_root, ".index.json")
    if os.path.exists(index_path):
        with open(index_path, encoding="utf-8") as fh:
            index = json.load(fh)
        rel = index.get(video_id)
        if rel:
            full = os.path.join(cache_root, rel)
            if os.path.exists(os.path.join(full, "transcript-raw.json")):
                return full
    # Fallback: scan channel/title dirs.
    for channel in sorted(os.listdir(cache_root)) if os.path.isdir(cache_root) else []:
        cdir = os.path.join(cache_root, channel)
        if not os.path.isdir(cdir):
            continue
        for title in sorted(os.listdir(cdir)):
            tdir = os.path.join(cdir, title)
            if os.path.exists(os.path.join(tdir, "transcript-raw.json")):
                meta_p = os.path.join(tdir, "meta.json")
                if os.path.exists(meta_p):
                    with open(meta_p, encoding="utf-8") as fh:
                        if json.load(fh).get("videoId") == video_id:
                            return tdir
    raise QCardError(
        f"upstream skill ran but no cached transcript for {video_id} under {cache_root}. "
        "Next step: re-run fetch; if the video has no captions, the skill will have "
        "printed 'Transcripts disabled' above — that video cannot be used without "
        "providing a local SRT (not supported in this MVP).")


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


def cmd_validate(args: argparse.Namespace) -> int:
    work_dir = _resolve_work_dir(args.work_dir)
    errors, warnings, _selection = validate_work_dir(work_dir)
    for w in warnings:
        print(f"[WARN] {w}")
    if errors:
        for e in errors:
            print(f"[ERROR] {e}")
        print(f"\nvalidate: FAILED ({len(errors)} error(s)). Fix selection.json / "
              "angles.json, then re-run.")
        return 1
    print("validate: OK")
    return 0


def _resolve_work_dir(work_dir: str) -> str:
    if os.path.isabs(work_dir) and os.path.exists(work_dir):
        return work_dir
    cand = work_dir if os.path.isabs(work_dir) else os.path.join(WORK_ROOT, work_dir)
    if not os.path.exists(cand):
        # Allow passing a full URL as <work-dir> convenience.
        try:
            vid = extract_video_id(work_dir)
            cand = os.path.join(WORK_ROOT, vid)
        except QCardError:
            raise QCardError(
                f"work dir not found: {work_dir}. Next step: run "
                "`bin/qcard fetch '<url>'` first, or pass the video id / absolute path.")
        if not os.path.exists(cand):
            raise QCardError(
                f"work dir not found: {work_dir}. Next step: run "
                "`bin/qcard fetch '<url>'` first, or pass the video id / absolute path.")
    return cand


# ---------------------------------------------------------------------------
# build / rerender
# ---------------------------------------------------------------------------


def _load_selection_checked(work_dir: str) -> Selection:
    errors, _warnings, selection = validate_work_dir(work_dir)
    if errors:
        for e in errors:
            print(f"[ERROR] {e}", file=sys.stderr)
        raise QCardError(
            f"validation failed with {len(errors)} error(s) — build aborted. "
            "Next step: fix the errors above in selection.json, then re-run validate.")
    return selection


def cmd_build(args: argparse.Namespace) -> int:
    work_dir = _resolve_work_dir(args.work_dir)
    selection = _load_selection_checked(work_dir)

    video_path = video_mod.download_video(
        work_dir, selection.source_url, venv_dir=os.path.join(PROJECT_ROOT, ".venv"))
    duration = video_mod.probe_duration(video_path)
    print(f"video ready: {video_path} ({duration:.1f}s)")

    chosen, _metrics = frames_mod.ensure_frames(video_path, selection, work_dir)
    print("frames selected + contact sheet written")

    cfg = render_mod.load_style(CONFIG_ROOT, args.style)
    produced = render_mod.render_outputs(work_dir, selection, cfg, chosen, args.mode)
    copy_paths = write_publish_copy(selection, work_dir)

    print("\nGenerated:")
    for name, path in produced.items():
        print(f"  {os.path.abspath(path)}")
    for p in copy_paths:
        print(f"  {os.path.abspath(p)}")
    print(f"  {os.path.abspath(os.path.join(work_dir, 'frames', 'contact_sheet.jpg'))}")
    return 0


def cmd_rerender(args: argparse.Namespace) -> int:
    """Text/frame edits only: no network, no transcript fetch, no video download."""
    work_dir = _resolve_work_dir(args.work_dir)
    selection = _load_selection_checked(work_dir)

    # Required local inputs must already exist.
    sel_dir = os.path.join(work_dir, "frames", "selected")
    video_path = os.path.join(work_dir, video_mod.VIDEO_FILENAME)
    problems = []
    if not os.path.isdir(sel_dir):
        problems.append(f"{sel_dir} missing — run build once first")
    changed_frames = []
    for q in selection.quotes:
        target = os.path.join(sel_dir, f"{q.id}.jpg")
        if not os.path.exists(target):
            # frame_time_sec pinned: extract locally from the existing video only.
            if q.frame_time_sec is not None and os.path.exists(video_path):
                cand_dir = os.path.join(work_dir, "frames", "candidates")
                os.makedirs(cand_dir, exist_ok=True)
                t = q.frame_time_sec
                path = os.path.join(cand_dir, f"{q.id}_pinned_{t:.3f}.jpg")
                if not frames_mod.extract_frame(video_path, t, path):
                    problems.append(f"{q.id}: pinned frame extraction failed at {t}s")
                else:
                    import shutil
                    shutil.copyfile(path, target)
                    changed_frames.append(q.id)
            else:
                problems.append(f"{q.id}: no selected frame (and no local video to extract)")
    if problems:
        for p in problems:
            print(f"[ERROR] {p}", file=sys.stderr)
        raise QCardError("rerender needs existing frames; run build first.")

    cfg = render_mod.load_style(CONFIG_ROOT, args.style)
    chosen = {q.id: os.path.join(sel_dir, f"{q.id}.jpg") for q in selection.quotes}
    produced = render_mod.render_outputs(work_dir, selection, cfg, chosen, args.mode)
    copy_paths = write_publish_copy(selection, work_dir)

    print("rerender complete (no network access performed):")
    for name, path in produced.items():
        print(f"  {os.path.abspath(path)}")
    for p in copy_paths:
        print(f"  {os.path.abspath(p)}")
    return 0


# ---------------------------------------------------------------------------
# open
# ---------------------------------------------------------------------------


def cmd_open(args: argparse.Namespace) -> int:
    work_dir = _resolve_work_dir(args.work_dir)
    outputs = os.path.join(work_dir, "outputs")
    target = outputs if os.path.isdir(outputs) else work_dir
    print(os.path.abspath(target))
    if sys.platform == "darwin":
        ok = subprocess.run(["open", target], capture_output=True).returncode == 0
    elif sys.platform.startswith("linux"):
        from .utils import which
        opener = which("xdg-open")
        ok = bool(opener) and subprocess.run([opener, target],
                                             capture_output=True).returncode == 0
    else:
        ok = False
    if not ok:
        print(f"(no system opener available; open manually: {os.path.abspath(target)})")
    return 0


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="qcard",
                                     description="quote-strip-studio deterministic CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("preflight", help="check required tools/fonts")

    p_fetch = sub.add_parser("fetch", help="fetch transcript + meta for a URL")
    p_fetch.add_argument("url")
    p_fetch.add_argument("--languages", default=None,
                         help="comma-separated priority, e.g. en,zh")

    p_val = sub.add_parser("validate", help="validate angles/selection JSON")
    p_val.add_argument("work_dir")

    p_build = sub.add_parser("build", help="download video, pick frames, render")
    p_build.add_argument("work_dir")
    p_build.add_argument("--mode", choices=["pair", "inline", "all"], default="pair")
    p_build.add_argument("--style", default="classic")

    p_re = sub.add_parser("rerender", help="re-render from selection.json only (offline)")
    p_re.add_argument("work_dir")
    p_re.add_argument("--mode", choices=["pair", "inline", "all"], default="pair")
    p_re.add_argument("--style", default="classic")

    p_open = sub.add_parser("open", help="open the outputs folder")
    p_open.add_argument("work_dir")

    args = parser.parse_args(argv)
    handlers = {
        "preflight": cmd_preflight,
        "fetch": cmd_fetch,
        "validate": cmd_validate,
        "build": cmd_build,
        "rerender": cmd_rerender,
        "open": cmd_open,
    }
    try:
        return handlers[args.command](args)
    except QCardError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except render_mod.OverflowError_ as exc:
        print(f"overflow: {exc}", file=sys.stderr)
        return 3
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
