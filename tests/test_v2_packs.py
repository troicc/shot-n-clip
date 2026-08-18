"""V2 tests — multi-pack rules (spec §十七.16-20) + editorial pack schema."""

import copy
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from qcard import pack_validation as pv
from qcard.source_integrity import SourceMap
from tests.editorial_cases import cases as C

ROOT = os.path.join(os.path.dirname(__file__), "..")
CONFIG = os.path.join(ROOT, "config")


@pytest.fixture
def sm():
    return SourceMap(video_id="t", source_language="en", caption_kind="auto",
                     segments=C.SEGMENTS, entities=[], warnings=[])


def _span(seg_id, s, e):
    return {"segment_id": seg_id, "start_sec": s, "end_sec": e}


def _quote(qid, order, role, seg, text, zh="中文示例句子。"):
    return {
        "quote_id": qid, "order": order, "role": role,
        "source_spans": [seg],
        "exact_source_text": text,
        "context_before": "", "context_after": "",
        "display_en": text, "display_en_edits": [],
        "semantic_brief": {"claim": "一个完整的命题描述", "rhetorical_function": role,
                           "tone": "克制", "modality": "absolute",
                           "resolved_references": {}},
        "faithful_zh": zh,
        "zh_candidates": [
            {"id": "a", "style": "faithful-natural", "text": zh},
            {"id": "b", "style": "spoken-compact", "text": zh},
            {"id": "c", "style": "memorable-restrained", "text": zh},
        ],
        "recommended_zh": zh, "compact_zh": zh,
        "entity_ids": [], "frame_time_sec": None,
        "review": {"fidelity_score": 9.5, "naturalness_score": 9.0,
                   "source_confidence": 9.0, "ai_tone_risk": 1.0,
                   "entity_integrity": "pass",
                   "modality_integrity": "pass", "verdict": "pass",
                   "issues": []},
    }


def _pack(quotes, pid="pack-01"):
    return {"schema_version": "2.0",
            "pack": {"pack_id": pid, "slug": "test-pack",
                     "core_claim": "一个用于测试的具体主张" + pid[-2:],
                     "reader_value": "读者得到的具体收益" + pid[-2:]},
            "quotes": quotes}


# 16. source span reuse across ready packs fails
def test_span_reuse_across_ready_packs_fails():
    spans_a = [_span("s000001", 10.0, 12.5), _span("s000002", 12.6, 14.0),
               _span("s000005", 104.2, 107.0), _span("s000007", 150.0, 153.0)]
    spans_b = [_span("s000001", 10.0, 12.5),  # reused from pack-01
               _span("s000003", 40.0, 42.0), _span("s000004", 100.0, 104.0),
               _span("s000008", 153.2, 156.0)]
    angle = {"schema_version": "2.0", "video_id": "t", "packs": [
        {"pack_id": "pack-01", "slug": "a", "title_zh_internal": "角度一的主题",
         "core_claim": "着迷驱动持续学习，这是结果而非输入",
         "reader_value": "帮助读者识别自己的能量来源",
         "quote_roles": ["hook", "problem", "mechanism", "evidence", "close"],
         "supporting_source_spans": spans_a,
         "coherence_score": 9, "novelty_score": 8,
         "evidence_density_score": 9, "platform_fit_score": 8,
         "overlap_with_other_packs": {}, "status": "ready",
         "rejection_reason": None},
        {"pack_id": "pack-02", "slug": "b", "title_zh_internal": "角度二的主题",
         "core_claim": "转行需要大幅降薪换取入场券的代价结构",
         "reader_value": "帮助读者评估转行成本",
         "quote_roles": ["hook", "problem", "evidence", "method", "close"],
         "supporting_source_spans": spans_b,
         "coherence_score": 8, "novelty_score": 7,
         "evidence_density_score": 8, "platform_fit_score": 7,
         "overlap_with_other_packs": {}, "status": "ready",
         "rejection_reason": None},
    ]}
    res = pv.validate_pack_set(angle)
    assert any("reused" in e for e in res.errors), res.errors


# 17. duplicate core claims fail
def test_duplicate_core_claims_fail():
    spans_a = [_span("s000001", 10.0, 12.5), _span("s000002", 12.6, 14.0),
               _span("s000005", 104.2, 107.0), _span("s000007", 150.0, 153.0)]
    spans_b = [_span("s000003", 40.0, 42.0), _span("s000004", 100.0, 104.0),
               _span("s000006", 107.2, 110.0), _span("s000008", 153.2, 156.0)]
    base = {"pack_id": "pack-01", "slug": "a", "title_zh_internal": "角度一主题",
            "core_claim": "持续而痴迷的学习是热情驱动的结果",
            "reader_value": "帮助读者识别能量来源",
            "quote_roles": ["hook", "problem", "mechanism", "evidence", "close"],
            "supporting_source_spans": spans_a,
            "coherence_score": 9, "novelty_score": 8,
            "evidence_density_score": 9, "platform_fit_score": 8,
            "overlap_with_other_packs": {}, "status": "ready",
            "rejection_reason": None}
    dup = dict(base, pack_id="pack-02", slug="b", title_zh_internal="角度二主题",
               core_claim="持续而痴迷的学习是热情驱动的结果",
               supporting_source_spans=spans_b)
    res = pv.validate_pack_set({"schema_version": "2.0", "video_id": "t",
                                "packs": [base, dup]})
    assert any("duplicates" in e or "similar" in e for e in res.errors), \
        res.errors


# 18. insufficient evidence spans fails (schema level)
def test_insufficient_spans_fails_schema():
    angle = {"schema_version": "2.0", "video_id": "t", "packs": [{
        "pack_id": "pack-01", "slug": "a", "title_zh_internal": "角度主题",
        "core_claim": "某个具体的可发布主张内容", "reader_value": "具体收益",
        "quote_roles": ["hook", "close"],
        "supporting_source_spans": [_span("s000001", 10.0, 12.5)],
        "coherence_score": 5, "novelty_score": 5,
        "evidence_density_score": 5, "platform_fit_score": 5,
        "overlap_with_other_packs": {}, "status": "candidate",
        "rejection_reason": None}]}
    res = pv.validate_pack_set(angle)
    assert res.errors


# 19. rejected pack must not render
def test_rejected_pack_not_rendered(tmp_path, sm, monkeypatch):
    from qcard import cli
    work = tmp_path / "w"
    (work / "packs" / "pack-01").mkdir(parents=True)
    (work / "packs" / "pack-02").mkdir(parents=True)
    (work / "transcript").mkdir()
    # minimal transcript for source map
    raw = [{"text": s["raw_text"], "start": s["start_sec"],
            "duration": s["end_sec"] - s["start_sec"]} for s in C.SEGMENTS]
    (work / "transcript" / "transcript-raw.json").write_text(
        json.dumps(raw), encoding="utf-8")
    (work / "transcript" / "meta.json").write_text(json.dumps({
        "videoId": "t", "title": "x", "channel": "c", "duration": 160,
        "url": "u", "language": {"code": "en", "name": "English",
                                 "isGenerated": True}, "chapters": []}),
        encoding="utf-8")
    import argparse
    cli.cmd_source_map(argparse.Namespace(work_dir=str(work)))

    good = _pack([
        _quote("q01", 1, "hook", _span("s000001", 10.0, 12.5),
               C.SEGMENTS[0]["raw_text"]),
        _quote("q02", 2, "problem", _span("s000002", 12.6, 14.0),
               C.SEGMENTS[1]["raw_text"]),
        _quote("q03", 3, "mechanism", _span("s000005", 104.2, 107.0),
               C.SEGMENTS[4]["raw_text"]),
        _quote("q04", 4, "close", _span("s000007", 150.0, 153.0),
               C.SEGMENTS[6]["raw_text"], zh="我接受了降薪 90%。"),
    ], "pack-01")
    (work / "packs" / "pack-01" / "editorial_pack.json").write_text(
        json.dumps(good, ensure_ascii=False), encoding="utf-8")

    angle = {"schema_version": "2.0", "video_id": "t", "packs": [
        {"pack_id": "pack-01", "slug": "a", "title_zh_internal": "角度",
         "core_claim": "着迷驱动学习的具体机制主张", "reader_value": "具体收益",
         "quote_roles": ["hook", "problem", "mechanism", "evidence", "close"],
         "supporting_source_spans": [_span("s000001", 10.0, 12.5),
                                     _span("s000002", 12.6, 14.0),
                                     _span("s000005", 104.2, 107.0),
                                     _span("s000007", 150.0, 153.0)],
         "coherence_score": 9, "novelty_score": 8,
         "evidence_density_score": 9, "platform_fit_score": 8,
         "overlap_with_other_packs": {}, "status": "ready",
         "rejection_reason": None},
        {"pack_id": "pack-02", "slug": "b", "title_zh_internal": "弱角度",
         "core_claim": "另一个不同的具体主张内容示例",
         "reader_value": "另一种具体收益说明",
         "quote_roles": ["hook", "problem", "evidence", "method", "close"],
         "supporting_source_spans": [_span("s000003", 40.0, 42.0),
                                     _span("s000004", 100.0, 104.0),
                                     _span("s000006", 107.2, 110.0),
                                     _span("s000008", 153.2, 156.0)],
         "coherence_score": 4, "novelty_score": 3,
         "evidence_density_score": 4, "platform_fit_score": 3,
         "overlap_with_other_packs": {}, "status": "rejected",
         "rejection_reason": "quotes don't progress; evidence thin"},
    ]}
    (work / "angle_packs.json").write_text(json.dumps(angle, ensure_ascii=False),
                                            encoding="utf-8")

    # render-packs with ready_only skips pack-02
    calls = {}
    import qcard.frames_packs as fp
    import qcard.render_packs as rp

    rendered_ids = []

    def fake_frames(video, pack, sm_, wd, ents=None):
        rendered_ids.append(pack["pack"]["pack_id"])
        return {q["quote_id"]: "" for q in pack["quotes"]}

    def fake_render(wd, pack, cfg, chosen, mode, **kw):
        return {"produced": {}, "layout_report": {}, "fit_ok": {},
                "out_dir": str(wd)}

    monkeypatch.setattr(fp, "ensure_pack_frames", fake_frames)
    monkeypatch.setattr(fp, "export_review_clips", lambda *a, **k: [])
    monkeypatch.setattr(rp, "render_pack", fake_render)
    (work / "source_video.mp4").write_bytes(b"0" * 20000)

    rc = cli.cmd_render_packs(argparse.Namespace(
        work_dir=str(work), ready_only=True, mode="all", style="classic"))
    assert rc == 0
    assert rendered_ids == ["pack-01"], "rejected pack must not render"
    rq = (work / "review_queue.md").read_text(encoding="utf-8")
    assert "Review Queue" in rq


# 20. one video manages multiple pack dirs (structure)
def test_multiple_pack_dirs_managed(tmp_path):
    from qcard.migration_v2 import migrate
    work = tmp_path / "w"
    (work / "transcript").mkdir(parents=True)
    # a minimal V1 selection.json to migrate
    (work / "selection.json").write_text(json.dumps({
        "schema_version": "1.0", "video_id": "t",
        "source_url": "https://x", "video_title": "x", "channel": "c",
        "source_language": "en",
        "angle": {"id": "angle-01", "title_zh": "主题", "title_en": "t",
                  "one_sentence_promise": "承诺", "target_reader": "读者"},
        "quotes": [
            {"id": "q01", "order": 1, "start_sec": 10.0, "end_sec": 12.5,
             "source_text": C.SEGMENTS[0]["raw_text"],
             "display_en": C.SEGMENTS[0]["raw_text"],
             "display_zh": "示例中文。", "speaker": None,
             "frame_time_sec": None, "selection_reason": "hook",
             "scores": {}},
            {"id": "q02", "order": 2, "start_sec": 100.0, "end_sec": 107.0,
             "source_text": C.SEGMENTS[4]["raw_text"],
             "display_en": C.SEGMENTS[4]["raw_text"],
             "display_zh": "示例中文二。", "speaker": None,
             "frame_time_sec": None, "selection_reason": "insight",
             "scores": {}},
        ]}, ensure_ascii=False), encoding="utf-8")
    raw = [{"text": s["raw_text"], "start": s["start_sec"],
            "duration": s["end_sec"] - s["start_sec"]} for s in C.SEGMENTS]
    (work / "transcript" / "transcript-raw.json").write_text(
        json.dumps(raw), encoding="utf-8")
    (work / "transcript" / "meta.json").write_text(json.dumps({
        "videoId": "t", "title": "x", "channel": "c", "duration": 160,
        "url": "u", "language": {"code": "en", "name": "English",
                                 "isGenerated": False}, "chapters": []}),
        encoding="utf-8")
    sm = SourceMap(video_id="t", source_language="en", caption_kind="manual",
                   segments=C.SEGMENTS, entities=[], warnings=[])
    out = migrate(str(work), sm)
    assert os.path.exists(out)
    assert os.path.exists(str(work) + "/selection.json.v1.bak")
    pack = json.loads(open(out, encoding="utf-8").read())
    assert pack["pack"]["pack_id"] == "pack-00"
    # migrated reviews are manual_review, never fake-pass
    for q in pack["quotes"]:
        assert q["review"]["verdict"] == "manual_review"
        assert q["review"]["entity_integrity"] == "fail"


# editorial pack schema + validator integration
def test_valid_editorial_pack_passes(sm):
    pack = _pack([
        _quote("q01", 1, "hook", _span("s000001", 10.0, 12.5),
               C.SEGMENTS[0]["raw_text"]),
        _quote("q02", 2, "problem", _span("s000002", 12.6, 14.0),
               C.SEGMENTS[1]["raw_text"]),
        _quote("q03", 3, "mechanism", _span("s000005", 104.2, 107.0),
               C.SEGMENTS[4]["raw_text"]),
        _quote("q04", 4, "close", _span("s000007", 150.0, 153.0),
               C.SEGMENTS[6]["raw_text"], zh="我接受了降薪 90%。"),
    ])
    res = pv.validate_editorial_pack(pack, sm, [], CONFIG)
    assert not [e for e in res.errors], res.errors


def test_pack_with_unlocatable_quote_fails(sm):
    pack = _pack([
        _quote("q01", 1, "hook", _span("s000001", 10.0, 12.5), "real text"),
        _quote("q02", 2, "problem", _span("s000002", 12.6, 14.0),
               "totally invented sentence"),
        _quote("q03", 3, "mechanism", _span("s000005", 104.2, 107.0),
               C.SEGMENTS[4]["raw_text"]),
        _quote("q04", 4, "close", _span("s000007", 150.0, 153.0),
               C.SEGMENTS[6]["raw_text"], zh="我接受了降薪 90%。"),
    ])
    res = pv.validate_editorial_pack(pack, sm, [], CONFIG)
    assert any("NOT FOUND" in e for e in res.errors)


def test_pack_with_stitched_span_fails(sm):
    bad = _quote("q01", 1, "hook",
                 {"segment_id": "s000001", "start_sec": 10.0, "end_sec": 42.0},
                 "The fascinated people leave big footprints. "
                 "A completely different part of the talk.")
    pack = _pack([bad] + [
        _quote("q02", 2, "problem", _span("s000002", 12.6, 14.0),
               C.SEGMENTS[1]["raw_text"]),
        _quote("q03", 3, "mechanism", _span("s000005", 104.2, 107.0),
               C.SEGMENTS[4]["raw_text"]),
        _quote("q04", 4, "close", _span("s000007", 150.0, 153.0),
               C.SEGMENTS[6]["raw_text"], zh="我接受了降薪 90%。"),
    ])
    res = pv.validate_editorial_pack(pack, sm, [], CONFIG)
    assert any("NOT FOUND" in e for e in res.errors)


def test_30s_window_density_fails(sm):
    # q01/q02/q03 all within 15s of each other (10-14s, 100-110s … craft it)
    pack = _pack([
        _quote("q01", 1, "hook", _span("s000005", 104.2, 107.0),
               C.SEGMENTS[4]["raw_text"]),
        _quote("q02", 2, "problem",
               {"segment_id": "s000006", "start_sec": 107.2, "end_sec": 110.0},
               C.SEGMENTS[5]["raw_text"]),
        _quote("q03", 3, "mechanism", _span("s000002", 12.6, 14.0),
               C.SEGMENTS[1]["raw_text"]),
        _quote("q04", 4, "close", _span("s000007", 150.0, 153.0),
               C.SEGMENTS[6]["raw_text"]),
    ])
    # s000005 and s000006 centers ~107.85/108.6 → within ±15s → 2 allowed,
    # add a third in-window one:
    pack["quotes"][2]["source_spans"] = [
        {"segment_id": "s000005", "start_sec": 104.2, "end_sec": 107.0}]
    pack["quotes"][2]["exact_source_text"] = C.SEGMENTS[4]["raw_text"]
    res = pv.validate_editorial_pack(pack, sm, [], CONFIG)
    assert any("30s" in e or "±15s" in e for e in res.errors)


def test_review_verdict_gate(sm):
    pack = _pack([
        _quote("q01", 1, "hook", _span("s000001", 10.0, 12.5),
               C.SEGMENTS[0]["raw_text"]),
        _quote("q02", 2, "problem", _span("s000002", 12.6, 14.0),
               C.SEGMENTS[1]["raw_text"]),
        _quote("q03", 3, "mechanism", _span("s000005", 104.2, 107.0),
               C.SEGMENTS[4]["raw_text"]),
        _quote("q04", 4, "close", _span("s000007", 150.0, 153.0),
               C.SEGMENTS[6]["raw_text"], zh="我接受了降薪 90%。"),
    ])
    pack["quotes"][0]["review"]["verdict"] = "revise"
    res = pv.validate_editorial_pack(pack, sm, [], CONFIG)
    assert any("verdict" in e for e in res.errors)
