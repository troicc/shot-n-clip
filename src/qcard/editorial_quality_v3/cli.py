"""Command-line interface for qcard-quality."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional, Sequence

from .common import Report
from .stages import (_resolve_work_dir, prepare_inputs, validate_candidate_stage,
                     validate_selection_stage, validate_translation_stage,
                     validate_work_dir)

def _print_report(report: Report) -> None:
    for warning in report.warnings:
        print(f"[WARN] {warning}")
    for error in report.errors:
        print(f"[ERROR] {error}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="qcard-quality",
        description="V3 deterministic editorial quality gate (no LLM API calls)",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare", help="chunk source_map for candidate mining")
    prepare.add_argument("work_dir")
    prepare.add_argument("--chunk-chars", type=int, default=18_000)
    prepare.add_argument("--force", action="store_true")
    prepare.add_argument("--overlap-segments", type=int, default=3)

    vc = sub.add_parser("validate-candidates", help="validate candidate_pool against source_map")
    vc.add_argument("work_dir")
    vc.add_argument("--json", action="store_true", dest="as_json")

    vs = sub.add_parser("validate-selection", help="validate candidate_pool + selection_audit")
    vs.add_argument("work_dir")
    vs.add_argument("--json", action="store_true", dest="as_json")

    vt = sub.add_parser("validate-translation", help="validate one pack's translation audit and binding")
    vt.add_argument("work_dir")
    vt.add_argument("--pack", required=True)
    vt.add_argument("--json", action="store_true", dest="as_json")

    validate = sub.add_parser("validate", help="validate candidate, selection and all ready-pack translation audits")
    validate.add_argument("work_dir")
    validate.add_argument("--strict", action="store_true")
    validate.add_argument("--json", action="store_true", dest="as_json")

    args = parser.parse_args(argv)
    try:
        work_dir = _resolve_work_dir(args.work_dir)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.command == "prepare":
        if args.chunk_chars < 4_000:
            print("error: --chunk-chars must be >= 4000", file=sys.stderr)
            return 2
        if not 0 <= args.overlap_segments <= 20:
            print("error: --overlap-segments must be within 0..20", file=sys.stderr)
            return 2
        report = prepare_inputs(
            work_dir, args.chunk_chars, args.force, args.overlap_segments
        )
        _print_report(report)
        return 0 if report.ok else 1

    if args.command == "validate-candidates":
        report, summary = validate_candidate_stage(work_dir)
    elif args.command == "validate-selection":
        report, summary = validate_selection_stage(work_dir)
    elif args.command == "validate-translation":
        report, summary = validate_translation_stage(work_dir, args.pack)
    else:
        report, summary = validate_work_dir(work_dir, strict=args.strict)
    if args.as_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        _print_report(report)
        print(
            f"editorial-quality-v3: {'OK' if report.ok else 'FAILED'} "
            f"({len(report.errors)} error(s), {len(report.warnings)} warning(s))"
        )
        if summary.get("report_path"):
            print(f"report: {summary['report_path']}")
    return 0 if report.ok else 1
