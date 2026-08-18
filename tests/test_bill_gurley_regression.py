"""Regression cases from the supplied Bill Gurley TED acceptance video."""

from qcard.editorial_quality_v3 import awkward_zh_flags, detect_context_dependency


def test_naked_23_percent_answer_is_not_publishable():
    assert "bare_yes_no_statistic" in detect_context_dependency(
        "Only 23 percent said yes."
    )


def test_unresolved_those_fragment_is_not_publishable():
    assert "unresolved_opening_reference" in detect_context_dependency(
        "Those that use LLMs to skip learning altogether."
    )


def test_success_is_not_injected_into_input_output_claim():
    source = (
        "Obsessive and continuous learning is not an input — it's an output. "
        "It's not the cause, it's the effect."
    )
    flags = awkward_zh_flags(source, "持续学习不是成功的原因，是结果。")
    assert "unsupported_success_concept" in flags
    assert "dropped_obsessive_anchor" in flags
    assert "lost_input_output_contrast" in flags


def test_artisan_identity_and_maybe_modality_survive():
    source = (
        "Maybe, for these fascinated artisans, AI is a jetpack. "
        "They learn faster, they soar higher."
    )
    flags = awkward_zh_flags(
        source, "对这些着迷的人，AI 是喷气背包：学得更快，飞得更高。"
    )
    assert "dropped_artisan_anchor" in flags
    assert "dropped_maybe_modality" in flags


def test_slogan_clipping_is_rejected():
    assert "zero_effort_calque" in awkward_zh_flags(
        "The learning comes for free. Zero conscious effort.",
        "学习自己会发生，零刻意努力。",
    )
