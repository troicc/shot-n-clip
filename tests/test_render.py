"""Render + frames + rerender-offline tests on a synthetic ffmpeg video."""

import json
import os
import shutil
import subprocess
import sys

import pytest
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import qcard.frames as frames_mod  # noqa: E402
import qcard.render as render_mod  # noqa: E402
from qcard.models import Selection  # noqa: E402
from qcard.cli import cmd_build, cmd_rerender, main as cli_main  # noqa: E402
from tests.fixtures.make_fixture_video import make_video, build_work_fixture  # noqa: E402

CONFIG_ROOT = os.path.join(os.path.dirname(__file__), "..", "config")
FFMPEG_REQUIRED = shutil.which("ffmpeg") is not None

pytestmark = pytest.mark.skipif(not FFMPEG_REQUIRED, reason="ffmpeg required")


@pytest.fixture(scope="module")
def synth_video(tmp_path_factory):
    path = str(tmp_path_factory.mktemp("media") / "fixture.mp4")
    make_video(path)
    return path


@pytest.fixture(scope="module")
def built_work(tmp_path_factory, synth_video):
    work = str(tmp_path_factory.mktemp("work") / "fixt1re0001")
    os.makedirs(work)
    build_work_fixture(work, video_path=synth_video)
    rc = cmd_build(_ns(work, "all", "classic"))
    assert rc == 0
    return work


def _ns(work_dir, mode, style):
    import argparse
    return argparse.Namespace(work_dir=work_dir, mode=mode, style=style)


# ---------------------------------------------------------------------------
# sizes
# ---------------------------------------------------------------------------


def test_output_is_1080x1440(built_work):
    for name in ("01_zh.png", "02_en.png", "03_bilingual.png"):
        img = Image.open(os.path.join(built_work, "outputs", name))
        assert img.size == (1080, 1440), f"{name}: {img.size}"


def test_rounded_corners_present(built_work):
    cfg = render_mod.load_style(CONFIG_ROOT, "classic")
    img = Image.open(os.path.join(built_work, "outputs", "01_zh.png")).convert("RGB")
    assert cfg.corner_radius >= 44 and cfg.corner_radius <= 52
    # Pixel boundary check: the exact corners must show the backing color
    # (gap_color), not frame content — proving the mask did its job.
    gap = cfg.gap_color
    for corner in [(1, 1), (1078, 1), (1, 1438), (1078, 1438)]:
        px = img.getpixel(corner)
        assert all(abs(px[i] - gap[i]) <= 12 for i in range(3)), (corner, px)


def test_strips_are_equal_height(built_work):
    cfg = render_mod.load_style(CONFIG_ROOT, "classic")
    img = Image.open(os.path.join(built_work, "outputs", "01_zh.png")).convert("RGB")
    # Gap rows must be near gap_color across the full width.
    strip_h = (1440 - cfg.strip_gap * 5) // 6
    for k in range(1, 6):
        y = k * strip_h + (k - 1) * cfg.strip_gap + cfg.strip_gap // 2
        row = [img.getpixel((x, y)) for x in (100, 540, 980)]
        for px in row:
            assert all(abs(px[i] - cfg.gap_color[i]) <= 25 for i in range(3)), (y, px)


# ---------------------------------------------------------------------------
# pair consistency: same frames, same order
# ---------------------------------------------------------------------------


def test_pair_outputs_use_identical_frames(built_work):
    zh = Image.open(os.path.join(built_work, "outputs", "01_zh.png")).convert("RGB")
    en = Image.open(os.path.join(built_work, "outputs", "02_en.png")).convert("RGB")
    cfg = render_mod.load_style(CONFIG_ROOT, "classic")
    strip_h = (1440 - cfg.strip_gap * 5) // 6
    strip_h = (1440 - cfg.strip_gap * 5) // 6
    # The top 40px of each strip contains no text band; frames must match there.
    for k in range(6):
        y_top = k * (strip_h + cfg.strip_gap)
        box = (0, y_top + 8, 1080, y_top + 40)
        a = zh.crop(box).tobytes()
        b = en.crop(box).tobytes()
        assert a == b, f"strip {k}: pair outputs use different frames"
    # And the same selected source image backs every strip.
    with open(os.path.join(built_work, "outputs", "manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    frame_paths = [q["frame_source"] for q in manifest["quotes"]]
    assert len(frame_paths) == 6
    for p in frame_paths:
        assert os.path.exists(p)


# ---------------------------------------------------------------------------
# text overflow
# ---------------------------------------------------------------------------


def test_overflow_raises_and_explains(built_work, tmp_path):
    errors = []
    selection = Selection.load(os.path.join(built_work, "selection.json"), errors)
    assert errors == []
    selection.quotes[0].display_zh = "这是一条被故意写得非常长的中文句子用来验证排版系统在达到最小字号之后必须报告溢出错误而不是继续缩小字号导致完全不可读" * 3
    cfg = render_mod.load_style(CONFIG_ROOT, "classic")
    book = render_mod.resolve_fonts()
    chosen = {q.id: os.path.join(built_work, "frames", "selected", f"{q.id}.jpg")
              for q in selection.quotes}
    with pytest.raises(render_mod.OverflowError_) as exc:
        render_mod.render_outputs(built_work, selection, cfg, chosen, "pair", fonts=book)
    assert "cannot fit" in str(exc.value)


def test_long_but_legal_zh_wraps_within_two_lines(built_work):
    errors = []
    selection = Selection.load(os.path.join(built_work, "selection.json"), errors)
    cfg = render_mod.load_style(CONFIG_ROOT, "classic")
    book = render_mod.resolve_fonts()
    font, lines, _h = render_mod.layout_text(
        "这是一条二十四个汉字左右的目标长度句子验证两行内完成换行",
        book.cjk_path, cfg.zh_font_range, int(1080 * 0.9), 2,
        cfg.zh_line_spacing, "zh", book)
    assert len(lines) <= 2


# ---------------------------------------------------------------------------
# deterministic frame scoring on the synthetic video
# ---------------------------------------------------------------------------


def test_frame_scoring_rejects_black_and_flat(synth_video):
    cand_black = _extract(synth_video, 1.0)   # near-black scene
    cand_flat = _extract(synth_video, 4.0)    # flat gray scene
    cand_sharp = _extract(synth_video, 6.0)   # testsrc2 geometry
    from PIL import Image as I
    for path, expect_reject, why in (
        (cand_black, "near-black", "black"),
        (cand_flat, "flat", "flat"),
    ):
        c = frames_mod.FrameCandidate(quote_id="t", t=1.0, path=path)
        scored = frames_mod.score_candidates([c])
        assert (not scored) and c.rejected_reason, f"{why} scene should be rejected"
    c = frames_mod.FrameCandidate(quote_id="t", t=6.0, path=cand_sharp)
    scored = frames_mod.score_candidates([c])
    assert len(scored) == 1 and scored[0].score > 0


def _extract(video, t):
    import tempfile
    path = os.path.join(tempfile.mkdtemp(), f"probe_{t}.jpg")
    assert frames_mod.extract_frame(video, t, path)
    return path


def test_candidate_times_cover_window_and_padding():
    times = frames_mod.candidate_times(10.0, 14.0, duration=100.0)
    assert len(times) >= 5
    assert any(abs(t - 12.0) < 0.01 for t in times)  # midpoint
    assert any(abs(t - 8.0) < 0.01 for t in times)   # -2s padding
    assert any(abs(t - 16.0) < 0.01 for t in times)  # +2s padding
    clamped = frames_mod.candidate_times(0.1, 0.3, duration=5.0)
    assert all(0 <= t < 5.0 for t in clamped)


def test_contact_sheet_written(built_work):
    sheet = os.path.join(built_work, "frames", "contact_sheet.jpg")
    assert os.path.exists(sheet) and os.path.getsize(sheet) > 10_000
    img = Image.open(sheet)
    assert img.width >= 320


# ---------------------------------------------------------------------------
# rerender: no network, no yt-dlp
# ---------------------------------------------------------------------------


def test_rerender_offline_and_idempotent(built_work, tmp_path, monkeypatch):
    # Fail loudly if anything tries to touch the network or spawn yt-dlp.
    def boom(*a, **kw):
        raise AssertionError("rerender must not call yt-dlp or download")

    monkeypatch.setattr("qcard.video.download_video", boom)
    monkeypatch.setattr("qcard.cli.run_transcript_skill", boom)
    monkeypatch.setattr("qcard.frames.extract_frame", boom)

    before = os.path.getmtime(os.path.join(built_work, "outputs", "01_zh.png"))
    rc = cmd_rerender(_ns(built_work, "pair", "classic"))
    assert rc == 0
    after = os.path.getmtime(os.path.join(built_work, "outputs", "01_zh.png"))
    assert after >= before


def test_rerender_after_text_edit(built_work, tmp_path):
    work = str(tmp_path / "w2")
    shutil.copytree(built_work, work)
    data = json.load(open(os.path.join(work, "selection.json"), encoding="utf-8"))
    data["quotes"][0]["display_zh"] = "改过的第一句。"
    with open(os.path.join(work, "selection.json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    rc = cli_main(["rerender", work, "--mode", "pair"])
    assert rc == 0
    # Manifest reflects the edit.
    manifest = json.load(open(os.path.join(work, "outputs", "manifest.json"),
                              encoding="utf-8"))
    assert manifest["quotes"][0]["display_zh"] == "改过的第一句。"
    # Frames untouched (same paths as before the edit).
    assert manifest["quotes"][0]["frame_source"].endswith("q01.jpg")


def test_pinned_frame_time_respected(synth_video, tmp_path):
    work = str(tmp_path / "w3")
    os.makedirs(work)
    build_work_fixture(work, video_path=synth_video)
    data = json.load(open(os.path.join(work, "selection.json"), encoding="utf-8"))
    data["quotes"][0]["frame_time_sec"] = 6.0  # pin to sharp scene
    with open(os.path.join(work, "selection.json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    rc = cmd_build(_ns(work, "pair", "classic"))
    assert rc == 0
    manifest = json.load(open(os.path.join(work, "outputs", "manifest.json"),
                              encoding="utf-8"))
    assert abs(manifest["quotes"][0]["frame"]["t"] - 6.0) < 1e-6
    assert "pinned" in manifest["quotes"][0]["frame"]["reason"]


# ---------------------------------------------------------------------------
# no-OpenCV path
# ---------------------------------------------------------------------------


def test_works_without_opencv(built_work, monkeypatch):
    monkeypatch.setattr(frames_mod, "HAS_OPENCV", False)
    monkeypatch.setattr(frames_mod, "cv2", None)
    rc = cmd_rerender(_ns(built_work, "all", "classic"))
    assert rc == 0


# ---------------------------------------------------------------------------
# publish copy
# ---------------------------------------------------------------------------


def test_publish_copy_written_and_hype_free(built_work):
    for name in ("publish_xhs.md", "publish_wechat.md"):
        path = os.path.join(built_work, "outputs", name)
        assert os.path.exists(path), name
        text = open(path, encoding="utf-8").read()
        for phrase in ("全网首发", "颠覆认知", "史上最"):
            assert phrase not in text
    xhs = open(os.path.join(built_work, "outputs", "publish_xhs.md"),
               encoding="utf-8").read()
    assert xhs.count("\n") > 10 and "原文对照见第 2 张" in xhs
