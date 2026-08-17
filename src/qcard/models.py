"""Data model for angles.json / selection.json plus JSON (de)serialization."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

SELECTION_SCHEMA_VERSION = "1.0"

SCORE_FIELDS = [
    "standalone_clarity",      # /20
    "specificity_novelty",     # /20
    "emotional_tension",       # /15
    "actionability",           # /15
    "memorability",            # /15
    "translation_compactness", # /10
    "source_fidelity",         # /5
]
SCORE_MAX = {
    "standalone_clarity": 20,
    "specificity_novelty": 20,
    "emotional_tension": 15,
    "actionability": 15,
    "memorability": 15,
    "translation_compactness": 10,
    "source_fidelity": 5,
}


@dataclass
class Score:
    standalone_clarity: int = 0
    specificity_novelty: int = 0
    emotional_tension: int = 0
    actionability: int = 0
    memorability: int = 0
    translation_compactness: int = 0
    source_fidelity: int = 0

    def total(self) -> int:
        return sum(getattr(self, f) for f in SCORE_FIELDS)


@dataclass
class Quote:
    id: str
    order: int
    start_sec: float
    end_sec: float
    source_text: str
    display_en: str
    display_zh: str
    speaker: Optional[str] = None
    frame_time_sec: Optional[float] = None
    selection_reason: str = ""
    scores: Score = field(default_factory=Score)

    def validate(self, errors: List[str], idx: int) -> None:
        tag = f"quotes[{idx}] ({self.id})"


        for name, val in [("start_sec", self.start_sec), ("end_sec", self.end_sec)]:
            if not isinstance(val, (int, float)) or isinstance(val, bool):
                errors.append(f"{tag}: {name} must be a number, got {val!r}")
        if isinstance(self.start_sec, (int, float)) and isinstance(self.end_sec, (int, float)):
            if self.end_sec <= self.start_sec:
                errors.append(f"{tag}: end_sec ({self.end_sec}) must be > start_sec ({self.start_sec})")
            if self.start_sec < 0:
                errors.append(f"{tag}: start_sec must be >= 0")
        for name in ("source_text", "display_en", "display_zh"):
            val = getattr(self, name)
            if not isinstance(val, str) or not val.strip():
                errors.append(f"{tag}: {name} must be a non-empty string")
        if self.frame_time_sec is not None:
            if not isinstance(self.frame_time_sec, (int, float)) or isinstance(self.frame_time_sec, bool):
                errors.append(f"{tag}: frame_time_sec must be a number or null")
        # Score bounds.
        for f in SCORE_FIELDS:
            v = getattr(self.scores, f)
            if not isinstance(v, int) or v < 0 or v > SCORE_MAX[f]:
                errors.append(f"{tag}: scores.{f}={v!r} must be an int in [0, {SCORE_MAX[f]}]")


@dataclass
class Angle:
    id: str
    title_zh: str
    title_en: str
    one_sentence_promise: str
    target_reader: str


@dataclass
class Selection:
    schema_version: str
    video_id: str
    source_url: str
    video_title: str
    channel: str
    source_language: str
    angle: Angle
    quotes: List[Quote]

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "video_id": self.video_id,
            "source_url": self.source_url,
            "video_title": self.video_title,
            "channel": self.channel,
            "source_language": self.source_language,
            "angle": {
                "id": self.angle.id,
                "title_zh": self.angle.title_zh,
                "title_en": self.angle.title_en,
                "one_sentence_promise": self.angle.one_sentence_promise,
                "target_reader": self.angle.target_reader,
            },
            "quotes": [
                {
                    "id": q.id,
                    "order": q.order,
                    "start_sec": q.start_sec,
                    "end_sec": q.end_sec,
                    "source_text": q.source_text,
                    "display_en": q.display_en,
                    "display_zh": q.display_zh,
                    "speaker": q.speaker,
                    "frame_time_sec": q.frame_time_sec,
                    "selection_reason": q.selection_reason,
                    "scores": {f: getattr(q.scores, f) for f in SCORE_FIELDS},
                }
                for q in self.quotes
            ],
        }

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # Parsing with field-level errors
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: Any, errors: List[str]) -> "Selection":
        def need(key: str, parent: str) -> Any:
            if not isinstance(data, dict) or key not in data:
                errors.append(f"{parent}: missing required field '{key}'")
                return None
            return data[key]

        schema = need("schema_version", "selection")
        video_id = need("video_id", "selection")
        source_url = need("source_url", "selection")
        video_title = need("video_title", "selection")
        channel = need("channel", "selection")
        source_language = need("source_language", "selection")

        angle_raw = need("angle", "selection")
        angle = Angle(id="", title_zh="", title_en="", one_sentence_promise="", target_reader="")
        if isinstance(angle_raw, dict):
            angle = Angle(
                id=str(angle_raw.get("id", "")),
                title_zh=str(angle_raw.get("title_zh", "")),
                title_en=str(angle_raw.get("title_en", "")),
                one_sentence_promise=str(angle_raw.get("one_sentence_promise", "")),
                target_reader=str(angle_raw.get("target_reader", "")),
            )
            for k in ("id", "title_zh", "one_sentence_promise"):
                if not getattr(angle, k if k != "title_zh" else "title_zh"):
                    errors.append(f"angle: field '{k}' must be non-empty")
        else:
            errors.append("angle: must be an object")

        quotes_raw = need("quotes", "selection")
        quotes: List[Quote] = []
        if isinstance(quotes_raw, list):
            for i, qr in enumerate(quotes_raw):
                if not isinstance(qr, dict):
                    errors.append(f"quotes[{i}]: must be an object")
                    continue
                missing = [k for k in
                           ("id", "order", "start_sec", "end_sec",
                            "source_text", "display_en", "display_zh") if k not in qr]
                for k in missing:
                    errors.append(f"quotes[{i}]: missing required field '{k}'")
                if missing:
                    continue
                scores_raw = qr.get("scores", {}) or {}
                scores = Score()
                for f in SCORE_FIELDS:
                    setattr(scores, f, scores_raw.get(f, 0))
                q = Quote(
                    id=str(qr["id"]),
                    order=qr["order"],
                    start_sec=qr["start_sec"],
                    end_sec=qr["end_sec"],
                    source_text=str(qr["source_text"]),
                    display_en=str(qr["display_en"]),
                    display_zh=str(qr["display_zh"]),
                    speaker=qr.get("speaker"),
                    frame_time_sec=qr.get("frame_time_sec"),
                    selection_reason=str(qr.get("selection_reason", "")),
                    scores=scores,
                )
                q.validate(errors, i)
                quotes.append(q)
        else:
            errors.append("quotes: must be an array")

        return cls(
            schema_version=str(schema or ""),
            video_id=str(video_id or ""),
            source_url=str(source_url or ""),
            video_title=str(video_title or ""),
            channel=str(channel or ""),
            source_language=str(source_language or ""),
            angle=angle,
            quotes=quotes,
        )

    @classmethod
    def load(cls, path: str, errors: List[str]) -> "Selection":
        import os
        if not os.path.exists(path):
            errors.append(f"selection.json not found at {path}")
            return cls("", "", "", "", "", "", Angle("", "", "", "", ""), [])
        with open(path, encoding="utf-8") as fh:
            try:
                data = json.load(fh)
            except json.JSONDecodeError as exc:
                errors.append(f"selection.json is not valid JSON: {exc}")
                return cls("", "", "", "", "", "", Angle("", "", "", "", ""), [])
        return cls.from_dict(data, errors)


@dataclass
class CandidateAngle:
    """One candidate angle in angles.json (3 entries)."""

    id: str
    title_zh: str
    title_en: str
    one_sentence_promise: str
    target_reader: str
    why_now: str
    candidate_quote_ids: List[str]
    novelty_score: int
    coherence_score: int
    platform_fit_score: int
    risk_notes: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title_zh": self.title_zh,
            "title_en": self.title_en,
            "one_sentence_promise": self.one_sentence_promise,
            "target_reader": self.target_reader,
            "why_now": self.why_now,
            "candidate_quote_ids": self.candidate_quote_ids,
            "novelty_score": self.novelty_score,
            "coherence_score": self.coherence_score,
            "platform_fit_score": self.platform_fit_score,
            "risk_notes": self.risk_notes,
        }


def load_angles(path: str, errors: List[str]) -> List[CandidateAngle]:
    import os
    if not os.path.exists(path):
        errors.append(f"angles.json not found at {path}")
        return []
    with open(path, encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError as exc:
            errors.append(f"angles.json is not valid JSON: {exc}")
            return []
    if not isinstance(data, dict) or not isinstance(data.get("angles"), list):
        errors.append("angles.json must be an object with an 'angles' array")
        return []
    out: List[CandidateAngle] = []
    for i, a in enumerate(data["angles"]):
        if not isinstance(a, dict):
            errors.append(f"angles[{i}]: must be an object")
            continue
        for k in ("id", "title_zh", "one_sentence_promise", "target_reader", "why_now"):
            if not str(a.get(k, "")).strip():
                errors.append(f"angles[{i}]: field '{k}' must be non-empty")
        out.append(CandidateAngle(
            id=str(a.get("id", "")),
            title_zh=str(a.get("title_zh", "")),
            title_en=str(a.get("title_en", "")),
            one_sentence_promise=str(a.get("one_sentence_promise", "")),
            target_reader=str(a.get("target_reader", "")),
            why_now=str(a.get("why_now", "")),
            candidate_quote_ids=[str(x) for x in (a.get("candidate_quote_ids") or [])],
            novelty_score=int(a.get("novelty_score", 0)),
            coherence_score=int(a.get("coherence_score", 0)),
            platform_fit_score=int(a.get("platform_fit_score", 0)),
            risk_notes=str(a.get("risk_notes", "")),
        ))
    if len(out) < 3:
        errors.append(f"angles.json must contain at least 3 angles, found {len(out)}")
    return out
