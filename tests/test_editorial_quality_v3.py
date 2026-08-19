import json
from pathlib import Path

from qcard.editorial_quality_v3 import (
    awkward_zh_flags,
    detect_context_dependency,
    prepare_inputs,
    validate_candidate_pool,
    validate_selection_audit,
    validate_translation_audit,
)


def candidate(cid, text, claim, start=0.0, verdict="pass"):
    flags = detect_context_dependency(text)
    return {
        "candidate_id": cid,
        "segment_ids": [f"s{int(start):06d}"],
        "start_sec": start,
        "end_sec": start + 4,
        "exact_source_text": text,
        "context_before": "The speaker is answering a complete question.",
        "context_after": "The next sentence gives an example.",
        "standalone_status": "independent" if verdict == "pass" else "reject",
        "context_dependency_flags": flags,
        "claim_signature": claim,
        "new_information": claim,
        "evidence_type": "claim",
        "scores": {
            "standalone": 9,
            "specificity": 8,
            "information_gain": 8,
            "source_confidence": 9,
            "compression": 8,
        },
        "verdict": verdict,
        "rejection_reasons": [] if verdict == "pass" else flags,
    }


def test_bare_percentage_answer_cannot_pass():
    c = candidate("c001", "Only 23 percent said yes.", "23 percent answered yes")
    report, _ = validate_candidate_pool({"schema_version": "3.0", "candidates": [c]})
    assert any("bare_yes_no_statistic" in e for e in report.errors)


def test_known_translation_regressions():
    source = (
        "Obsessive and continuous learning is not an input — it's an output. "
        "It's not the cause, it's the effect."
    )
    flags = awkward_zh_flags(source, "持续学习不是成功的原因，是结果。")
    assert "unsupported_success_concept" in flags
    assert "dropped_obsessive_anchor" in flags
    assert "lost_input_output_contrast" in flags
    assert "automatic_study_calque" in awkward_zh_flags(
        "When you're fascinated, you study automatically.", "着迷会推着你自动去学。"
    )
    assert "zero_effort_calque" in awkward_zh_flags(
        "The learning comes for free. Zero conscious effort.",
        "学习自己会发生，零刻意努力。",
    )


def test_selection_rejects_redundant_claims():
    candidates = [
        candidate("c001", "Fascination makes you study.", "fascination drives study", 0),
        candidate("c002", "Being fascinated makes learning happen.", "fascination drives studying", 40),
        candidate("c003", "Learning disliked topics drains energy.", "disliked learning drains energy", 80),
        candidate("c004", "AI can speed up learning.", "ai accelerates learning", 120),
        candidate("c005", "People leave a deeper mark.", "fascination leaves a mark", 160),
    ]
    pool = {"schema_version": "3.0", "candidates": candidates}
    pool_report, index = validate_candidate_pool(pool)
    assert not pool_report.errors
    selection = {
        "schema_version": "3.0",
        "packs": [
            {
                "pack_id": "pack-01",
                "status": "ready",
                "core_claim": "Fascination creates self-propelled learning",
                "selected": [
                    {"candidate_id": "c001", "role": "hook", "support": "direct", "incremental_value": "states the thesis"},
                    {"candidate_id": "c002", "role": "mechanism", "support": "direct", "incremental_value": "repeats the thesis"},
                    {"candidate_id": "c003", "role": "problem", "support": "direct", "incremental_value": "shows the energy contrast"},
                    {"candidate_id": "c004", "role": "evidence", "support": "direct", "incremental_value": "adds the AI consequence"},
                    {"candidate_id": "c005", "role": "close", "support": "direct", "incremental_value": "ends with long-term impact"},
                ],
                "selection_review": {"verdict": "pass", "issues": []},
            }
        ],
    }
    report, _ = validate_selection_audit(selection, index)
    assert any("redundant" in e for e in report.errors)


def test_translation_audit_requires_empty_ledger_and_natural_checks():
    pack = {
        "quotes": [
            {
                "quote_id": "q01",
                "order": 1,
                "role": "hook",
                "exact_source_text": "Those who use LLMs to learn faster than ever, and those who use LLMs to skip learning altogether.",
                "recommended_zh": "有人用大模型把学习提速，也有人拿它直接跳过学习。",
                "compact_zh": "有人用大模型加快学习，也有人用它跳过学习。",
                "display_en": "Those who use LLMs to learn faster than ever, and those who use LLMs to skip learning altogether.",
                "review": {"verdict": "pass", "issues": []},
            }
        ]
    }
    audit = {
        "schema_version": "3.0",
        "pack_id": "pack-01",
        "quotes": [
            {
                "quote_id": "q01",
                "candidate_id": "c001",
                "source_claim_units": [
                    {"source": "use LLMs to learn faster", "meaning_zh": "用大模型加快学习", "required": True, "status": "preserved"},
                    {"source": "use LLMs to skip learning", "meaning_zh": "用大模型跳过学习", "required": True, "status": "preserved"},
                ],
                "back_translation_en": "Some use LLMs to speed up learning; others use them to skip learning.",
                "fidelity_ledger": {"additions": [], "omissions": [], "strengthenings": [], "weakenings": []},
                "naturalness_checks": {
                    "native_without_source": True,
                    "read_aloud": True,
                    "collocation": True,
                    "no_translationese": True,
                    "no_slogan_clipping": True,
                },
                "review_verdict": "pass",
                "issues": [],
            }
        ],
    }
    assert validate_translation_audit(audit, pack).ok
    audit["quotes"][0]["fidelity_ledger"]["omissions"] = ["faster than ever"]
    assert not validate_translation_audit(audit, pack).ok


def test_prepare_inputs_preserves_all_segments(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    source = {
        "video_id": "abcdefghijk",
        "caption_kind": "manual",
        "source_language": "en",
        "segments": [
            {"segment_id": "s000001", "start_sec": 0, "end_sec": 2, "raw_text": "First complete idea."},
            {"segment_id": "s000002", "start_sec": 2, "end_sec": 4, "raw_text": "Second complete idea."},
        ],
    }
    (work / "source_map.json").write_text(json.dumps(source), encoding="utf-8")
    report = prepare_inputs(work, chunk_chars=4000)
    assert report.ok
    text = (work / "editorial_inputs" / "chunks" / "chunk-0001.md").read_text()
    assert "s000001" in text and "s000002" in text


def test_candidate_must_bind_to_declared_source_segments():
    source_map = {
        "segments": [
            {
                "segment_id": "s000001",
                "start_sec": 10.0,
                "end_sec": 12.0,
                "raw_text": "A complete source-backed claim.",
            }
        ]
    }
    c = candidate("c001", "An invented claim.", "invented claim", 10)
    c["segment_ids"] = ["s000001"]
    c["start_sec"] = 10.0
    c["end_sec"] = 12.0
    report, _ = validate_candidate_pool(
        {"schema_version": "3.0", "candidates": [c]}, source_map
    )
    assert any("not contained" in error for error in report.errors)


def test_unresolved_those_fragment_cannot_pass():
    c = candidate(
        "c001",
        "Those that use LLMs to skip learning altogether.",
        "some people use LLMs to skip learning",
    )
    report, _ = validate_candidate_pool(
        {"schema_version": "3.0", "candidates": [c]}
    )
    assert any("unresolved_opening_reference" in error for error in report.errors)


def test_identity_and_modality_anchors_are_not_dropped():
    source = (
        "Maybe, for these fascinated artisans, AI is a jetpack. "
        "They learn faster and soar higher."
    )
    flags = awkward_zh_flags(source, "对这些着迷的人，AI 是喷气背包：学得更快，飞得更高。")
    assert "dropped_artisan_anchor" in flags
    assert "dropped_maybe_modality" in flags


def test_prepare_force_removes_stale_chunks(tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    source = {
        "video_id": "abcdefghijk",
        "caption_kind": "manual",
        "source_language": "en",
        "segments": [
            {"segment_id": "s000001", "start_sec": 0, "end_sec": 2, "raw_text": "First."}
        ],
    }
    (work / "source_map.json").write_text(json.dumps(source), encoding="utf-8")
    assert prepare_inputs(work, chunk_chars=4000).ok
    stale = work / "editorial_inputs" / "chunks" / "chunk-9999.md"
    stale.write_text("stale", encoding="utf-8")
    assert prepare_inputs(work, chunk_chars=4000, force=True).ok
    assert not stale.exists()
