from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image, JpegImagePlugin

from qcard.editorial_quality_v3.candidate import validate_candidate_pool
from qcard.editorial_quality_v3.density import source_density_flags
from qcard.editorial_quality_v3.selection import validate_selection_audit
from qcard.editorial_quality_v3.translation import validate_translation_audit
from qcard.promote_selection import promote
from qcard.render_editorial import (
    normalize_zh_typography,
    render_pack,
    resolve_editorial_fonts,
)


def _candidate(
    cid: str,
    source: str,
    claim: str,
    topics: list[str],
    start: float,
) -> dict:
    return {
        "candidate_id": cid,
        "segment_ids": [f"s{int(start):06d}"],
        "start_sec": start,
        "end_sec": start + 4.0,
        "exact_source_text": source,
        "context_before": "Complete local context before the quote.",
        "context_after": "Complete local context after the quote.",
        "standalone_status": "independent",
        "context_dependency_flags": source_density_flags(source),
        "claim_signature": claim,
        "new_information": claim,
        "topic_terms": topics,
        "evidence_type": "claim",
        "scores": {
            "standalone": 9,
            "specificity": 8,
            "information_gain": 8,
            "source_confidence": 9,
            "compression": 8,
        },
        "verdict": "pass",
        "rejection_reasons": [],
    }


def test_claim_plus_long_anecdote_is_not_one_card_unit():
    source = (
        "Passion doesn't invoke work. You could be passionate about the "
        "Cincinnati Reds and sit in a chair for 3.5 hours, drinking beer."
    )
    assert "thesis_plus_example_overload" in source_density_flags(source)


def test_fact_stack_is_rejected_before_translation():
    source = (
        "In 2023, Gallup asked how many people were engaged at work. "
        "Only 23 percent said yes. A full 59 percent were called quiet quitters."
    )
    flags = source_density_flags(source)
    assert "too_many_numeric_facts" in flags
    assert "multi_sentence_paragraph" in flags


def test_candidate_pool_rejects_dense_passing_source():
    source = (
        "Passion doesn't invoke work. You could be passionate about the "
        "Cincinnati Reds and sit in a chair for 3.5 hours, drinking beer."
    )
    item = _candidate("c001", source, "passion can remain passive", ["passion"], 0)
    report, _ = validate_candidate_pool(
        {"schema_version": "3.0", "candidates": [item]}
    )
    assert any("thesis_plus_example_overload" in error for error in report.errors)


def test_single_theme_chronological_pack_can_pass():
    candidates = [
        _candidate("c001", "Fascination is an output, not an input.", "fascination follows interest", ["fascination"], 0),
        _candidate("c002", "Passive passion does not create action.", "passion can stay passive", ["passion", "fascination"], 55),
        _candidate("c003", "Fascination makes people keep studying.", "fascination sustains study", ["fascination", "learning"], 105),
        _candidate("c004", "Studying what fascinates you gives you energy.", "fascinated learning restores energy", ["fascination", "learning"], 155),
    ]
    selection = {
        "schema_version": "3.0",
        "packs": [{
            "pack_id": "pack-01",
            "status": "ready",
            "core_claim": "Fascination sustains self-propelled learning",
            "focus_question": "What makes learning continue without external pressure?",
            "anchor_terms": ["fascination", "learning"],
            "reader_value": "Distinguishes fascination from passive enthusiasm",
            "selected": [
                {"candidate_id": "c001", "role": "hook", "support": "direct", "incremental_value": "reverses cause and result"},
                {"candidate_id": "c002", "role": "problem", "support": "direct", "incremental_value": "separates passive enthusiasm from action"},
                {"candidate_id": "c003", "role": "mechanism", "support": "direct", "incremental_value": "explains self-propelled study"},
                {"candidate_id": "c004", "role": "close", "support": "direct", "incremental_value": "adds the energy consequence"},
            ],
            "selection_review": {"verdict": "pass", "issues": []},
            "rejection_reason": None,
        }],
    }
    report, _ = validate_selection_audit(selection, {c["candidate_id"]: c for c in candidates})
    assert report.errors == [], report.errors


def test_topic_collage_and_wide_gap_are_rejected():
    candidates = [
        _candidate("c001", "Gallup measured engagement at work.", "work engagement survey", ["engagement"], 0),
        _candidate("c002", "Students begin a resume arms race in sixth grade.", "school resume competition", ["school"], 80),
        _candidate("c003", "Many schools require an early major choice.", "early major choice", ["school", "career"], 220),
        _candidate("c004", "LLMs can speed up learning or replace it.", "llms change learning", ["LLM", "learning"], 500),
    ]
    selection = {
        "schema_version": "3.0",
        "packs": [{
            "pack_id": "pack-01",
            "status": "ready",
            "core_claim": "Learning and work choices are changing",
            "focus_question": "Why are work and learning changing?",
            "anchor_terms": ["learning"],
            "reader_value": "A broad summary",
            "selected": [
                {"candidate_id": "c001", "role": "hook", "support": "direct", "incremental_value": "survey"},
                {"candidate_id": "c002", "role": "problem", "support": "direct", "incremental_value": "school pressure"},
                {"candidate_id": "c003", "role": "evidence", "support": "direct", "incremental_value": "early choice"},
                {"candidate_id": "c004", "role": "close", "support": "direct", "incremental_value": "llm split"},
            ],
            "selection_review": {"verdict": "pass", "issues": []},
        }],
    }
    report, _ = validate_selection_audit(selection, {c["candidate_id"]: c for c in candidates})
    assert any("matches none" in error for error in report.errors)
    assert any("source locality failure" in error for error in report.errors)


def _translation_pack(zh: str, compact: str, en: str) -> tuple[dict, dict]:
    pack = {
        "quotes": [{
            "quote_id": "q01",
            "order": 1,
            "role": "hook",
            "exact_source_text": en,
            "display_en": en,
            "recommended_zh": zh,
            "compact_zh": compact,
            "review": {"verdict": "pass", "issues": []},
        }]
    }
    audit = {
        "schema_version": "3.0",
        "pack_id": "pack-01",
        "quotes": [{
            "quote_id": "q01",
            "candidate_id": "c001",
            "source_claim_units": [{
                "source": en,
                "meaning_zh": zh,
                "required": True,
                "status": "preserved",
            }],
            "back_translation_en": en,
            "fidelity_ledger": {
                "additions": [], "omissions": [],
                "strengthenings": [], "weakenings": [],
            },
            "naturalness_checks": {
                "native_without_source": True,
                "read_aloud": True,
                "collocation": True,
                "no_translationese": True,
                "no_slogan_clipping": True,
            },
            "review_verdict": "pass",
            "issues": [],
        }],
    }
    return pack, audit


def test_translation_gate_rejects_paragraph_visual_load():
    zh = "2023年，Gallup调查了工作投入度，只有23%的人回答是，另有59%的人被归入静默辞职者。"
    pack, audit = _translation_pack(
        zh,
        "Gallup调查显示，多数人并未真正投入工作。",
        "Gallup measured engagement; 23 percent said yes and 59 percent were quiet quitters.",
    )
    report = validate_translation_audit(audit, pack)
    assert any("visual load" in error for error in report.errors)


def test_chinese_typography_cleanup():
    raw = '2023 年 ， 有 23 % 的人说 ： " 是 " 。 他们坐了 3.5 小时 。'
    cleaned = normalize_zh_typography(raw)
    assert "2023年" in cleaned
    assert "23%" in cleaned
    assert "3.5小时" in cleaned
    assert " ，" not in cleaned and " ：" not in cleaned
    assert "“" in cleaned and "”" in cleaned


def test_high_clarity_renderer_outputs_1440x1920_and_444_jpeg(tmp_path: Path):
    cjk, latin = resolve_editorial_fonts()
    assert "light" not in cjk.name.lower()
    assert "thin" not in cjk.name.lower()

    frame_dir = tmp_path / "frames"
    frame_dir.mkdir()
    chosen = {}
    quotes = []
    source_lines = [
        "Fascination is an output, not an input.",
        "Passive passion does not create action.",
        "Fascination makes people keep studying.",
        "Studying what fascinates you gives you energy.",
    ]
    zh_lines = [
        "持续学习更像着迷后的结果。",
        "光有热情，并不会让人真正动起来。",
        "一旦真的着迷，你会不由自主地钻下去。",
        "钻研真正感兴趣的东西，反而会让人恢复精力。",
    ]
    for index, (source, zh) in enumerate(zip(source_lines, zh_lines), 1):
        qid = f"q{index:02d}"
        frame = Image.new("RGB", (1280, 720), (30 + index * 25, 45, 85 + index * 20))
        path = frame_dir / f"{qid}.jpg"
        frame.save(path)
        chosen[qid] = str(path)
        quotes.append({
            "quote_id": qid,
            "order": index,
            "display_en": source,
            "exact_source_text": source,
            "recommended_zh": zh,
            "compact_zh": zh,
        })

    pack = {"pack": {"pack_id": "pack-01"}, "quotes": quotes}
    result = render_pack(str(tmp_path), pack, chosen, mode="all")
    outputs = result["produced"]
    for name in ("01_zh.png", "02_en.png", "03_bilingual.png"):
        image = Image.open(outputs[name])
        assert image.size == (1440, 1920)
    bilingual_report = result["layout_report"]["modes"]["bilingual"]
    for detail in bilingual_report.values():
        assert detail["zh"]["font_size"] >= 50
        assert detail["en"]["font_size"] >= 30
        assert len(detail["zh"]["lines"]) <= 2
        assert len(detail["en"]["lines"]) <= 2
    jpg = Image.open(outputs["03_bilingual.jpg"])
    assert JpegImagePlugin.get_sampling(jpg) == 0  # 4:4:4, not chroma-blurred 4:2:0


def test_promote_uses_reviewed_selection_not_stale_angles(tmp_path: Path):
    source = {
        "video_id": "abcdefghijk",
        "segments": [],
    }
    candidates = [
        _candidate("c001", "Fascination is an output.", "fascination follows interest", ["fascination"], 0),
        _candidate("c002", "Fascination differs from passive passion.", "fascination differs from passive passion", ["fascination"], 50),
        _candidate("c003", "Fascination sustains deliberate study over time.", "fascination sustains deliberate study", ["fascination"], 100),
        _candidate("c004", "It restores energy over time.", "fascination restores energy", ["fascination"], 150),
    ]
    # Avoid context-opening rejection in this unit: the source in c004 is made complete.
    candidates[-1]["exact_source_text"] = "Fascinated study restores energy over time."
    candidates[-1]["context_dependency_flags"] = []
    selection = {
        "schema_version": "3.0",
        "video_id": "abcdefghijk",
        "packs": [{
            "pack_id": "pack-01",
            "status": "ready",
            "core_claim": "Fascination sustains learning",
            "focus_question": "What sustains learning?",
            "anchor_terms": ["fascination"],
            "reader_value": "Explains sustained study",
            "selected": [
                {"candidate_id": "c001", "role": "hook", "support": "direct", "incremental_value": "reversal"},
                {"candidate_id": "c002", "role": "problem", "support": "direct", "incremental_value": "contrast"},
                {"candidate_id": "c003", "role": "mechanism", "support": "direct", "incremental_value": "mechanism"},
                {"candidate_id": "c004", "role": "close", "support": "direct", "incremental_value": "consequence"},
            ],
            "selection_review": {"verdict": "pass", "issues": []},
        }],
    }
    (tmp_path / "source_map.json").write_text(json.dumps(source), encoding="utf-8")
    (tmp_path / "candidate_pool.json").write_text(
        json.dumps({"schema_version": "3.0", "candidates": candidates}), encoding="utf-8"
    )
    (tmp_path / "selection_audit.json").write_text(json.dumps(selection), encoding="utf-8")
    (tmp_path / "angle_packs.json").write_text(
        json.dumps({"schema_version": "2.0", "video_id": "abcdefghijk", "packs": []}),
        encoding="utf-8",
    )
    path = promote(tmp_path)
    promoted = json.loads(path.read_text(encoding="utf-8"))
    assert promoted["packs"][0]["status"] == "ready"
    assert promoted["packs"][0]["quote_roles"] == ["hook", "problem", "mechanism", "close"]
