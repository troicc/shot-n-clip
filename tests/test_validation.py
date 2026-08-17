"""Validation tests: selection parsing, source_text matching, time bounds,
duplicates, missing fields, non-ASCII, no-opencv path."""

import json
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from qcard.validate import validate_work_dir, similarity  # noqa: E402
from qcard.transcript import find_source_text, load_raw_snippets  # noqa: E402
from qcard.utils import normalize_text  # noqa: E402
from tests.fixtures.make_fixture_video import build_work_fixture  # noqa: E402


@pytest.fixture(scope="module")
def base_work(tmp_path_factory):
    work = tmp_path_factory.mktemp("work")
    build_work_fixture(str(work))
    return str(work)


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def load_selection(work):
    with open(os.path.join(work, "selection.json"), encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# 1. valid selection passes
# ---------------------------------------------------------------------------


def test_valid_selection_passes(base_work):
    errors, warnings, sel = validate_work_dir(base_work)
    assert errors == [], errors
    assert len(sel.quotes) == 6


# ---------------------------------------------------------------------------
# 2. missing fields produce field-level errors
# ---------------------------------------------------------------------------


def test_missing_fields_reported(base_work, tmp_path):
    work = str(tmp_path / "w")
    shutil.copytree(base_work, work)
    data = load_selection(work)
    del data["quotes"][2]["source_text"]
    del data["angle"]["title_zh"]
    write_json(os.path.join(work, "selection.json"), data)
    errors, _, _ = validate_work_dir(work)
    joined = "\n".join(errors)
    assert "quotes[2]: missing required field 'source_text'" in joined
    assert "angle: field 'title_zh' must be non-empty" in joined


# ---------------------------------------------------------------------------
# 3. source_text not in transcript => hard failure
# ---------------------------------------------------------------------------


def test_source_text_not_found_fails(base_work, tmp_path):
    work = str(tmp_path / "w")
    shutil.copytree(base_work, work)
    data = load_selection(work)
    data["quotes"][0]["source_text"] = "this sentence was never spoken on camera"
    write_json(os.path.join(work, "selection.json"), data)
    errors, _, _ = validate_work_dir(work)
    assert any("source_text NOT FOUND" in e for e in errors), errors


def test_source_text_normalized_match_across_snippets():
    """Case/punct differences still match; windowed across consecutive snippets."""
    snippets = load_raw_snippets(os.path.join(os.path.dirname(__file__), "fixtures"))
    # Build directly from fixture data.
    from tests.fixtures.make_fixture_video import RAW_SNIPPETS
    from qcard.transcript import Snippet
    snips = [Snippet(**s) for s in RAW_SNIPPETS]
    hit = find_source_text(snips, "Most people wake up and check their phone!")
    assert hit is not None and abs(hit[0] - 6.8) < 0.1
    # Cross-snippet phrase.
    hit2 = find_source_text(snips, "protect your attention and that means saying no")
    assert hit2 is not None and hit2[0] < 5.0 and hit2[1] > 6.0
    assert find_source_text(snips, "totally absent text") is None


def test_normalize_text_folds_punct_and_case():
    assert normalize_text("Hello, World!") == normalize_text("hello   world")
    assert normalize_text("你好，世界。") == normalize_text("你好世界")


# ---------------------------------------------------------------------------
# 4. timestamps out of range
# ---------------------------------------------------------------------------


def test_timestamp_out_of_duration_fails(base_work, tmp_path):
    work = str(tmp_path / "w")
    shutil.copytree(base_work, work)
    data = load_selection(work)
    data["quotes"][1]["start_sec"] = 99.0
    data["quotes"][1]["end_sec"] = 101.0
    write_json(os.path.join(work, "selection.json"), data)
    errors, _, _ = validate_work_dir(work)
    assert any("outside video duration" in e for e in errors), errors


def test_end_before_start_fails(base_work, tmp_path):
    work = str(tmp_path / "w")
    shutil.copytree(base_work, work)
    data = load_selection(work)
    data["quotes"][1]["end_sec"] = data["quotes"][1]["start_sec"] - 1
    write_json(os.path.join(work, "selection.json"), data)
    errors, _, _ = validate_work_dir(work)
    assert any("end_sec" in e for e in errors), errors


# ---------------------------------------------------------------------------
# 5. duplicates rejected
# ---------------------------------------------------------------------------


def test_duplicate_quotes_rejected(base_work, tmp_path):
    work = str(tmp_path / "w")
    shutil.copytree(base_work, work)
    data = load_selection(work)
    data["quotes"][3]["source_text"] = data["quotes"][2]["source_text"]
    write_json(os.path.join(work, "selection.json"), data)
    errors, _, _ = validate_work_dir(work)
    assert any("duplicate" in e for e in errors), errors


def test_similarity_detector():
    assert similarity("you must protect your attention deeply",
                      "you must protect your attention now") > 0.6
    assert similarity("choose one hard thing before noon",
                      "the moon is made of cheese entirely") < 0.2


# ---------------------------------------------------------------------------
# 6. wrong angle reference / count
# ---------------------------------------------------------------------------


def test_unknown_angle_fails(base_work, tmp_path):
    work = str(tmp_path / "w")
    shutil.copytree(base_work, work)
    data = load_selection(work)
    data["angle"]["id"] = "angle-99"
    write_json(os.path.join(work, "selection.json"), data)
    errors, _, _ = validate_work_dir(work)
    assert any("not found in angles.json" in e for e in errors), errors


def test_too_few_quotes_fails(base_work, tmp_path):
    work = str(tmp_path / "w")
    shutil.copytree(base_work, work)
    data = load_selection(work)
    data["quotes"] = data["quotes"][:2]
    write_json(os.path.join(work, "selection.json"), data)
    errors, _, _ = validate_work_dir(work)
    assert any("expected 4-8" in e for e in errors), errors


# ---------------------------------------------------------------------------
# 7. non-ASCII title/path handled
# ---------------------------------------------------------------------------


def test_non_ascii_workdir_and_title(base_work, tmp_path):
    work = str(tmp_path / "工作目录-非ASCII")
    shutil.copytree(base_work, work)
    errors, _, sel = validate_work_dir(work)
    assert errors == [], errors
    assert "非 ASCII" in sel.video_title
