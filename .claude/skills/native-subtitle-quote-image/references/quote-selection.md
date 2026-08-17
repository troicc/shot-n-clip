# Quote Selection Rules

## Step 1 — three candidate angles (angles.json)

Each angle must be genuinely different (not three phrasings of one idea). Write
3 entries with all fields:

```json
{
  "angles": [
    {
      "id": "angle-01",
      "title_zh": "…",
      "title_en": "…",
      "one_sentence_promise": "读者看完这组图能得到什么（一句话）",
      "target_reader": "谁会转发它",
      "why_now": "为什么此刻成立",
      "candidate_quote_ids": ["q01", "…"],
      "novelty_score": 8,
      "coherence_score": 9,
      "platform_fit_score": 8,
      "risk_notes": "断章取义/过度承诺/需要上下文等风险，无则写'无'"
    }
  ]
}
```

Pick the angle that best satisfies, in order: clear reader benefit; tension /
contrarian take / concrete mechanism; can be carried by 5–7 real quotes in a
reading progression; not generic chicken-soup; understandable without extra
context; clearly distinct from the other two angles.

## Step 2 — quote scoring (/100)

| Dimension | Max | Deduct when… |
|---|---|---|
| standalone_clarity | 20 | needs the previous paragraph to make sense; unresolved this/that/it/he/she |
| specificity_novelty | 20 | true but information-free; pure platitude |
| emotional_tension | 15 | flat restatement of common knowledge |
| actionability | 15 | nothing a reader could do differently |
| memorability | 15 | forgettable phrasing |
| translation_compactness | 10 | too long → unreadable font size |
| source_fidelity | 5 | speaker/timing uncertain |

Additional hard deductions: heavy deictic reference (this/that/it), duplicates
an already-chosen quote, must be compressed below readability, translation
would turn hype-y.

## Step 3 — narrative order (default 6)

Hook → Problem → Insight → Evidence → Method → Close.
Not "the six highest-scoring sentences" — a single storyline under one angle.
Close must have aftertaste without being vague.

## Length targets (display text)

- display_zh: ~12–34 hanzi, max 2 rendered lines. Never more absolute/absolute-sounding than the original; may reorder clauses; may not add facts.
- display_en: ~35–95 chars, max 2 lines. Only clean disfluencies/repeats/case/punct — no semantic rewrite.
- Too long → pick a different complete short sentence. Never truncate mid-idea.

## selection.json contract

```json
{
  "schema_version": "1.0",
  "video_id": "…",
  "source_url": "https://…",
  "video_title": "…",
  "channel": "…",
  "source_language": "en",
  "angle": {
    "id": "angle-01",
    "title_zh": "…", "title_en": "…",
    "one_sentence_promise": "…", "target_reader": "…"
  },
  "quotes": [
    {
      "id": "q01",
      "order": 1,
      "start_sec": 123.4,
      "end_sec": 131.2,
      "source_text": "contiguous transcript text (verbatim)",
      "display_en": "…",
      "display_zh": "…",
      "speaker": null,
      "frame_time_sec": null,
      "selection_reason": "hook | problem | insight | evidence | method | close + why",
      "scores": { "standalone_clarity": 18, "specificity_novelty": 17,
                  "emotional_tension": 13, "actionability": 12,
                  "memorability": 14, "translation_compactness": 9,
                  "source_fidelity": 5 }
    }
  ]
}
```

Rules: start/end are numeric seconds (never formatted strings). source_text
must be locatable in the transcript after whitespace/case/punct normalization
(cross-snippet windows count). frame_time_sec null = auto-pick; a number pins
the frame. UTF-8, never escape Chinese to \uXXXX. All derived copy must
trace back to this file.
