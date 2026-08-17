"""Draft publish copy (Xiaohongshu + WeChat) derived solely from selection.json."""

from __future__ import annotations

import os
from typing import List

from .models import Selection
from .utils import fmt_ts

BANNED_PHRASES = ["全网首发", "颠覆认知", "震惊", "史上最", "99%的人", "必看",
                  "绝世", "逆天", "封神"]


def _check_no_hype(text: str, errors: List[str], where: str) -> None:
    for phrase in BANNED_PHRASES:
        if phrase in text:
            errors.append(f"{where}: banned hype phrase '{phrase}'")


def _tags(selection: Selection) -> str:
    base = ["金句", "人物访谈", "深度思考"]
    if selection.source_language.startswith("en"):
        base += ["英文原文", "英语学习"]
    return " ".join(f"#{t}" for t in base)


def write_xhs(selection: Selection, out_dir: str) -> str:
    errors: List[str] = []
    quotes_block = "\n".join(
        f"{q.order}. {q.display_zh}" for q in selection.quotes)

    titles = [
        f"{selection.angle.title_zh}｜{selection.video_title[:28]}",
        f"{selection.quotes[0].display_zh[:30]}",
        f"{selection.angle.one_sentence_promise[:32]}",
        f"{selection.video_title[:24]}：{selection.angle.title_zh[:16]}",
        f"从这期访谈里，我记住了这{len(selection.quotes)}句话",
    ]
    ts_lines = "\n".join(
        f"- {q.id} {fmt_ts(q.start_sec)} {q.display_zh[:24]}" for q in selection.quotes)

    content = f"""# 小红书文案草稿（angle: {selection.angle.title_zh}）

## 标题候选（任选其一，可自行微调）

{chr(10).join(f'{i+1}. {t}' for i, t in enumerate(titles))}

## 导语

{selection.angle.one_sentence_promise}
这 {len(selection.quotes)} 句话来自 {selection.channel} 的这期访谈，原文出处见第 2 张图，中文对照见第 1 张图。

## 金句（纯文本版）

{quotes_block}

> 原文对照见第 2 张（英文原文 + 相同画面）。

## 来源信息

- 视频：{selection.video_title}
- 频道/嘉宾：{selection.channel}
- 链接：{selection.source_url}
- 时间戳：
{ts_lines}

## 标签建议

{_tags(selection)}
"""
    _check_no_hype(content, errors, "publish_xhs")
    if errors:
        raise ValueError("; ".join(errors))
    path = os.path.join(out_dir, "publish_xhs.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return path


def write_wechat(selection: Selection, out_dir: str) -> str:
    quotes_ctx = "\n\n".join(
        f"**{q.order}. {q.display_zh}**\n\n（{fmt_ts(q.start_sec)}）{q.selection_reason}"
        for q in selection.quotes)
    ts_lines = "\n".join(f"- {q.id} {fmt_ts(q.start_sec)}" for q in selection.quotes)

    content = f"""# 公众号文章草稿（angle: {selection.angle.title_zh}）

## 引导段

{selection.angle.one_sentence_promise}
这期 {selection.channel} 的访谈《{selection.video_title}》里，有 {len(selection.quotes)} 句值得单独记下来。下面每句都保留了原始时间戳，可以回到视频核对。

## 中文金句图（占位）

[在此插入 outputs/01_zh.png]

## 每句上下文

{quotes_ctx}

## 英文原文图（占位）

[在此插入 outputs/02_en.png]

## 原视频信息

- 视频：{selection.video_title}
- 频道/嘉宾：{selection.channel}
- 链接：{selection.source_url}
- 时间戳：
{ts_lines}

## 编辑说明

以上中文翻译为便于中文阅读调整了语序与断句，未增删事实；英文以视频原话为准，原文见图 2 与上述时间戳。
"""
    path = os.path.join(out_dir, "publish_wechat.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return path


def write_all(selection: Selection, work_dir: str) -> List[str]:
    out_dir = os.path.join(work_dir, "outputs")
    os.makedirs(out_dir, exist_ok=True)
    return [write_xhs(selection, out_dir), write_wechat(selection, out_dir)]
