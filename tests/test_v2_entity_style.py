"""V2 tests — entities, modality, chinese style (spec §十七.6-15)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from qcard import editorial_lint as lint
from qcard import entity_glossary as eg
from tests.editorial_cases import cases as C

ROOT = os.path.join(os.path.dirname(__file__), "..")
CONFIG = os.path.join(ROOT, "config")


def _entity(**kw):
    base = dict(entity_id="e003", source_form="Uncle Richard",
                canonical_zh="Richard 叔叔", type="person_or_nickname",
                do_not_guess=True, evidence=["x"], status="resolved")
    base.update(kw)
    return eg.Entity(**base)


# 6. entity hallucination fails
def test_entity_hallucination_fails():
    case = C.CASE_ENTITY_HALLUCINATION
    problems, ok = eg.check_zh_entities(case["bad_zh"], [_entity()],
                                        ["e003"])
    assert not ok and any("locked form" in p for p in problems)


def test_entity_locked_form_passes():
    case = C.CASE_ENTITY_HALLUCINATION
    problems, ok = eg.check_zh_entities(case["good_zh"], [_entity()],
                                        ["e003"])
    assert ok, problems


def test_unresolved_entity_blocks_ready():
    ent = _entity(status="needs_review", canonical_zh=None)
    problems, ok = eg.check_zh_entities("whatever", [ent], ["e003"])
    assert not ok and any("needs_review" in p for p in problems)


def test_entity_discovery_and_overrides(tmp_path):
    # overrides win; discovery adds repeated phrases as needs_review
    texts = {"transcript": "Alice met Bob twice. Alice liked the idea. "
                           "Bob from Acme Corp agreed with Alice."}
    import json
    src_map = type("SM", (), {"segments": [
        {"raw_text": texts["transcript"], "start_sec": 0, "end_sec": 5}]})()
    entities = eg.build_glossary(src_map, os.path.join(tmp_path, "noconf"),
                                 texts)
    forms = {e.source_form for e in entities}
    assert "Alice" in forms
    unresolved = [e for e in entities if e.status != "resolved"]
    assert unresolved, "discovered entities must start needs_review"


# 7. numbers consistent
def test_number_drift_detected():
    case = C.CASE_NUMBER_DRIFT
    facts = eg.numeric_facts(case["exact_source_text"])
    assert eg.facts_match(facts, case["bad_zh"])
    assert not eg.facts_match(facts, case["good_zh"])


# 8. hedge absolutization fails
def test_maybe_absolutized_fails():
    case = C.CASE_MAYBE_ABSOLUTE
    v = lint.modality_violations(case["exact_source_text"], case["bad_zh"])
    assert any("maybe" in x for x in v)
    ok = lint.modality_violations(case["exact_source_text"],
                                  case["good_zh"])
    assert ok == []


def test_negation_dropped_fails():
    v = lint.negation_violations("It's not the cause, it's the effect.",
                                 "它是原因。")
    assert v


# 9. negation/causality direction (lint layer)
def test_negation_direction():
    assert lint.negation_violations("I don't like it", "我不喜欢") == []
    assert lint.negation_violations("I don't like it", "我喜欢它")


# 11. banned clichés fail lint
@pytest.mark.parametrize("bad", [
    "这段访谈含金量太高了", "值得所有人反复看", "建议收藏这篇",
    "看完通透了", "真正的成长，是学会接受", "这段话告诉我们一个道理",
    "你一定要明白这个道理", "狠狠共鸣了",
])
def test_banned_cliche_fails(bad):
    res = lint.lint_zh([bad], CONFIG)
    assert res.failed, bad


def test_clean_text_passes():
    res = lint.lint_zh(["我接受了降薪 90%，进入这一行。"], CONFIG)
    assert not res.failed


# 12. 不是……而是…… repetition
def test_not_but_repetition_warns():
    res = lint.lint_zh(C.CASE_NOT_BUT_STACK, CONFIG)
    assert any("不是……而是" in str(h) or "not_but" in h.rule
               for h in res.hits)


def test_single_not_but_allowed():
    res = lint.lint_zh(["持续学习不是输入，而是输出。"], CONFIG)
    assert not res.failed


# 13. consecutive shape repetition
def test_ending_rhythm_flagged():
    # identical last-4 chars across 3 consecutive sentences
    texts = ["学习从来不是终点。", "着迷从来不是终点。", "热情从来不是终点。"]
    res = lint.lint_zh(texts, CONFIG)
    assert any(h.rule == "ending_rhythm" for h in res.hits)


# 14. absolutization flagged
def test_absolutes_flagged():
    res = lint.lint_zh(["所有人都该这样做"], CONFIG)
    assert any("absolute" in h.rule for h in res.hits)


# 15. long text cannot pass by shrinking (layout layer, tested in render v2)
def test_translationese_fails():
    case = C.CASE_TRANSLATIONESE
    res = lint.lint_zh([case["bad_zh"]], CONFIG)
    assert res.failed
    res2 = lint.lint_zh([case["good_zh"]], CONFIG)
    assert not res2.failed


def test_literal_metaphor_flagged():
    case = C.CASE_LITERAL_METAPHOR
    res = lint.lint_zh([case["bad_zh"]], CONFIG)
    assert res.failed
    res2 = lint.lint_zh([case["good_zh"]], CONFIG)
    assert not res2.failed


def test_abstract_stack_flagged():
    res = lint.lint_zh(["这就是认知升级和思维破局带来的格局赋能与价值沉淀"],
                       CONFIG)
    assert any(h.rule == "abstract_stack" for h in res.hits)
