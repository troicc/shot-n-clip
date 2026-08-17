"""Generate a short synthetic test video + subtitle fixture via ffmpeg.

Different brightness per scene and simple geometry so the deterministic frame
scorer has real signal (a near-black scene, a flat scene, sharp scenes).
"""

import os
import subprocess
import sys


def make_video(path: str, seconds: int = 12) -> None:
    # Five lavfi scenes concatenated: near-black, flat gray, geometry-heavy,
    # grid-on-blue, box-on-dark. The frame scorer must reject the first two.
    srcs = [
        "color=0x050505:s=640x360:d=3:r=10",
        "color=0x808080:s=640x360:d=2:r=10",
        "testsrc2=size=640x360:rate=10:duration=3",
        "color=0x3040a0:s=640x360:d=2:r=10,drawgrid=w=40:h=40:t=4:c=yellow@0.8",
        "color=0x101820:s=640x360:d=2:r=10,drawbox=x=100:y=80:w=200:h=150:t=8:c=white",
    ]
    inputs = " ".join(f"-f lavfi -i {s}" for s in srcs)
    filters = ";".join(f"[{i}:v]format=yuv420p,settb=AVTB[v{i}]"
                       for i in range(len(srcs)))
    concat_in = "".join(f"[v{i}]" for i in range(len(srcs)))
    cmd = (f"ffmpeg -hide_banner -loglevel error {inputs} "
           f"-filter_complex \"{filters};{concat_in}concat=n={len(srcs)}:v=1:a=0[outv]\" "
           f"-map \"[outv]\" -c:v libx264 -pix_fmt yuv420p -y \"{path}\"")
    subprocess.run(cmd, shell=True, check=True)


RAW_SNIPPETS = [
    {"text": "the first idea is simple", "start": 0.5, "duration": 2.0},
    {"text": "you have to protect your attention", "start": 2.6, "duration": 2.2},
    {"text": "and that means saying no", "start": 4.9, "duration": 1.8},
    {"text": "most people wake up and check their phone", "start": 6.8, "duration": 2.4},
    {"text": "that is a mistake, it fragments the mind", "start": 9.3, "duration": 2.4},
    {"text": "so choose one hard thing before noon", "start": 11.8, "duration": 2.2},
]

SENTENCES = [
    {"text": "The first idea is simple.", "start": "00:00:00", "end": "00:00:02"},
    {"text": "You have to protect your attention.", "start": "00:00:02", "end": "00:00:05"},
    {"text": "And that means saying no.", "start": "00:00:05", "end": "00:00:07"},
    {"text": "Most people wake up and check their phone.", "start": "00:00:07", "end": "00:00:09"},
    {"text": "That is a mistake, it fragments the mind.", "start": "00:00:09", "end": "00:00:12"},
    {"text": "So choose one hard thing before noon.", "start": "00:00:12", "end": "00:00:14"},
]

META = {
    "videoId": "fixt1re0001",
    "title": "合成测试视频 — attention & focus (非 ASCII 标题)",
    "channel": "Fixture Channel 频道",
    "duration": 14,
    "url": "https://www.youtube.com/watch?v=fixt1re0001",
    "language": {"code": "en", "name": "English", "isGenerated": True},
    "chapters": [],
}


def write_transcript_fixture(transcript_dir: str) -> None:
    import json
    os.makedirs(os.path.join(transcript_dir, "imgs"), exist_ok=True)
    with open(os.path.join(transcript_dir, "transcript-raw.json"), "w",
              encoding="utf-8") as fh:
        json.dump(RAW_SNIPPETS, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(transcript_dir, "transcript-sentences.json"), "w",
              encoding="utf-8") as fh:
        json.dump(SENTENCES, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(transcript_dir, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(META, fh, ensure_ascii=False, indent=2)


def selection_dict() -> dict:
    return {
        "schema_version": "1.0",
        "video_id": "fixt1re0001",
        "source_url": "https://www.youtube.com/watch?v=fixt1re0001",
        "video_title": META["title"],
        "channel": META["channel"],
        "source_language": "en",
        "angle": {
            "id": "angle-01",
            "title_zh": "注意力保护",
            "title_en": "Protecting attention",
            "one_sentence_promise": "如何在一天开始时守住注意力",
            "target_reader": "知识工作者",
        },
        "quotes": [
            {
                "id": "q01", "order": 1, "start_sec": 0.5, "end_sec": 2.5,
                "source_text": "The first idea is simple",
                "display_en": "The first idea is simple.",
                "display_zh": "第一个道理很简单。",
                "speaker": None, "frame_time_sec": None,
                "selection_reason": "hook",
                "scores": {"standalone_clarity": 18, "specificity_novelty": 15,
                           "emotional_tension": 10, "actionability": 8,
                           "memorability": 13, "translation_compactness": 9,
                           "source_fidelity": 5},
            },
            {
                "id": "q02", "order": 2, "start_sec": 2.6, "end_sec": 4.8,
                "source_text": "you have to protect your attention",
                "display_en": "You have to protect your attention.",
                "display_zh": "你必须保护自己的注意力。",
                "speaker": None, "frame_time_sec": None,
                "selection_reason": "problem",
                "scores": {"standalone_clarity": 19, "specificity_novelty": 16,
                           "emotional_tension": 12, "actionability": 10,
                           "memorability": 14, "translation_compactness": 9,
                           "source_fidelity": 5},
            },
            {
                "id": "q03", "order": 3, "start_sec": 4.9, "end_sec": 6.7,
                "source_text": "and that means saying no",
                "display_en": "And that means saying no.",
                "display_zh": "而这意味着说不。",
                "speaker": None, "frame_time_sec": None,
                "selection_reason": "insight",
                "scores": {"standalone_clarity": 17, "specificity_novelty": 14,
                           "emotional_tension": 11, "actionability": 12,
                           "memorability": 12, "translation_compactness": 9,
                           "source_fidelity": 5},
            },
            {
                "id": "q04", "order": 4, "start_sec": 6.8, "end_sec": 9.2,
                "source_text": "most people wake up and check their phone",
                "display_en": "Most people wake up and check their phone.",
                "display_zh": "大多数人醒来就看手机。",
                "speaker": None, "frame_time_sec": None,
                "selection_reason": "evidence",
                "scores": {"standalone_clarity": 18, "specificity_novelty": 15,
                           "emotional_tension": 12, "actionability": 8,
                           "memorability": 13, "translation_compactness": 9,
                           "source_fidelity": 5},
            },
            {
                "id": "q05", "order": 5, "start_sec": 9.3, "end_sec": 11.7,
                "source_text": "that is a mistake, it fragments the mind",
                "display_en": "That is a mistake — it fragments the mind.",
                "display_zh": "这是个错误，它会撕裂你的思维。",
                "speaker": None, "frame_time_sec": None,
                "selection_reason": "mechanism",
                "scores": {"standalone_clarity": 16, "specificity_novelty": 15,
                           "emotional_tension": 13, "actionability": 9,
                           "memorability": 12, "translation_compactness": 8,
                           "source_fidelity": 5},
            },
            {
                "id": "q06", "order": 6, "start_sec": 11.8, "end_sec": 13.9,
                "source_text": "so choose one hard thing before noon",
                "display_en": "So choose one hard thing before noon.",
                "display_zh": "所以在中午前做完一件难事。",
                "speaker": None, "frame_time_sec": None,
                "selection_reason": "close",
                "scores": {"standalone_clarity": 18, "specificity_novelty": 14,
                           "emotional_tension": 10, "actionability": 15,
                           "memorability": 13, "translation_compactness": 9,
                           "source_fidelity": 5},
            },
        ],
    }


def angles_dict() -> dict:
    return {
        "angles": [
            {
                "id": "angle-01", "title_zh": "注意力保护", "title_en": "Protect attention",
                "one_sentence_promise": "如何在一天开始时守住注意力",
                "target_reader": "知识工作者", "why_now": "手机优先的早晨普遍",
                "candidate_quote_ids": ["q01", "q02", "q03", "q04", "q05", "q06"],
                "novelty_score": 8, "coherence_score": 9, "platform_fit_score": 8,
                "risk_notes": "无",
            },
            {
                "id": "angle-02", "title_zh": "深度工作", "title_en": "Deep work",
                "one_sentence_promise": "如何在干扰中做深度工作",
                "target_reader": "远程工作者", "why_now": "远程办公常态化",
                "candidate_quote_ids": ["q02", "q05", "q06"],
                "novelty_score": 7, "coherence_score": 8, "platform_fit_score": 8,
                "risk_notes": "无",
            },
            {
                "id": "angle-03", "title_zh": "说不的勇气", "title_en": "Saying no",
                "one_sentence_promise": "为什么说不是一种能力",
                "target_reader": "管理者", "why_now": "过载普遍",
                "candidate_quote_ids": ["q03"],
                "novelty_score": 7, "coherence_score": 7, "platform_fit_score": 7,
                "risk_notes": "句子偏少",
            },
        ]
    }


def build_work_fixture(work_dir: str, video_path=None) -> None:
    import json
    import shutil
    write_transcript_fixture(os.path.join(work_dir, "transcript"))
    with open(os.path.join(work_dir, "selection.json"), "w", encoding="utf-8") as fh:
        json.dump(selection_dict(), fh, ensure_ascii=False, indent=2)
    with open(os.path.join(work_dir, "angles.json"), "w", encoding="utf-8") as fh:
        json.dump(angles_dict(), fh, ensure_ascii=False, indent=2)
    os.makedirs(os.path.join(work_dir, "frames", "candidates"), exist_ok=True)
    os.makedirs(os.path.join(work_dir, "frames", "selected"), exist_ok=True)
    os.makedirs(os.path.join(work_dir, "outputs"), exist_ok=True)
    if video_path and os.path.exists(video_path):
        shutil.copyfile(video_path, os.path.join(work_dir, "source_video.mp4"))


if __name__ == "__main__":
    target = sys.argv[1]
    make_video(target)
    print(f"wrote {target}")
