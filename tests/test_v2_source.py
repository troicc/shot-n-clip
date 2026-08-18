"""V2 tests — source authenticity (spec §十七.1-5) + editorial_cases."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from qcard.source_integrity import (SourceMap, find_spans,
                                    spans_are_contiguous, display_en_diff,
                                    build_source_map)
from tests.editorial_cases import cases as C

ROOT = os.path.join(os.path.dirname(__file__), "..")


@pytest.fixture
def sm():
    return SourceMap(video_id="t", source_language="en", caption_kind="auto",
                     segments=C.SEGMENTS, entities=[],
                     warnings=[])


# 1. exact_source_text locatable
def test_exact_text_locatable(sm):
    spans, err = find_spans(sm, "The fascinated people leave big footprints.")
    assert err is None and spans[0]["segment_id"] == "s000001"


def test_exact_text_locatable_across_adjacent(sm):
    spans, err = find_spans(sm, "Fascination comes with the mechanism. "
                                "When you're fascinated, you study automagically.")
    assert err is None
    assert spans[0]["segment_id"] == "s000005"


def test_exact_text_not_found(sm):
    spans, err = find_spans(sm, "This sentence was never spoken.")
    assert spans == [] and "NOT FOUND" in err


# 2. non-contiguous stitching fails
def test_span_stitching_fails(sm):
    ok, err = spans_are_contiguous(sm, C.CASE_STITCHING["spans"])
    assert not ok and "stitching" in err


def test_adjacent_spans_ok(sm):
    ok, err = spans_are_contiguous(sm, [
        {"segment_id": "s000001", "start_sec": 10.0, "end_sec": 12.5},
        {"segment_id": "s000002", "start_sec": 12.6, "end_sec": 14.0},
    ])
    assert ok


# 3. display_en semantic replacement fails
def test_display_en_paraphrase_fails():
    case = C.CASE_DISPLAY_EN_PARAPHRASE
    violations, ok = display_en_diff(case["exact_source_text"],
                                     case["display_en"], case["edits"])
    assert not ok
    assert any("unexplained" in v for v in violations)


def test_display_en_allowed_cleanup_passes():
    exact = "and, um, you should follow your fascination."
    display = "You should follow your fascination."
    edits = [{"operation": "remove_filler", "from": "and, um,",
              "to": ""},
             {"operation": "capitalization", "from": "you", "to": "You"},
             {"operation": "punctuation", "from": "fascination.",
              "to": "fascination."}]
    violations, ok = display_en_diff(exact, display, edits)
    assert ok, violations


def test_display_en_explained_deletions_pass():
    exact = "so so choose one hard thing before noon"
    display = "Choose one hard thing before noon."
    edits = [{"operation": "remove_immediate_false_start", "from": "so so",
              "to": ""},
             {"operation": "capitalization", "from": "choose", "to": "Choose"}]
    violations, ok = display_en_diff(exact, display, edits)
    assert ok, violations


# 4. ASR-suspicion → review queue path
def test_asr_suspicion_flags_review():
    from qcard.context_builder import evidence_pack_for_quote, needs_audio_check
    sm2 = SourceMap(video_id="t", source_language="en", caption_kind="auto",
                    segments=C.SEGMENTS, entities=[], warnings=[])
    ev = evidence_pack_for_quote(sm2, "I took a 90 percent pay cut.")
    assert ev["suspected_asr_issues"], "digits should raise suspicion"
    assert needs_audio_check(ev, auto_captions=True)
    assert not needs_audio_check(ev, auto_captions=False)


# 5. timestamps out of bounds fail (pack_validation level covered in v1;
# here verify build_source_map keeps segment order + normalized text)
def test_build_source_map_normalizes(tmp_path):
    tdir = tmp_path / "transcript"
    tdir.mkdir()
    raw = [{"text": "Hello, World!", "start": 1.0, "duration": 2.0},
           {"text": "你好，世界。", "start": 3.5, "duration": 1.5}]
    meta = {"videoId": "vid123", "title": "t", "channel": "c",
            "duration": 10, "url": "u",
            "language": {"code": "en", "name": "English", "isGenerated": True},
            "chapters": []}
    (tdir / "transcript-raw.json").write_text(json.dumps(raw), encoding="utf-8")
    (tdir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    sm = build_source_map(str(tdir))
    assert sm.caption_kind == "auto"
    assert sm.segments[0]["normalized_text"] == "helloworld"
    assert sm.segments[0]["segment_id"] == "s000000"
    assert sm.segments[1]["normalized_text"] == "你好世界"


# schema_lite sanity
def test_schema_lite_validates_source_map():
    from qcard.schema_lite import validate_file
    data = {"schema_version": "2.0", "video_id": "t",
            "source_language": "en", "caption_kind": "auto",
            "segments": [{"segment_id": "s000001", "start_sec": 1,
                          "end_sec": 2, "raw_text": "x",
                          "normalized_text": "x"}],
            "entities": [], "warnings": []}
    errs = validate_file(data, os.path.join(ROOT, "schemas", "v2",
                                            "source-map.schema.json"))
    assert errs == [], errs
    data["schema_version"] = "1.0"
    errs = validate_file(data, os.path.join(ROOT, "schemas", "v2",
                                            "source-map.schema.json"))
    assert errs and "must equal" in errs[0]
