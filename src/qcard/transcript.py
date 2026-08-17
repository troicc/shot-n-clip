"""Transcript loading + agent_input.md generation on top of the upstream skill output."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .utils import fmt_ts

RAW_JSON = "transcript-raw.json"
SENTENCES_JSON = "transcript-sentences.json"
META_JSON = "meta.json"

MAX_AGENT_INPUT_CHARS = 120_000


@dataclass
class Snippet:
    text: str
    start: float
    duration: float

    @property
    def end(self) -> float:
        return self.start + self.duration


@dataclass
class Sentence:
    text: str
    start: float  # seconds (parsed from HH:mm:ss)
    end: float


def parse_hms(value: str) -> float:
    """'HH:MM:SS' or 'MM:SS' -> seconds."""
    parts = [float(p) for p in str(value).split(":")]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    h, m, s = parts
    return h * 3600 + m * 60 + s


@dataclass
class VideoMeta:
    video_id: str
    title: str
    channel: str
    duration: float
    url: str
    language_code: str
    language_name: str
    publish_date: str = ""


def load_meta(transcript_dir: str) -> VideoMeta:
    with open(os.path.join(transcript_dir, META_JSON), encoding="utf-8") as fh:
        raw = json.load(fh)
    lang = raw.get("language") or {}
    return VideoMeta(
        video_id=raw.get("videoId", ""),
        title=raw.get("title", ""),
        channel=raw.get("channel", ""),
        duration=float(raw.get("duration") or 0),
        url=raw.get("url", ""),
        language_code=lang.get("code", ""),
        language_name=lang.get("name", ""),
        publish_date=raw.get("publishDate", ""),
    )


def load_raw_snippets(transcript_dir: str) -> List[Snippet]:
    """Raw snippets carry the ground-truth timing used for source_text verification."""
    path = os.path.join(transcript_dir, RAW_JSON)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    out = []
    for item in raw:
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        out.append(Snippet(
            text=text,
            start=float(item.get("start", 0)),
            duration=float(item.get("duration", 0)),
        ))
    return out


def load_sentences(transcript_dir: str) -> List[Sentence]:
    """Sentence-level entries (timing estimated proportionally upstream)."""
    path = os.path.join(transcript_dir, SENTENCES_JSON)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    out = []
    for item in raw:
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        start = item.get("start")
        end = item.get("end")
        out.append(Sentence(
            text=text,
            start=parse_hms(start) if isinstance(start, str) else float(start or 0),
            end=parse_hms(end) if isinstance(end, str) else float(end or 0),
        ))
    return out


def build_transcript_text(transcript_dir: str) -> str:
    """One line per raw snippet: timestamp + text. Raw snippets have exact timing."""
    lines = []
    for sn in load_raw_snippets(transcript_dir):
        lines.append(f"[{fmt_ts(sn.start)}] {sn.text}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# agent_input.md — model-readable digest. Chunk by sentence boundaries when
# the transcript exceeds MAX_AGENT_INPUT_CHARS; never silently truncate.
# ---------------------------------------------------------------------------


def _chunk_by_chars(text: str, limit: int) -> List[Tuple[str, str]]:
    """Split a big text into chunks on line boundaries; return (label, chunk)."""
    lines = text.split("\n")
    chunks: List[Tuple[str, str]] = []
    buf: List[str] = []
    size = 0
    start_ts = ""
    for line in lines:
        if not start_ts:
            m = re.match(r"\[([\d:]+)\]", line)
            if m:
                start_ts = m.group(1)
        if size + len(line) + 1 > limit and buf:
            label = f"{start_ts} → " + (re.match(r"\[([\d:]+)\]", line).group(1) if re.match(r"\[([\d:]+)\]", line) else "end")
            chunks.append((label, "\n".join(buf)))
            buf, size, start_ts = [], 0, ""
            m = re.match(r"\[([\d:]+)\]", line)
            if m:
                start_ts = m.group(1)
        buf.append(line)
        size += len(line) + 1
    if buf:
        last_ts = ""
        for line in reversed(buf):
            m = re.match(r"\[([\d:]+)\]", line)
            if m:
                last_ts = m.group(1)
                break
        chunks.append((f"{start_ts} → {last_ts or 'end'}", "\n".join(buf)))
    return chunks


def write_agent_input(work_dir: str, transcript_dir: str, meta: VideoMeta,
                      source_url: str) -> str:
    text = build_transcript_text(transcript_dir)
    header = (
        f"# Agent Input — {meta.title}\n\n"
        f"- video_id: `{meta.video_id}`\n"
        f"- channel: {meta.channel}\n"
        f"- duration: {int(meta.duration)}s ({fmt_ts(meta.duration)})\n"
        f"- source_url: {source_url}\n"
        f"- transcript_language: {meta.language_code} ({meta.language_name})\n"
        f"- transcript_chars: {len(text)}\n\n"
        f"## 说明\n\n"
        f"- 每行格式为 `[HH:MM:SS] 字幕文本`，时间来自原始字幕片段，可信。\n"
        f"- 选择金句时 `source_text` 必须是字幕中连续出现的原文（可跨行拼接同一时间段的文本）。\n"
        f"- start_sec / end_sec 用秒（数值），落在对应字幕行的时间附近。\n"
    )
    agent_path = os.path.join(work_dir, "agent_input.md")
    os.makedirs(work_dir, exist_ok=True)
    if len(header) + len(text) <= MAX_AGENT_INPUT_CHARS:
        with open(agent_path, "w", encoding="utf-8") as fh:
            fh.write(header + "\n## 完整字幕（时间戳 + 文本）\n\n```\n" + text + "\n```\n")
        return agent_path

    # Chunk with an index; no silent truncation.
    chunks = _chunk_by_chars(text, MAX_AGENT_INPUT_CHARS - len(header) - 2_000)
    index_lines = []
    for i, (label, _) in enumerate(chunks, 1):
        index_lines.append(f"- agent_input_part{i}.md  ({label})")
    with open(agent_path, "w", encoding="utf-8") as fh:
        fh.write(header + "\n## 字幕分块索引（超过 120,000 字符，按行边界分块）\n\n"
                 + "\n".join(index_lines) + "\n")
    for i, (label, chunk) in enumerate(chunks, 1):
        part_path = os.path.join(work_dir, f"agent_input_part{i}.md")
        with open(part_path, "w", encoding="utf-8") as fh:
            fh.write(f"# Agent Input Part {i}/{len(chunks)} — {meta.title}\n\n"
                     f"时间范围: {label}\n\n```\n{chunk}\n```\n")
    return agent_path


def find_source_text(snippets: List[Snippet], source_text: str) -> Optional[Tuple[float, float]]:
    """Locate source_text inside the snippet stream.

    Matches after aggressive normalization (case/whitespace/punct). Returns
    (start_sec, end_sec) of the covering snippet window, or None.
    """
    from .utils import normalize_text
    needle = normalize_text(source_text)
    if not needle:
        return None
    # 1) Single-snippet containment.
    for sn in snippets:
        if needle in normalize_text(sn.text):
            return (sn.start, sn.end)
    # 2) Window of consecutive snippets (ASR splits sentences across snippets).
    norm = [normalize_text(sn.text) for sn in snippets]
    for window in range(2, 9):
        for i in range(len(norm) - window + 1):
            joined = "".join(norm[i:i + window])
            if needle in joined:
                return (snippets[i].start, snippets[i + window - 1].end)
    return None
