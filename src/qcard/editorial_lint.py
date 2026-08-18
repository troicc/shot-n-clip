"""Chinese style lint (V2 §九): banned templates, repeated shapes,
absolutization, translationese, abstract-stacking, ending rhythm."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import yaml

_TRANSLATIONESE_FALLBACK = [
    r"自带机制", r"留下(很大)?的脚印", r"让我们", r"值得注意的(是)?",
    r"本质上(是)?(说)?", r"输入.?输出",
]


@dataclass
class LintHit:
    rule: str
    severity: str          # fail | warn
    pattern: str = ""
    text_excerpt: str = ""

    def __str__(self) -> str:
        loc = f" [{self.pattern}]" if self.pattern else ""
        return f"({self.severity}) {self.rule}{loc}: …{self.text_excerpt}…"


@dataclass
class LintResult:
    hits: List[LintHit] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return any(h.severity == "fail" for h in self.hits)

    @property
    def warn_count(self) -> int:
        return sum(1 for h in self.hits if h.severity == "warn")

    def ai_tone_risk(self) -> float:
        """0–10 estimate from warn/fail density in one pack."""
        fails = sum(1 for h in self.hits if h.severity == "fail")
        return min(10.0, fails * 3.0 + self.warn_count * 1.2)

    def messages(self) -> List[str]:
        return [str(h) for h in self.hits]


def load_config(config_root: str) -> dict:
    import os
    path = os.path.join(config_root, "editorial", "banned_patterns.yaml")
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def lint_zh(texts: List[str], config_root: str) -> LintResult:
    """Lint a pack's zh texts (recommended_zh list, in order)."""
    cfg = load_config(config_root)
    res = LintResult()
    _banned_patterns(texts, cfg, res)
    _not_but_repetition(texts, cfg, res)
    _translationese(texts, config_root, res)
    _absolutes(texts, cfg, res)
    _abstract_stack(texts, cfg, res)
    _ending_rhythm(texts, cfg, res)
    _judgment_ratio(texts, cfg, res)
    _punct_abuse(texts, cfg, res)
    return res


def _excerpt(texts: List[str], idx: int) -> str:
    return texts[idx][:28]


def _banned_patterns(texts, cfg, res) -> None:
    per_pack_count: Dict[str, int] = {}
    for idx, text in enumerate(texts):
        for pat in cfg.get("patterns", []):
            regex = pat["regex"]
            m = re.search(regex, text)
            if not m:
                continue
            limit = pat.get("limit_per_pack")
            if limit is not None:
                per_pack_count[pat["id"]] = per_pack_count.get(pat["id"], 0) + 1
                if per_pack_count[pat["id"]] > limit:
                    res.hits.append(LintHit(
                        f"pattern '{pat['id']}' exceeds per-pack limit "
                        f"{limit}", pat["severity"], regex, _excerpt(texts, idx)))
                elif per_pack_count[pat["id"]] == 1:
                    res.hits.append(LintHit(
                        f"pattern '{pat['id']}' (within limit, noted)",
                        "warn", regex, _excerpt(texts, idx)))
                continue
            res.hits.append(LintHit(f"banned_{pat['id']}", pat["severity"],
                                    regex, _excerpt(texts, idx)))


def _not_but_repetition(texts, cfg, res) -> None:
    pat = re.compile(r"不是[^，。]{1,20}，(而|是)")
    hits = [i for i, t in enumerate(texts) if pat.search(t)]
    if len(hits) > 1:
        res.hits.append(LintHit(
            "not_but_repetition",
            "warn" if len(hits) == 2 else "fail",
            f"used {len(hits)}x at positions {[h+1 for h in hits]}",
            _excerpt(texts, hits[0])))


def _translationese(texts, config_root, res) -> None:
    import os
    voice_path = os.path.join(config_root, "editorial", "voice.zh-CN.yaml")
    patterns = _TRANSLATIONESE_FALLBACK
    if os.path.exists(voice_path):
        with open(voice_path, encoding="utf-8") as fh:
            voice = yaml.safe_load(fh) or {}
        patterns = [p for p in (voice.get("translationese") or
                                _TRANSLATIONESE_FALLBACK)]
    for idx, text in enumerate(texts):
        for p in patterns:
            if re.search(p, text):
                res.hits.append(LintHit("translationese", "fail", p,
                                        _excerpt(texts, idx)))


def _ABS_WORDS_FALLBACK():
    return []


def _absolutes(texts, cfg, res) -> None:
    # 绝对化 only when the corresponding English hedge is missing —
    # the *pair* check lives in pack_validation; here we flag raw absolutes.
    pat = re.compile(r"(所有人|每个人)(都|均)|永远|从来(不)?|根本(不)?|绝不|一定")
    for idx, text in enumerate(texts):
        m = pat.search(text)
        if m:
            res.hits.append(LintHit("absolute_phrasing", "warn",
                                    m.group(0), _excerpt(texts, idx)))


def _abstract_stack(texts, cfg, res) -> None:
    words = (cfg.get("abstract_stack") or {}).get(
        "words", ["认知", "思维", "格局", "赋能", "价值", "力量", "智慧", "成长"])
    limit = (cfg.get("abstract_stack") or {}).get("max_in_sentence", 2)
    for idx, text in enumerate(texts):
        n = sum(1 for w in words if w in text)
        if n > limit:
            res.hits.append(LintHit("abstract_stack",
                                    "warn", f"{n} buzzwords",
                                    _excerpt(texts, idx)))


def _ending_rhythm(texts, cfg, res) -> None:
    cfg_r = cfg.get("ending_rhythm") or {}
    window = cfg_r.get("check_window", 3)
    same = cfg_r.get("identical_endings_warn", 2)
    for i in range(len(texts) - same + 1):
        endings = [t.rstrip()[-4:] for t in texts[i:i + same] if len(t) >= 4]
        if len(endings) == same and len(set(endings)) == 1:
            res.hits.append(LintHit(
                "ending_rhythm", "warn",
                f"{same} consecutive identical endings ('{endings[0]}')",
                _excerpt(texts, i)))
            break


_JUDGE_RE = re.compile(r"^[^，。]{2,14}，(其实)?是[^，。]{2,14}[。！？]?$")


def _judgment_ratio(texts, cfg, res) -> None:
    limit = (cfg.get("sentence_shape") or {}).get("max_judgment_ratio", 0.5)
    if not texts:
        return
    n = sum(1 for t in texts if _JUDGE_RE.match(t.strip()))
    if n / len(texts) > limit:
        res.hits.append(LintHit(
            "judgment_ratio", "warn",
            f"{n}/{len(texts)} sentences", ""))


def _punct_abuse(texts, cfg, res) -> None:
    for idx, text in enumerate(texts):
        if text.count("——") >= 3:
            res.hits.append(LintHit("dash_overuse", "warn", "dash",
                                    _excerpt(texts, idx)))
        if text.count("：") + text.count(":") >= 2:
            res.hits.append(LintHit("colon_stacking", "warn", "colon",
                                    _excerpt(texts, idx)))
        if text.count("「") > 1 or text.count("“") > 2:
            res.hits.append(LintHit("quote_nesting", "warn", "quotes",
                                    _excerpt(texts, idx)))


# ---------------------------------------------------------------------------
# Modality integrity: hedges must survive translation.
# ---------------------------------------------------------------------------

_HEDGES = {
    "maybe": r"也许|可能|或许",
    "perhaps": r"或许|可能",
    "often": r"常常|经常|往往",
    "usually": r"通常",
    "tend to": r"往往|倾向于",
    "can": r"可以|能|会",
    "might": r"可能",
    "i think": r"我认为|我觉得",
    "i fear": r"我担心|恐怕",
    "i have a hunch": r"我猜|直觉|有种预感",
}


def modality_violations(en_text: str, zh_text: str) -> List[str]:
    """Hedged English must not become absolute Chinese."""
    out = []
    low = en_text.lower()
    for hedge, zh_alts in _HEDGES.items():
        if re.search(rf"\b{re.escape(hedge)}\b", low):
            if not re.search(zh_alts, zh_text):
                out.append(f"source hedge '{hedge}' lost or absolutized in zh")
    return out


_NEGATION_FLIPS = [
    (r"\b(?:not|never|n't)\b", r"不|没|未|别|无|非"),
    (r"\b(?:do|does|did|is|are|was|were|can|could|will|would|has|have)n't\b",
     r"不|没|未|别|无|非"),
]


def negation_violations(en_text: str, zh_text: str) -> List[str]:
    out = []
    low = en_text.lower()
    for en_pat, zh_alts in _NEGATION_FLIPS:
        if re.search(en_pat, low) and not re.search(zh_alts, zh_text):
            out.append(f"negation '{en_pat}' dropped in zh — meaning flipped")
    return out
