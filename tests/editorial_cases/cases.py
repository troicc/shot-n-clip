"""Anonymized regression fixtures for the exact V1 defects found in audit.

Each case pins ONE defect class. Names are generic; the structures are the
real ones. Consumed by test_v2_* suites; also serves as documentation of
what "regression" means for this repo.
"""

# A tiny synthetic source map used across cases: 8 contiguous segments.
SEGMENTS = [
    {"segment_id": "s000001", "start_sec": 10.0, "end_sec": 12.5,
     "raw_text": "The fascinated people leave big footprints.",
     "normalized_text": "thefascinatedpeopleleavebigfootprints"},
    {"segment_id": "s000002", "start_sec": 12.6, "end_sec": 14.0,
     "raw_text": "Danny had Uncle Richard at that dinner.",
     "normalized_text": "dannyhadunclerichardatthatdinner"},
    {"segment_id": "s000003", "start_sec": 40.0, "end_sec": 42.0,
     "raw_text": "A completely different part of the talk.",
     "normalized_text": "acompletelydifferentpartofthetalk"},
    {"segment_id": "s000004", "start_sec": 100.0, "end_sec": 104.0,
     "raw_text": "Maybe all the world really needs more mentors.",
     "normalized_text": "maybealltheworldreallyneedsmorementors"},
    {"segment_id": "s000005", "start_sec": 104.2, "end_sec": 107.0,
     "raw_text": "Fascination comes with the mechanism.",
     "normalized_text": "fascinationcomeswiththemechanism"},
    {"segment_id": "s000006", "start_sec": 107.2, "end_sec": 110.0,
     "raw_text": "When you're fascinated, you study automagically.",
     "normalized_text": "whenyourefascinatedyoustudyautomagically"},
    {"segment_id": "s000007", "start_sec": 150.0, "end_sec": 153.0,
     "raw_text": "I took a 90 percent pay cut.",
     "normalized_text": "itooka90percentpaycut"},
    {"segment_id": "s000008", "start_sec": 153.2, "end_sec": 156.0,
     "raw_text": "It was the best trade I ever made.",
     "normalized_text": "itwasthebesttradeievermade"},
]

ENTITY_UNCLE_RICHARD = {
    "entity_id": "e003", "source_form": "Uncle Richard",
    "canonical_zh": "Richard 叔叔", "type": "person_or_nickname",
    "do_not_guess": True, "evidence": ["repeated occurrence"],
    "status": "resolved",
}

# --- defect cases -----------------------------------------------------------

# 1. V1 literal translation of "leave big footprints"
CASE_LITERAL_METAPHOR = {
    "defect": "literal_translation",
    "exact_source_text": "The fascinated people leave big footprints.",
    "bad_zh": "着迷的人，会留下很大的脚印。",
    "good_zh": "着迷的人，影响会远远超出自己。",
}

# 2. V1 entity hallucination: Uncle Richard → 一句话伯乐
CASE_ENTITY_HALLUCINATION = {
    "defect": "entity_error",
    "exact_source_text": "Danny had Uncle Richard at that dinner.",
    "bad_zh": "Danny 身边有一位一句话伯乐。",
    "good_zh": "那顿晚饭桌上有 Richard 叔叔。",
    "entity": ENTITY_UNCLE_RICHARD,
}

# 3. English word broken across lines
CASE_WORD_SPLIT = {
    "defect": "en_word_split",
    "text": "Continuous and obsessive learning throughout an entire career",
    "width": 260,  # px with a stub font → forces wraps
}

# 4. 不是……而是…… stacking
CASE_NOT_BUT_STACK = [
    "持续学习不是输入，而是输出。",
    "该追的不是热情，而是着迷。",
    "安全工作不是保险箱，而是舒适区。",
]

# 5. maybe absolutized
CASE_MAYBE_ABSOLUTE = {
    "defect": "modality_lost",
    "exact_source_text": "Maybe all the world really needs more mentors.",
    "bad_zh": "这个世界需要的就是更多的引路人。",
    "good_zh": "这个世界需要的，也许是更多的引路人。",
}

# 6. mechanism → 自带机制 translationese
CASE_TRANSLATIONESE = {
    "defect": "translationese",
    "bad_zh": "着迷自带机制。",
    "good_zh": "着迷会推着你主动去钻研。",
}

# 7. display_en paraphrase (semantic synonym replacement)
CASE_DISPLAY_EN_PARAPHRASE = {
    "defect": "display_en_paraphrase",
    "exact_source_text":
        "When you learn about something you're fascinated by, you get energy.",
    "display_en":
        "Learning what fascinates you gives it back.",   # "gives it back" invented
    "edits": [],
}

# 8. non-contiguous span stitching (gap 28s)
CASE_STITCHING = {
    "defect": "span_stitching",
    "spans": [
        {"segment_id": "s000002", "start_sec": 12.6, "end_sec": 14.0},
        {"segment_id": "s000003", "start_sec": 40.0, "end_sec": 42.0},
    ],
}

# 9. number drift
CASE_NUMBER_DRIFT = {
    "defect": "number_missing",
    "exact_source_text": "I took a 90 percent pay cut.",
    "bad_zh": "我大幅降薪进入了这一行。",
    "good_zh": "我接受了降薪 90%，进入这一行。",
}

# 10. banned copy patterns
CASE_BANNED_COPY = {
    "bad_intro": "这期访谈含金量太高了，值得所有人反复看，建议收藏！",
    "bad_title": "看完通透了！!",
}
