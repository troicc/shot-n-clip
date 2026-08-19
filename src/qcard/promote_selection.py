"""Promote a validated V3 selection audit into the V2 render manifest.

The renderer historically consumes angle_packs.json.  This bridge prevents a
stale V2 angle file from bypassing the independently reviewed V3 selection.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

from .editorial_quality_v3.candidate import validate_candidate_pool
from .editorial_quality_v3.selection import validate_selection_audit


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing required file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc


def _slug(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return slug or fallback


def promote(work_dir: Path) -> Path:
    source = _read(work_dir / "source_map.json")
    candidates = _read(work_dir / "candidate_pool.json")
    selection = _read(work_dir / "selection_audit.json")

    candidate_report, candidate_index = validate_candidate_pool(candidates, source)
    selection_report, _ = validate_selection_audit(selection, candidate_index)
    errors = candidate_report.errors + selection_report.errors
    if errors:
        raise ValueError(
            "selection cannot be promoted because V3 validation failed:\n- "
            + "\n- ".join(errors)
        )

    packs: List[Dict[str, Any]] = []
    for pack in selection.get("packs", []):
        pid = str(pack.get("pack_id"))
        selected = pack.get("selected") or []
        spans = []
        roles = []
        for item in selected:
            candidate = candidate_index[str(item["candidate_id"])]
            roles.append(item["role"])
            segment_ids = candidate.get("segment_ids") or [item["candidate_id"]]
            spans.append({
                "segment_id": str(segment_ids[0]),
                "start_sec": float(candidate["start_sec"]),
                "end_sec": float(candidate["end_sec"]),
                "note": f"V3 candidate {item['candidate_id']}",
            })
        core = str(pack.get("core_claim") or "V3 reviewed quote pack")
        reader_value = str(pack.get("reader_value") or core)
        status = str(pack.get("status") or "candidate")
        packs.append({
            "pack_id": pid,
            "slug": _slug(str(pack.get("slug") or pid), pid),
            "title_zh_internal": str(pack.get("title_zh_internal") or core)[:80],
            "core_claim": core,
            "reader_value": reader_value,
            "quote_roles": roles,
            "supporting_source_spans": spans,
            "coherence_score": 9 if status == "ready" else 0,
            "novelty_score": 8 if status == "ready" else 0,
            "evidence_density_score": 9 if status == "ready" else 0,
            "platform_fit_score": 9 if status == "ready" else 0,
            "overlap_with_other_packs": {
                "generated_from": "selection_audit.json",
                "anchor_terms": pack.get("anchor_terms", []),
            },
            "status": status,
            "rejection_reason": pack.get("rejection_reason"),
        })

    if not any(pack["status"] == "ready" for pack in packs):
        raise ValueError("selection_audit has no ready pack to promote")

    output = {
        "schema_version": "2.0",
        "video_id": str(selection.get("video_id") or source.get("video_id") or work_dir.name),
        "packs": packs,
    }
    path = work_dir / "angle_packs.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="qcard-promote",
        description="Promote a validated V3 selection into angle_packs.json for rendering",
    )
    parser.add_argument("work_dir")
    args = parser.parse_args(argv)
    path = Path(args.work_dir).expanduser()
    if not path.exists():
        project = Path(__file__).resolve().parents[2]
        candidate = project / "work" / args.work_dir
        path = candidate if candidate.exists() else path
    try:
        output = promote(path.resolve())
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"promoted V3 selection → {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
