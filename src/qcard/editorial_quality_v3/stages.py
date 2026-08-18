"""Work-directory preparation and stage orchestration."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .candidate import validate_candidate_pool
from .common import SCHEMA_VERSION, Report, _read_json
from .selection import validate_selection_audit
from .translation import (validate_pack_binding, validate_translation_audit,
                          _pack_quote_index)

def _resolve_work_dir(raw: str) -> Path:
    path = Path(raw).expanduser()
    if path.exists():
        return path.resolve()
    project_root = Path(__file__).resolve().parents[3]
    candidate = project_root / "work" / raw
    if candidate.exists():
        return candidate.resolve()
    raise ValueError(f"work directory not found: {raw}")


def prepare_inputs(
    work_dir: Path, chunk_chars: int = 18_000, force: bool = False,
    overlap_segments: int = 3,
) -> Report:
    report = Report()
    source_path = work_dir / "source_map.json"
    try:
        source = _read_json(source_path)
    except ValueError as exc:
        report.error(str(exc))
        return report
    segments = source.get("segments") if isinstance(source, dict) else None
    if not isinstance(segments, list) or not segments:
        report.error(f"{source_path}: segments must be a non-empty array")
        return report

    out_root = work_dir / "editorial_inputs"
    chunks_dir = out_root / "chunks"
    if out_root.exists() and not force:
        report.error(
            f"{out_root} already exists; use --force only when you intentionally want to rebuild inputs"
        )
        return report
    if out_root.exists() and force:
        import shutil
        shutil.rmtree(out_root)
    chunks_dir.mkdir(parents=True, exist_ok=True)

    chunks: List[List[dict]] = []
    current: List[dict] = []
    size = 0
    for segment in segments:
        text = str(segment.get("raw_text", ""))
        if current and size + len(text) > chunk_chars:
            chunks.append(current)
            current, size = [], 0
        current.append(segment)
        size += len(text)
    if current:
        chunks.append(current)

    manifest_chunks = []
    for idx, chunk in enumerate(chunks, start=1):
        previous_tail = chunks[idx - 2][-overlap_segments:] if idx > 1 and overlap_segments else []
        next_head = chunks[idx][:overlap_segments] if idx < len(chunks) and overlap_segments else []
        visible = previous_tail + chunk + next_head
        primary_ids = {str(seg.get("segment_id")) for seg in chunk}
        path = chunks_dir / f"chunk-{idx:04d}.md"
        lines = [
            f"# Transcript chunk {idx}/{len(chunks)}",
            "",
            "Mine candidates only from exact contiguous source text. Preserve segment IDs and timestamps.",
            "Segments marked PRIMARY belong to this chunk. OVERLAP segments exist only to complete boundary context.",
            "Assign a candidate to this chunk only when its midpoint falls inside PRIMARY; this prevents duplicates.",
            "A bare answer, isolated number, setup line, or unresolved pronoun is not publishable unless the contiguous quote itself includes the missing setup.",
            "",
        ]
        for segment in visible:
            marker = "PRIMARY" if str(segment.get("segment_id")) in primary_ids else "OVERLAP"
            lines.append(
                f"[{marker} | {segment.get('segment_id')} | "
                f"{float(segment.get('start_sec', 0)):.3f}-"
                f"{float(segment.get('end_sec', 0)):.3f}] {segment.get('raw_text', '')}"
            )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        manifest_chunks.append(
            {
                "index": idx,
                "path": str(path.relative_to(work_dir)),
                "first_segment_id": chunk[0].get("segment_id"),
                "last_segment_id": chunk[-1].get("segment_id"),
                "start_sec": chunk[0].get("start_sec"),
                "end_sec": chunk[-1].get("end_sec"),
                "segment_count": len(chunk),
                "overlap_before": len(previous_tail),
                "overlap_after": len(next_head),
            }
        )

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "video_id": source.get("video_id"),
        "caption_kind": source.get("caption_kind"),
        "source_language": source.get("source_language"),
        "chunk_chars": chunk_chars,
        "overlap_segments": overlap_segments,
        "chunks": manifest_chunks,
        "next_stage": "run quote-candidate-miner once per chunk, merge into candidate_pool.json, then run selection-reviewer",
    }
    (out_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report.warn(
        f"prepared {len(chunks)} chunk(s) under {chunks_dir}; semantic agents still need to produce the audit JSON files"
    )
    return report



def validate_candidate_stage(work_dir: Path) -> Tuple[Report, Dict[str, Any]]:
    report = Report()
    summary: Dict[str, Any] = {"work_dir": str(work_dir), "stage": "candidates"}
    try:
        source_data = _read_json(work_dir / "source_map.json")
        candidate_data = _read_json(work_dir / "candidate_pool.json")
    except ValueError as exc:
        report.error(str(exc))
        summary.update(report.to_dict())
        return report, summary
    stage_report, index = validate_candidate_pool(candidate_data, source_data)
    report.merge(stage_report, "candidate_pool")
    summary.update(report.to_dict())
    summary["candidate_count"] = len(index)
    summary["pass_count"] = sum(1 for item in index.values() if item.get("verdict") == "pass")
    return report, summary


def validate_selection_stage(work_dir: Path) -> Tuple[Report, Dict[str, Any]]:
    report, summary = validate_candidate_stage(work_dir)
    summary["stage"] = "selection"
    try:
        candidate_data = _read_json(work_dir / "candidate_pool.json")
        selection_data = _read_json(work_dir / "selection_audit.json")
    except ValueError as exc:
        report.error(str(exc))
        summary.update(report.to_dict())
        return report, summary
    _, candidate_index = validate_candidate_pool(candidate_data)
    selection_report, selection_index = validate_selection_audit(selection_data, candidate_index)
    report.merge(selection_report, "selection_audit")
    summary.update(report.to_dict())
    summary["pack_count"] = len(selection_index)
    summary["ready_count"] = sum(
        1 for item in selection_index.values() if item.get("status") == "ready"
    )
    return report, summary


def validate_translation_stage(
    work_dir: Path, pack_id: str
) -> Tuple[Report, Dict[str, Any]]:
    report, summary = validate_selection_stage(work_dir)
    summary["stage"] = "translation"
    summary["pack_id"] = pack_id
    try:
        candidate_data = _read_json(work_dir / "candidate_pool.json")
        selection_data = _read_json(work_dir / "selection_audit.json")
        pack = _read_json(work_dir / "packs" / pack_id / "editorial_pack.json")
        audit = _read_json(work_dir / "packs" / pack_id / "translation_audit.json")
    except ValueError as exc:
        report.error(str(exc))
        summary.update(report.to_dict())
        return report, summary
    _, candidate_index = validate_candidate_pool(candidate_data)
    _, selection_index = validate_selection_audit(selection_data, candidate_index)
    selected_pack = selection_index.get(pack_id)
    if selected_pack is None:
        report.error(f"selection_audit has no pack {pack_id!r}")
    else:
        report.merge(validate_translation_audit(audit, pack), f"{pack_id}.translation")
        report.merge(
            validate_pack_binding(pack, selected_pack, candidate_index, audit),
            f"{pack_id}.binding",
        )
    summary.update(report.to_dict())
    return report, summary

def validate_work_dir(work_dir: Path, strict: bool = False) -> Tuple[Report, Dict[str, Any]]:
    report = Report()
    summary: Dict[str, Any] = {"work_dir": str(work_dir), "packs": {}}
    try:
        source_data = _read_json(work_dir / "source_map.json")
        candidate_data = _read_json(work_dir / "candidate_pool.json")
        selection_data = _read_json(work_dir / "selection_audit.json")
    except ValueError as exc:
        report.error(str(exc))
        return report, summary

    candidate_report, candidate_index = validate_candidate_pool(candidate_data, source_data)
    report.merge(candidate_report, "candidate_pool")
    selection_report, selection_index = validate_selection_audit(
        selection_data, candidate_index
    )
    report.merge(selection_report, "selection_audit")

    ready_count = 0
    for pid, selection_pack in selection_index.items():
        status = selection_pack.get("status")
        summary["packs"][pid] = {"status": status, "ok": False}
        if status != "ready":
            continue
        ready_count += 1
        pack_root = work_dir / "packs" / pid
        pack_path = pack_root / "editorial_pack.json"
        audit_path = pack_root / "translation_audit.json"
        try:
            pack = _read_json(pack_path)
            audit = _read_json(audit_path)
        except ValueError as exc:
            report.error(f"{pid}: {exc}")
            continue

        per_pack = Report()
        per_pack.merge(validate_translation_audit(audit, pack), "translation")
        per_pack.merge(
            validate_pack_binding(pack, selection_pack, candidate_index, audit),
            "binding",
        )
        # Existing V2 review must also be green; V3 does not replace source/entity checks.
        for qid, quote in _pack_quote_index(pack).items():
            review = quote.get("review")
            if not isinstance(review, dict) or review.get("verdict") != "pass":
                per_pack.error(f"{qid}: existing editorial review.verdict must be 'pass'")
            if review and review.get("issues"):
                per_pack.error(f"{qid}: existing editorial review still has issues")

        if strict:
            for name in ("publish_xhs.json", "publish_wechat.json"):
                if not (pack_root / name).exists():
                    per_pack.error(f"missing {name} for ready pack")

        report.merge(per_pack, pid)
        summary["packs"][pid]["ok"] = per_pack.ok
        summary["packs"][pid]["errors"] = per_pack.errors
        summary["packs"][pid]["warnings"] = per_pack.warnings

    if strict and ready_count == 0:
        report.error("strict mode requires at least one ready pack")
    summary["ready_count"] = ready_count
    summary["ok"] = report.ok
    summary["errors"] = report.errors
    summary["warnings"] = report.warnings
    report_path = work_dir / "editorial_quality_report.json"
    report_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    summary["report_path"] = str(report_path)
    return report, summary
