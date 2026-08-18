"""V2 tests — copy rules (§十七.21-25) + layout (§十七.26-30)."""

import os
import sys

import pytest
from PIL import Image, ImageFont

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from qcard import copy_validation as cv
from qcard import wrap_text as wt
from qcard.schema_lite import validate as schema_validate
from qcard.pack_validation import _load_schema
from tests.editorial_cases import cases as C

ROOT = os.path.join(os.path.dirname(__file__), "..")

CJK = "/System/Library/Fonts/PingFang.ttc"
LATIN = "/System/Library/Fonts/Helvetica.ttc"
HAVE_FONTS = os.path.exists(CJK) and os.path.exists(LATIN)
pytestmark = pytest.mark.skipif(
    not HAVE_FONTS and sys.platform == "darwin",
    reason="system fonts missing")


def _pack():
    return {"pack": {"pack_id": "pack-01"},
            "quotes": [{"quote_id": "q01",
                        "exact_source_text": "I took a 90 percent pay cut."}]}


def _copy(**over):
    base = {
        "schema_version": "2.0", "platform": "xhs", "pack_id": "pack-01",
        "content_brief": {
            "core_claim": "x", "reader_value": "y",
            "key_facts": ["90 percent pay cut"],
            "misread_risk": "m", "tone": "克制"},
        "title_candidates": [
            {"text": "他降薪 90% 换了赛道", "strategy": "direct",
             "score": 8.5, "risk": []},
            {"text": "为什么他敢降薪 90%？", "strategy": "question",
             "score": 8.0, "risk": []},
            {"text": "热爱不值钱，着迷才保值", "strategy": "contrast",
             "score": 7.5, "risk": []},
            {"text": "转行前先算这笔账", "strategy": "number",
             "score": 7.0, "risk": []},
            {"text": "别用热爱骗自己", "strategy": "contrast",
             "score": 6.5, "risk": []},
            {"text": "一场饭局改写职业生涯", "strategy": "story",
             "score": 6.0, "risk": []},
        ],
        "recommended_title": "他降薪 90% 换了赛道",
        "intro_short": "降薪换入场券，这笔账他算得很清楚。",
        "intro_full": "x" * 120,
        "hashtags": ["#职业选择", "#访谈", "#金句"],
        "source_note": "来源：某访谈，链接见文案末尾，时间戳见图。",
        "review": {"naturalness_score": 9.0, "specificity_score": 8.5,
                   "ai_tone_risk": 1.0, "unsupported_claims": []},
    }
    base.update(over)
    return base


os.environ.setdefault("QCARD_CONFIG_ROOT", os.path.join(ROOT, "config"))


# 21. banned cliché in copy fails
def test_copy_banned_cliche_fails():
    copy = _copy(intro_full="这期访谈含金量太高了，" + "很具体的机制说明。" * 8)
    errs, _ = cv.validate_copy(copy, "xhs", _pack())
    assert any("banned" in e or "含金量" in e for e in errs)


# 22. unsupported claim (number not in pack) fails
def test_copy_unsupported_number_fails():
    copy = _copy(recommended_title="他靠 300 万粉丝翻盘")
    errs, _ = cv.validate_copy(copy, "xhs", _pack())
    assert any("absent from pack" in e for e in errs)


# 23. fabricated first-person fails
def test_copy_fabricated_first_person_fails():
    copy = _copy(intro_full="我亲测过这条路，" + "具体机制展开说明。" * 8)
    errs, _ = cv.validate_copy(copy, "xhs", _pack())
    assert any("first-person" in e for e in errs)


# 24. field completeness via schema
def test_copy_schema_missing_fields():
    copy = _copy()
    del copy["content_brief"]
    errs, _ = cv.validate_copy(copy, "xhs", _pack())
    assert errs


def test_wechat_fields_valid():
    copy = _copy(platform="wechat",
                 intro_full="y" * 150,
                 intro_short="z" * 70)
    copy["title_candidates"] = copy["title_candidates"][:4]
    errs, warns = cv.validate_copy(copy, "wechat", _pack())
    assert errs == [], errs


# 25. recommended exists
def test_recommended_present():
    copy = _copy()
    errs, _ = cv.validate_copy(copy, "xhs", _pack())
    assert errs == [], errs


# 26. English never breaks mid-word
@pytest.mark.skipif(not HAVE_FONTS, reason="fonts")
def test_english_no_mid_word_break():
    font = ImageFont.truetype(LATIN, 30)
    text = ("Continuous and obsessive learning is not an input — it's an "
            "output. It's not the cause, it's the effect.")
    lines = wt.wrap(text, font, 620)
    assert len(lines) <= 3
    words = {w.strip(".,—'\"") for w in text.replace("—", " ").split()}
    for ln in lines:
        toks = [t for t in ln.replace("—", " ").split() if t]
        for tok in toks:
            stripped = tok.strip(".,—'\"")
            # every rendered token must be a whole source word (punct ok)
            assert stripped in words, f"mid-word break produced {tok!r}"


@pytest.mark.skipif(not HAVE_FONTS, reason="fonts")
def test_wrap_narrow_width_never_splits_words():
    font = ImageFont.truetype(LATIN, 30)
    text = "fascination extraordinary automagically mechanisms"
    lines = wt.wrap(text, font, 150)
    for ln in lines:
        assert "fascinat" != ln[:8] or ln == "fascination"  # no partial
    # stricter: each line is composed of whole words
    src_words = set(text.split())
    for ln in lines:
        for tok in ln.split():
            assert tok in src_words


# 27. widow guard
@pytest.mark.skipif(not HAVE_FONTS, reason="fonts")
def test_widow_guard():
    font = ImageFont.truetype(LATIN, 30)
    text = ("Learning what fascinates you provides energy and the "
            "willingness to continue studying for decades")
    lines = wt.wrap(text, font, 430)
    last = lines[-1].split()
    assert not (len(last) == 1 and len(last[0]) <= 4), \
        f"widow word: {lines}"


@pytest.mark.skipif(not HAVE_FONTS, reason="fonts")
def test_zh_widow_guard():
    font = ImageFont.truetype(CJK, 44)
    text = "着迷的人会主动钻研一个领域很多年"
    lines = wt.wrap(text, font, 460)
    last = lines[-1]
    cjk_len = len([c for c in last if wt.is_cjk(c)])
    assert cjk_len >= 3 or len(lines) == 1


# 28. quote-escape residue cleaned
def test_escape_residue_cleaned():
    assert wt.clean_escapes("it&#39;s") == "it's"
    assert wt.clean_escapes("&quot;quote&quot;") == '"quote"'
    assert "&#" not in wt.clean_escapes("a&#x27;b&b&#39;c")


# 29/30 layout: pack renderer on synthetic frames
@pytest.mark.skipif(not HAVE_FONTS, reason="fonts")
def test_render_pack_outputs_and_layout_report(tmp_path):
    from qcard import render_packs
    from qcard.render import load_style
    cfg = load_style(os.path.join(ROOT, "config"), "classic")
    # synthetic frames
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    chosen = {}
    quotes = []
    seg_texts = ["One line of source text here.",
                 "Another line of source text.",
                 "Third line of the source.",
                 "Fourth line of source.",
                 "Fifth line of source text."]
    for i, t in enumerate(seg_texts, 1):
        img = Image.new("RGB", (1280, 720),
                        (30 + i * 20, 60, 120 - i * 10))
        p = frames_dir / f"q{i:02d}.jpg"
        img.save(str(p))
        chosen[f"q{i:02d}"] = str(p)
        quotes.append({
            "quote_id": f"q{i:02d}", "order": i, "role": "hook",
            "source_spans": [{"segment_id": "s1", "start_sec": 0,
                              "end_sec": 1}],
            "exact_source_text": t, "context_before": "", "context_after": "",
            "display_en": t, "display_en_edits": [],
            "semantic_brief": {}, "faithful_zh": "",
            "zh_candidates": [
                {"id": "a", "style": "faithful-natural", "text": "示例"},
                {"id": "b", "style": "spoken-compact", "text": "示例"},
                {"id": "c", "style": "memorable-restrained", "text": "示例"}],
            "recommended_zh": f"这是第{i}条中文示例句子，长度适中。",
            "compact_zh": f"第{i}条示例。",
            "entity_ids": [], "frame_time_sec": None,
            "review": {},
        })
    pack = {"schema_version": "2.0",
            "pack": {"pack_id": "pack-01", "core_claim": "测试主张" * 3,
                     "reader_value": "测试收益" * 3},
            "quotes": quotes}
    result = render_packs.render_pack(str(tmp_path), pack, cfg, chosen,
                                      "all")
    for name in ("01_zh.png", "02_en.png", "03_bilingual.png"):
        p = result["produced"][name]
        assert os.path.exists(p)
        img = Image.open(p)
        assert img.size == (1080, 1440)
    report = result["layout_report"]
    ids = {k.rsplit(":", 1)[0] for k in report}
    assert ids == {"q01", "q02", "q03", "q04", "q05"}
    for key, info in report.items():
        assert info.get("fits") is True
        if info["kind"] == "zh":
            assert info["font_size"] >= 42, (key, info)
        if info["kind"] == "en":
            assert info["font_size"] >= 28, (key, info)
    # inline defaulted to 5 quotes
    bi = Image.open(result["produced"]["03_bilingual.png"])
    assert bi.size == (1080, 1440)


@pytest.mark.skipif(not HAVE_FONTS, reason="fonts")
def test_overflow_falls_back_to_compact_then_fails(tmp_path):
    from qcard import render_packs
    from qcard.render import load_style
    cfg = load_style(os.path.join(ROOT, "config"), "classic")
    img = Image.new("RGB", (1280, 720), (80, 80, 140))
    p = str(tmp_path / "f.jpg")
    img.save(p)
    long_zh = "这是一条特别长的中文句子，" * 8
    quotes = [{
        "quote_id": "q01", "order": 1, "role": "hook",
        "source_spans": [{"segment_id": "s1", "start_sec": 0, "end_sec": 1}],
        "exact_source_text": "src", "context_before": "", "context_after": "",
        "display_en": "src", "display_en_edits": [],
        "semantic_brief": {}, "faithful_zh": "",
        "zh_candidates": [
            {"id": "a", "style": "faithful-natural", "text": long_zh},
            {"id": "b", "style": "spoken-compact", "text": long_zh},
            {"id": "c", "style": "memorable-restrained", "text": long_zh}],
        "recommended_zh": long_zh,
        "compact_zh": "短版本。",   # compact rescues
        "entity_ids": [], "frame_time_sec": None, "review": {}}]
    pack = {"schema_version": "2.0",
            "pack": {"pack_id": "pack-01", "core_claim": "x" * 10,
                     "reader_value": "y" * 10},
            "quotes": quotes}
    result = render_packs.render_pack(str(tmp_path), pack, cfg,
                                      {"q01": p}, "pair")
    zh_report = result["layout_report"]["q01:zh"]
    assert zh_report["used_compact"] is True
    assert zh_report["text"] == "短版本。"

    # both overlong → hard fail
    pack["quotes"][0]["compact_zh"] = long_zh
    with pytest.raises(render_packs.OverflowError_):
        render_packs.render_pack(str(tmp_path), pack, cfg, {"q01": p}, "pair")


# schema file sanity for publish-copy
def test_publish_copy_schema():
    data = {"schema_version": "2.0", "platform": "xhs",
            "pack_id": "pack-01",
            "content_brief": {}, "title_candidates": [],
            "recommended_title": "t", "intro_full": "x" * 50,
            "hashtags": ["#a"], "source_note": "note here",
            "review": {"naturalness_score": 1, "specificity_score": 1,
                       "ai_tone_risk": 1, "unsupported_claims": []}}
    errs = schema_validate(data, _load_schema("publish-copy.schema.json"))
    assert any("content_brief" in e for e in errs)
