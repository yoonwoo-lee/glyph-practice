"""Checks for the tuning page, the timing log and the lighting correction.

    python -m tests.test_tools
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from glyph import config, demo, tune  # noqa: E402
from glyph.page import find_page_quad, normalize_light, warp_page  # noqa: E402
from tests.test_pipeline import run  # noqa: E402


def _page(step="highlights", change=None):
    f = demo.build_steps()[step]
    if change:
        f = change(f)
    quad, _ = find_page_quad(f)
    return warp_page(f, quad)


def test_timing_log_has_a_row_per_look():
    s = demo.build_steps()
    engine, brain, session = run([s["blank"], s["spark"], s["underline"]])
    rows = [json.loads(line) for line in (session.dir / "timings.jsonl").read_text().splitlines()]
    assert len(rows) == len(brain.calls) == 2, rows
    for r in rows:
        assert r["total_s"] >= r["model_s"] >= 0 and r["triggers"] == 1 and r["error"] == "", r
    hint = session.events_of("hint")[0]
    assert hint["meta"]["seconds"] == rows[0]["total_s"], hint
    st = engine.status()
    assert st["last_seconds"] is not None and st["avg_seconds"] is not None, st


def test_each_answer_gets_a_picture_of_its_mark():
    s = demo.build_steps()
    engine, brain, session = run([s["blank"], s["spark"], s["underline"]])
    hint, define = session.events_of("hint")[0], session.events_of("define")[0]
    assert hint["at"] >= 0 and define["at"] >= hint["at"], (hint, define)
    for e in (hint, define):
        img = cv2.imread(str(session.snip_path(e["meta"]["snip"])))
        assert img is not None, e
        h, w = img.shape[:2]
        assert abs(w / float(h) - 1.5) < 0.05 and w >= 300, (w, h)
    # the spark sits in the margin: its picture must reach left far enough to show the working
    img = cv2.imread(str(session.snip_path(hint["meta"]["snip"])))
    dark = (cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) < 120).sum(axis=0)
    assert dark[: img.shape[1] // 2].sum() > 300, "no writing in the left half of the hint picture"


def test_warm_or_dim_light_does_not_change_paper_color():
    warm = lambda f: (f.astype("float32") * [0.7, 0.9, 1.0]).clip(0, 255).astype("uint8")  # noqa: E731
    for change in (warm, lambda f: demo.dim(f, 0.4), lambda f: demo.lamp(f, 0.3)):
        hsv = cv2.cvtColor(normalize_light(_page("blank", change)), cv2.COLOR_BGR2HSV)
        blank = hsv[430:470, 300:700]  # empty paper between the working and the notes
        assert np.median(blank[..., 1]) < 30, "paper still tinted: S=%d" % np.median(blank[..., 1])
        assert np.median(blank[..., 2]) > 200, "paper still dark: V=%d" % np.median(blank[..., 2])


def test_probe_and_fit_find_the_highlighter():
    page = _page()
    hsv = tune.probe(page, 300 / 850.0, 550 / 1100.0)  # on the yellow line
    lo, hi = config.HIGHLIGHT_HSV["yellow"][0]
    assert lo[0] <= hsv["h"] <= hi[0] and hsv["s"] > 80, hsv
    fit = tune.fit("yellow", hsv)
    assert fit["hmin"] <= hsv["h"] <= fit["hmax"] and fit["smin"] < hsv["s"] and fit["vmin"] < hsv["v"], fit
    paper = tune.probe(page, 0.5, 0.41)
    assert paper["s"] < 35, paper
    assert tune.fit("purple", hsv) is None


def test_apply_and_save_keep_the_key():
    s = demo.build_steps()
    engine, brain, session = run([s["blank"]], hold=0.8)
    before = tune.values(engine)
    root, ink_c, hsv = config.ROOT, config.INK_C, dict(config.HIGHLIGHT_HSV)
    tmp = Path(tempfile.mkdtemp(prefix="glyph_env_"))
    (tmp / ".env").write_text("GEMINI_API_KEY=secret-123\n# GLYPH_INK_C=14\nGLYPH_SETTLE_SECONDS=1.0\n")
    try:
        config.ROOT = tmp
        after = tune.apply(engine, {"ink_c": 99, "settle": 1.4, "colors": {"pink": {"hmin": 150, "hmax": 170, "smin": 80, "vmin": 160}, "bogus": {}}})
        assert after["ink_c"] == 40 and after["settle"] == 1.4, after  # clamped to the slider range
        assert config.HIGHLIGHT_HSV["pink"] == [((150, 80, 160), (170, 255, 255))]
        assert tune.save_env(engine) > 0
        text = (tmp / ".env").read_text()
        assert "GEMINI_API_KEY=secret-123" in text, "the key line must survive"
        assert "GLYPH_SETTLE_SECONDS=1.4" in text and text.count("GLYPH_SETTLE_SECONDS") == 1, text
        assert "GLYPH_INK_C=40" in text and "GLYPH_HSV_PINK=150,80,160,170,255,255" in text, text
    finally:
        config.ROOT, config.INK_C = root, ink_c
        config.HIGHLIGHT_HSV.clear()
        config.HIGHLIGHT_HSV.update(hsv)
        engine.settings.settle = before["settle"]


def test_tuner_pictures_render():
    s = demo.build_steps()
    engine, brain, session = run([s["highlights"]], hold=1.0)
    for which in ("page", "ink", "highlights", "cover"):
        img = cv2.imdecode(np.frombuffer(tune.render(engine, which), np.uint8), cv2.IMREAD_COLOR)
        assert img is not None and img.shape[0] > 500, which


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    failed = 0
    for t in TESTS:
        t0 = time.time()
        try:
            t()
            print("ok    %-52s %.1fs" % (t.__name__, time.time() - t0))
        except AssertionError as e:
            failed += 1
            print("FAIL  %-52s %s" % (t.__name__, e))
    print("\n%d passed, %d failed" % (len(TESTS) - failed, failed))
    sys.exit(1 if failed else 0)
