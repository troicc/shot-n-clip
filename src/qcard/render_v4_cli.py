"""Strict V4 render entry point.

This command closes the gap between the independently reviewed V3 selection and
the legacy V2 render manifest.  It validates candidate/selection/translation
artifacts, promotes the reviewed selection, applies the non-layout V2 integrity
checks, downloads the source video when needed, extracts frames, and renders the
high-clarity 1440x1920 editorial cards.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from . import frames_packs, video as video_mod
from .editorial_quality_v3.stages import _resolve_work_dir, validate_work_dir
from .promote_selection import promote
from .render_editorial import EditorialOverflowError, render_pack

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_ROOT = PROJECT_ROOT / "config"


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing required file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc


def _load_source_map(work_dir: Path):
    from .source_integrity import SourceMap

    data = _read_json(work_dir / "source_map.json")
    return SourceMap(
        video_id=data["video_id"],
        source_language=data["source_language"],
        caption_kind=data["caption_kind"],
        segments=data["segments"],
        entities=data.get("entities", []),
        warnings=data.get("warnings", []),
    )


def _load_entities(work_dir: Path) -> List[Any]:
    from .entity_glossary import Entity

    path = work_dir / "entity_glossary.json"
    if not path.exists():
        return []
    raw = _read_json(path)
    return [
        Entity(
            entity_id=item["entity_id"],
            source_form=item["source_form"],
            canonical_zh=item.get("canonical_zh"),
            type=item["type"],
            do_not_guess=item.get("do_not_guess", True),
            evidence=item.get("evidence", []),
            status=item.get("status", "needs_review"),
            note=item.get("note", ""),
        )
        for item in raw
    ]


def _validate_promoted_manifest(work_dir: Path) -> None:
    from . import pack_validation

    data = _read_json(work_dir / "angle_packs.json")
    result = pack_validation.validate_pack_set(data)
    if result.errors:
        raise ValueError(
            "promoted angle_packs.json failed V2 pack-set validation:\n- "
            + "\n- ".join(result.errors)
        )


def _copy_errors(work_dir: Path, pack_id: str, pack: dict) -> List[str]:
    from . import copy_validation

    errors: List[str] = []
    for platform in ("xhs", "wechat"):
        path = work_dir / "packs" / pack_id / f"publish_{platform}.json"
        if not path.exists():
            errors.append(f"missing {path.name}")
            continue
        data = _read_json(path)
        current, _warnings = copy_validation.validate_copy(data, platform, pack)
        errors.extend(f"{platform}: {item}" for item in current)
    return errors


def _write_contact_sheet(work_dir: Path, produced: Dict[str, List[str]]) -> Optional[Path]:
    from PIL import Image, ImageDraw, ImageOps

    cards: List[tuple[str, Path]] = []
    for pack_id, paths in produced.items():
        for raw in paths:
            path = Path(raw)
            if path.suffix.lower() == ".jpg" and path.name in {
                "01_zh.jpg", "02_en.jpg", "03_bilingual.jpg"
            }:
                cards.append((pack_id, path))
    if not cards:
        return None
    thumb_w, thumb_h, label_h = 360, 480, 34
    columns = 3
    rows = (len(cards) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * thumb_w, rows * (thumb_h + label_h)), "#111111")
    draw = ImageDraw.Draw(sheet)
    for index, (pack_id, path) in enumerate(cards):
        image = Image.open(path).convert("RGB")
        thumb = ImageOps.fit(image, (thumb_w, thumb_h), Image.Resampling.LANCZOS)
        x = (index % columns) * thumb_w
        y = (index // columns) * (thumb_h + label_h)
        sheet.paste(thumb, (x, y))
        draw.text((x + 8, y + thumb_h + 8), f"{pack_id} / {path.stem}", fill="white")
    output = work_dir / "render_v4_contact_sheet.jpg"
    sheet.save(output, quality=94, subsampling=0, optimize=True)
    return output


def _v2_integrity_errors(pack: dict, source_map: Any, entities: List[Any]) -> List[str]:
    """Run V2 source/entity/display-English checks without its old dispersion rule.

    V2's historical "max two quotes per 30 seconds" rule conflicts with the V4
    locality requirement and was a direct cause of topic-collage packs.  All
    other V2 errors remain hard failures.
    """
    from . import pack_validation

    result = pack_validation.validate_editorial_pack(
        pack, source_map, entities, str(CONFIG_ROOT), layout_fit=None
    )
    ignored_fragment = "quotes within ±15s"
    return [error for error in result.errors if ignored_fragment not in error]


def _ready_pack_ids(selection: dict) -> List[str]:
    return [
        str(pack.get("pack_id"))
        for pack in selection.get("packs", [])
        if isinstance(pack, dict) and pack.get("status") == "ready"
    ]


def _ensure_video(work_dir: Path, video_id: str, offline: bool) -> Path:
    target = work_dir / video_mod.VIDEO_FILENAME
    if target.exists() and target.stat().st_size > 10_000:
        return target
    if offline:
        raise ValueError(
            f"{target} is missing and --offline was requested; run without --offline once"
        )
    url = f"https://www.youtube.com/watch?v={video_id}"
    resolved = video_mod.download_video(
        str(work_dir), url, venv_dir=str(PROJECT_ROOT / ".venv"), max_height=720
    )
    return Path(resolved)


def render_work_dir(
    work_dir: Path,
    mode: str = "all",
    style: str = "editorial",
    offline: bool = False,
) -> Dict[str, Any]:
    report, summary = validate_work_dir(work_dir, strict=True)
    if not report.ok:
        raise ValueError(
            "V3 strict validation failed; rendering is blocked:\n- "
            + "\n- ".join(report.errors)
        )

    # Rewrite angle_packs.json from the independently approved V3 selection so
    # stale V2 proposals cannot silently drive rendering.
    promoted_path = promote(work_dir)
    _validate_promoted_manifest(work_dir)
    selection = _read_json(work_dir / "selection_audit.json")
    ready_ids = _ready_pack_ids(selection)
    if not ready_ids:
        raise ValueError("selection_audit.json contains no ready pack")

    source_map = _load_source_map(work_dir)
    entities = _load_entities(work_dir)
    video_path = _ensure_video(work_dir, source_map.video_id, offline)

    produced: Dict[str, List[str]] = {}
    for pack_id in ready_ids:
        pack_path = work_dir / "packs" / pack_id / "editorial_pack.json"
        pack = _read_json(pack_path)
        v2_errors = _v2_integrity_errors(pack, source_map, entities)
        if v2_errors:
            raise ValueError(
                f"{pack_id}: V2 source/entity/display-English validation failed:\n- "
                + "\n- ".join(v2_errors)
            )
        copy_errors = _copy_errors(work_dir, pack_id, pack)
        if copy_errors:
            raise ValueError(
                f"{pack_id}: platform-copy validation failed:\n- "
                + "\n- ".join(copy_errors)
            )

        chosen = frames_packs.ensure_pack_frames(
            str(video_path), pack, source_map, str(work_dir), entities
        )
        frames_packs.export_review_clips(
            str(video_path), pack, source_map, str(work_dir), entities
        )
        result = render_pack(
            str(work_dir), pack, chosen, mode=mode, style_name=style
        )
        produced[pack_id] = sorted(result["produced"].values())

    contact_sheet = _write_contact_sheet(work_dir, produced)
    result_summary = {
        "ok": True,
        "work_dir": str(work_dir),
        "promoted_manifest": str(promoted_path),
        "video": str(video_path),
        "ready_packs": ready_ids,
        "produced": produced,
        "contact_sheet": str(contact_sheet) if contact_sheet else None,
        "quality_report": summary.get("report_path"),
    }
    (work_dir / "render_v4_report.json").write_text(
        json.dumps(result_summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result_summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="qcard-render-v4",
        description="strict V3-to-V4 high-clarity quote-card renderer",
    )
    parser.add_argument("work_dir")
    parser.add_argument("--mode", choices=("pair", "inline", "all"), default="all")
    parser.add_argument("--style", default="editorial")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="do not download a missing source_video.mp4",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    try:
        work_dir = _resolve_work_dir(args.work_dir)
        result = render_work_dir(work_dir, args.mode, args.style, args.offline)
    except (ValueError, RuntimeError, EditorialOverflowError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("V4 render complete:")
        for pack_id, paths in result["produced"].items():
            print(f"  {pack_id}")
            for path in paths:
                print(f"    {path}")
        print(f"report: {Path(result['work_dir']) / 'render_v4_report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
