"""Entity glossary (V2 §七): lock proper nouns before any translation.

Merge order (highest wins): user overrides (entity_overrides.yaml) →
entities already in source_map → discovered from transcript/title.
Unresolved entities keep source_form and are marked needs_review; any
quote whose zh text mutates an unresolved entity meaning fails hard.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import yaml

CAP_GUESS_TYPES = {
    "person": r"\b(?:Mr|Mrs|Ms|Dr|Uncle|Aunt|President|Professor)\b",
    "organization": r"\b(?:Inc|LLC|University|College|Institute|Cafe|Corp)\b",
}


@dataclass
class Entity:
    entity_id: str
    source_form: str
    canonical_zh: Optional[str]
    type: str
    do_not_guess: bool
    evidence: List[str]
    status: str  # resolved | needs_review
    note: str = ""

    def to_dict(self) -> dict:
        d = {
            "entity_id": self.entity_id,
            "source_form": self.source_form,
            "canonical_zh": self.canonical_zh,
            "type": self.type,
            "do_not_guess": self.do_not_guess,
            "evidence": self.evidence,
            "status": self.status,
        }
        if self.note:
            d["note"] = self.note
        return d


def load_overrides(config_root: str) -> List[Entity]:
    path = os.path.join(config_root, "editorial", "entity_overrides.yaml")
    out: List[Entity] = []
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    for item in raw.get("overrides", []):
        out.append(Entity(
            entity_id=item["entity_id"],
            source_form=item["source_form"],
            canonical_zh=item.get("canonical_zh"),
            type=item.get("type", "unknown"),
            do_not_guess=item.get("do_not_guess", True),
            evidence=item.get("evidence", []),
            status=item.get("status", "needs_review"),
            note=item.get("note", ""),
        ))
    return out


# Capitalized multi-word / known-title patterns for discovery.
_DISCOVER_RE = re.compile(
    r"\b([A-Z][a-zA-Z]+(?:\s+(?:of\s+)?[A-Z][a-zA-Z]+){0,3})\b")
_STOP = {"The", "This", "That", "These", "Those", "And", "But", "So", "Well",
         "Okay", "Now", "When", "What", "Why", "How", "Maybe", "Over", "One",
         "In", "On", "At", "For", "With", "They", "There", "Then", "Here",
         "Thank", "Thanks", "First", "Second", "Last", "Next", "Back",
         "See", "Guess", "You", "Your", "We", "Our", "He", "She", "It", "I",
         "A", "An", "My", "Me", "Do", "Did", "Does", "Don", "Doesn", "Isn",
         "Was", "Were", "Are", "Am", "Be", "Been", "Being"}


def discover_from_text(texts: Dict[str, str]) -> List[Tuple[str, int]]:
    """Candidate proper nouns from {source: text} with occurrence counts."""
    counts: Dict[str, int] = {}
    for source, text in texts.items():
        for m in _DISCOVER_RE.finditer(text):
            phrase = m.group(1).strip()
            words = phrase.split()
            if words[0] in _STOP or (len(words) > 1 and words[-1] in _STOP
                                     and len(words) < 3):
                continue
            if len(phrase) < 4:
                continue
            counts[phrase] = counts.get(phrase, 0) + 1
    return sorted(counts.items(), key=lambda kv: -kv[1])


def build_glossary(source_map, config_root: str, extra_texts=None
                   ) -> List[Entity]:
    overrides = {e.source_form: e for e in load_overrides(config_root)}
    entities: List[Entity] = list(overrides.values())
    existing_forms = {e.source_form for e in entities}

    texts = {"transcript": " ".join(s["raw_text"] for s in
                                    source_map.segments[:400])}
    if extra_texts:
        texts.update(extra_texts)

    next_id = len(overrides) + 1
    for phrase, count in discover_from_text(texts):
        if phrase in existing_forms:
            continue
        if count < 2:
            continue  # singletons from ASR are noise-prone; skip silently
        eid = f"e{next_id:03d}"
        next_id += 1
        etype = _guess_type(phrase)
        entities.append(Entity(
            entity_id=eid,
            source_form=phrase,
            canonical_zh=None,          # unresolved: keep source_form
            type=etype,
            do_not_guess=True,
            evidence=[f"appears {count}× in transcript"],
            status="needs_review",
        ))
        existing_forms.add(phrase)
    return entities


def _guess_type(phrase: str) -> str:
    for typ, pattern in CAP_GUESS_TYPES.items():
        if re.search(pattern, phrase):
            return typ
    if " " in phrase:
        return "multiword_name"
    return "proper_noun"


def glossary_index(entities: List[Entity]) -> Dict[str, Entity]:
    return {e.source_form.lower(): e for e in entities}


def check_zh_entities(zh_text: str, entities: List[Entity],
                      used_entity_ids: List[str]
                      ) -> Tuple[List[str], bool]:
    """Hard checks on one quote's zh text.

    - resolved entity used → its canonical_zh (or source_form) must appear
      verbatim (verbatim substring; e.g. 'Richard 叔叔' in 'Richard 叔叔…').
    - any entity_id referenced but unresolved → blocks ready.
    """
    problems: List[str] = []
    by_id = {e.entity_id: e for e in entities}
    for eid in used_entity_ids:
        ent = by_id.get(eid)
        if ent is None:
            problems.append(f"unknown entity_id {eid}")
            continue
        if ent.status != "resolved":
            problems.append(
                f"entity {ent.source_form} ({eid}) is needs_review — "
                "cannot enter ready pack until resolved in "
                "config/editorial/entity_overrides.yaml")
            continue
        expected = ent.canonical_zh or ent.source_form
        if expected not in zh_text:
            problems.append(
                f"zh text must contain locked form {expected!r} for entity "
                f"{ent.source_form!r} — free translation of proper nouns is "
                "forbidden")
    return problems, not problems


def unresolved_entities(entities: List[Entity],
                        used_ids: List[str]) -> List[Entity]:
    by_id = {e.entity_id: e for e in entities}
    return [by_id[i] for i in used_ids if i in by_id
            and by_id[i].status != "resolved"]


def extract_entity_ids(exact_text: str, entities: List[Entity]) -> List[str]:
    ids = []
    for e in entities:
        if e.source_form.lower() in exact_text.lower():
            ids.append(e.entity_id)
    return ids


# Structured numeric facts -----------------------------------------------

_NUM_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(percent|%|billion|million|thousand|dollars|years?|"
    r"times|hours?|minutes?|locations|percent said)", re.I)


def numeric_facts(text: str) -> List[str]:
    return [m.group(0).strip() for m in _NUM_RE.finditer(text)]


def facts_match(source_facts: List[str], zh_text: str) -> List[str]:
    """Every number in source must appear in zh (as digits) — no silent
    unit/value drift. Returns mismatches."""
    missing = []
    for fact in source_facts:
        num = re.match(r"(\d+(?:\.\d+)?)", fact).group(1)
        if num not in zh_text:
            missing.append(f"number {num} (from '{fact}') missing in zh text")
    return missing
