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
from glyph import engine as engine_mod  # noqa: E402
from glyph.page import find_page_quad, normalize_light, warp_page  # noqa: E402
from tests.test_pipeline import kinds, run  # noqa: E402


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



def test_covered_highlight_is_not_saved_again():
    """A hand over part of a saved highlight leaves smaller pieces of it. They are not new highlights."""
    from glyph.highlights import HighlightStore

    page = np.full((900, 700, 3), 245, np.uint8)
    cv2.rectangle(page, (100, 200), (500, 240), (60, 230, 250), -1)
    store = HighlightStore(Path(tempfile.mkdtemp(prefix="glyph_hl_")), {"yellow": "Key ideas"})
    store.new_page()
    whole = [{"color": "yellow", "bbox": (100, 200, 400, 40), "area": 16000}]
    store.update(whole, page)
    assert len(store.update(whole, page)) == 1
    for piece in [(100, 200, 110, 40), (100, 202, 90, 36), (420, 200, 80, 40)]:  # overlap as low as 0.2
        part = [{"color": "yellow", "bbox": piece, "area": piece[2] * piece[3]}]
        store.update(part, page)
        assert store.update(part, page) == [], piece
    assert len(store.all()) == 1
    # A separate highlight further down the page still counts.
    other = [{"color": "yellow", "bbox": (100, 400, 300, 40), "area": 12000}]
    store.update(other, page)
    assert len(store.update(other, page)) == 1


class _Err(Exception):
    def __init__(self, code, text):
        super().__init__(text)
        self.code = code


def _brain_with(models, behave):
    """A Brain wired to a fake Gemini. behave(model, config, n) returns text or raises."""
    from glyph import brain as brain_mod
    from google.genai import types

    class Models:
        def __init__(self):
            self.asked = []

        def generate_content(self, model, contents, config):
            self.asked.append(model)
            return type("R", (), {"text": behave(model, config, len(self.asked))})()

    b = brain_mod.Brain.__new__(brain_mod.Brain)
    b._types, b.legend, b.system, b.last_model = types, config.load_legend(), "s", ""
    b._no_budget, b._resting, b._quota_hits, b.last_errors = set(), {}, {}, []
    b.models = list(models)
    b._client = type("C", (), {"models": Models()})()
    return b


OK = '{"occluded": false, "triggers": []}'


def test_dead_model_is_dropped_and_the_next_one_answers():
    def behave(model, cfg, n):
        if model == "old":
            raise _Err(404, "This model models/old is no longer available to new users.")
        if model == "slow":
            raise TimeoutError("timed out")
        return OK

    b = _brain_with(["old", "slow", "good"], behave)
    assert b.analyze(b"jpg") == {"occluded": False, "triggers": []}
    assert b.last_model == "good" and b.models == ["good", "slow"], b.models  # dead one dropped, slow one last
    b.analyze(b"jpg")
    assert b._client.models.asked == ["old", "slow", "good", "good"], b._client.models.asked


def test_model_over_its_limit_is_left_alone_for_a_while():
    from glyph import brain as brain_mod

    def behave(model, cfg, n):
        if model == "a" or (model == "b" and n > 3):
            raise _Err(429, "RESOURCE_EXHAUSTED. You exceeded your current quota. Please retry in 40s.")
        return OK

    b = _brain_with(["a", "b"], behave)
    b.analyze(b"jpg")  # a is over its limit, b answers
    b.analyze(b"jpg")  # a is resting: only b is asked
    assert b._client.models.asked == ["a", "b", "b"], b._client.models.asked
    try:
        b.analyze(b"jpg")  # now b is over its limit too
        raise AssertionError("expected a quota error")
    except brain_mod.QuotaError as e:
        assert 30 <= e.retry_after <= 41, e.retry_after
        assert "usage limit" in str(e), str(e)
    asked = len(b._client.models.asked)
    try:
        b.analyze(b"jpg")  # everything is resting: fail at once, without spending a request
        raise AssertionError("expected a quota error")
    except brain_mod.QuotaError:
        pass
    assert len(b._client.models.asked) == asked, b._client.models.asked


def test_busy_model_gets_one_more_try_and_a_slow_one_does_not():
    from glyph import brain as brain_mod

    def behave(model, cfg, n):
        if model == "busy":
            raise _Err(503, "UNAVAILABLE. The model is overloaded.")
        raise _Err(504, "DEADLINE_EXCEEDED")

    b = _brain_with(["slow", "busy"], behave)
    try:
        b.analyze(b"jpg")
        raise AssertionError("expected an error")
    except brain_mod.BrainError as e:
        assert "too slow" in str(e) and "busy" in str(e), str(e)
    assert b._client.models.asked == ["slow", "busy", "busy"], b._client.models.asked


def test_model_that_refuses_the_thinking_setting_is_asked_again_without_it():
    seen = []

    def behave(model, cfg, n):
        seen.append(cfg.thinking_config is not None)
        if cfg.thinking_config is not None:
            raise _Err(400, "INVALID_ARGUMENT. Budget 0 is invalid. This model only works in thinking mode.")
        return OK

    b = _brain_with(["m"], behave)
    b.analyze(b"jpg")
    b.analyze(b"jpg")
    assert seen == [True, False, False], seen  # asked with it once, then never again


def test_client_uses_v1beta_one_attempt_and_a_timeout():
    import os
    from glyph import brain as brain_mod

    os.environ["GEMINI_API_KEY"] = "test-key-not-real"
    try:
        b = brain_mod.Brain(config.load_legend())
    finally:
        del os.environ["GEMINI_API_KEY"]
    opts = b._client._api_client._http_options
    assert opts.api_version == "v1beta", opts.api_version
    assert opts.timeout == int(config.LLM_TIMEOUT_SECONDS * 1000) and opts.timeout >= 10000, opts.timeout  # Gemini's minimum
    assert opts.retry_options.attempts == 1, opts.retry_options
    assert not any(m.startswith("gemini-2.5") for m in b.models), b.models
    assert b.models[0] == config.LLM_MODEL and len(b.models) == len(set(b.models)), b.models

def _second_sheet():
    page = np.full((demo.PAGE_H, demo.PAGE_W, 3), 244, np.uint8)
    for i in range(9):
        cv2.putText(page, "Chapter 4 reading, a different page, line %d." % i, (70, 640 + 45 * i), demo.FONT, 0.8, demo.INK, 2, cv2.LINE_AA)
    return page


def test_study_guide_has_a_section_per_sheet():
    first = demo.build_steps()["highlights"]
    page2 = _second_sheet()
    blank2 = demo.desk_scene(page2)
    tint = np.array(demo.MARKER["yellow"], np.float32) / 255.0
    page2[690:730, 60:640] = (page2[690:730, 60:640].astype(np.float32) * tint).astype(np.uint8)
    marked2 = demo.desk_scene(page2)
    # Sheet 1, sheet 2, then sheet 1 again: still two pages, not three.
    engine, brain, session = run([first, blank2, marked2, first], hold=2.6, big_hold=0.6)
    pages = sorted({r["page_no"] for r in engine.store.all()})
    assert len(pages) == 2, [(r["page_no"], r["color"]) for r in engine.store.all()]
    assert engine.store.page_no == pages[0], "back on the first sheet, it keeps its number"
    guide = engine.study_guide()
    assert "## Page 1" in guide and "## Page 2" in guide and "## Page 3" not in guide, guide
    assert "### Key ideas" in guide, guide


def test_sheet_sliding_out_of_view_is_not_read():
    s = demo.build_steps()
    page = demo.base_page()
    demo.draw_spark(page)
    off = demo.desk_scene(page, shift=(760, 0))  # the right part of the sheet leaves the picture
    engine, brain, session = run([s["blank"], off], hold=2.4)
    assert brain.calls == [], brain.calls
    assert engine.status()["text"] == engine_mod.CUT_OFF_TEXT, engine.status()
    assert len(engine.store._signatures) == 1, "sliding out is not a new page"

def test_a_new_sheet_is_read_in_full_straight_away():
    s = demo.build_steps()
    engine, brain, session = run([s["spark"]], hold=2.0, read_first_page=True)
    assert [c["full"] for c in brain.calls] == [True], brain.calls


def test_camera_picture_endpoint():
    from fastapi.testclient import TestClient
    from glyph.app import create_app

    s = demo.build_steps()
    engine, brain, session = run([s["blank"]], hold=1.2)
    client = TestClient(create_app(engine))
    for which in ("raw", "page"):
        r = client.get("/api/frame/%s.jpg" % which)
        assert r.status_code == 200 and r.content[:2] == b"\xff\xd8", (which, r.status_code)
    assert client.get("/api/frame/other.jpg").status_code == 404

def test_study_guide_puts_hints_and_words_under_their_page():
    s = demo.build_steps()
    engine, brain, session = run([s["blank"]], hold=1.0)
    session.add_event("hint", "Hint", "try the power rule", target="problem 1", page=2)
    session.add_event("define", "Definition: panzootic", "a very wide outbreak", target="panzootic", page=3)
    guide = engine.study_guide()
    one, two = guide.index("## Page 1"), guide.index("## Page 2")
    assert one < guide.index("problem 1") < two < guide.index("panzootic"), guide
    assert "### Where you asked for help" in guide and "### Words you looked up" in guide, guide


def test_sheet_is_found_on_a_wooden_desk_with_a_shadow_across_it():
    page = demo.base_page()
    scene = demo.desk_scene(page)
    paper = cv2.inRange(scene, (150, 150, 150), (255, 255, 255))
    scene[paper == 0] = (60, 130, 190)  # orange-brown wood, about as bright as shaded paper
    shade = np.ones(scene.shape[:2], np.float32)
    cv2.ellipse(shade, (1000, 500), (260, 330), 0, 0, 360, 0.55, -1)  # the phone's shadow on the sheet
    shade = cv2.GaussianBlur(shade, (0, 0), 25)
    scene = (scene.astype(np.float32) * shade[..., None]).astype(np.uint8)
    quad, clean = find_page_quad(scene)
    want, _ = find_page_quad(demo.desk_scene(page))
    assert quad is not None and clean, "sheet not found"
    assert float(np.abs(quad - want).max()) < 12, np.abs(quad - want).max()

def test_camera_is_chosen_by_what_it_sees():
    from glyph import camera

    desk = np.full((1080, 1920, 3), (60, 130, 190), np.uint8)  # just a desk: no sheet
    sheet = demo.build_steps()["blank"]
    said = []
    real = camera.find_cameras
    try:
        camera.find_cameras = lambda max_index=5: [(0, sheet), (1, desk)]
        assert camera.pick_camera(wait=0, say=said.append) == 0  # the one looking at paper, wherever it is
        camera.find_cameras = lambda max_index=5: [(0, desk), (1, desk)]
        assert camera.pick_camera(wait=0, say=said.append) == 1  # no paper anywhere: the phone comes last
        camera.find_cameras = lambda max_index=5: [(0, desk)]
        assert camera.pick_camera(wait=0, say=said.append) == 0  # only one camera: use it
        seen = iter([[(0, desk)], [(0, desk), (1, sheet)]])
        camera.find_cameras = lambda max_index=5: next(seen)
        real_sleep, camera.time.sleep = camera.time.sleep, lambda s: None
        try:
            assert camera.pick_camera(wait=30, say=said.append) == 1  # waited, and the phone connected
        finally:
            camera.time.sleep = real_sleep
        assert any("Waiting for a phone" in line for line in said), said
    finally:
        camera.find_cameras = real


def test_blank_or_dark_view_is_not_sent_to_the_model():
    dark = np.full((1080, 1920, 3), 25, np.uint8)
    blank = demo.desk_scene(np.full((demo.PAGE_H, demo.PAGE_W, 3), 244, np.uint8))
    for scene in (dark, blank):
        engine, brain, session = run([scene], hold=2.0, read_first_page=True)
        assert brain.calls == [], brain.calls


def test_sheet_that_comes_back_is_not_read_in_full_again():
    first = demo.build_steps()["blank"]
    second = demo.desk_scene(_second_sheet())
    engine, brain, session = run([first, second, first], hold=2.4, big_hold=0.6, read_first_page=True)
    assert [c["full"] for c in brain.calls] == [True, True], brain.calls  # once per sheet, not three times


def test_sheet_sliding_a_little_keeps_old_ink_old_and_new_ink_new():
    page = demo.base_page()
    before = demo.desk_scene(page)
    demo.draw_spark(page)
    after = demo.desk_scene(page, shift=(8, -6))  # the paper slid while the spark was drawn
    engine, brain, session = run([before, after], hold=2.0)
    assert len(brain.calls) == 1 and not brain.calls[0]["full"], brain.calls
    w, h = brain.calls[0]["shape"]
    assert max(w, h) <= 80, "only the spark is new, not the whole page: %r" % (brain.calls[0]["shape"],)
    assert kinds(session) == ["hint"], kinds(session)


def test_shadow_falling_on_the_page_is_not_a_cover_and_not_ink():
    s = demo.build_steps()
    shade = np.ones(s["blank"].shape[:2], np.float32)
    cv2.ellipse(shade, (1000, 520), (300, 260), 0, 0, 360, 0.62, -1)
    shade = cv2.GaussianBlur(shade, (0, 0), 30)[..., None]
    dark = lambda f: (f.astype(np.float32) * shade).astype(np.uint8)  # noqa: E731
    engine, brain, session = run([s["blank"], dark(s["blank"]), dark(s["spark"])], hold=1.6)
    assert engine._cover is None, "a shadow must not count as something lying on the sheet"
    assert len(brain.calls) == 1 and kinds(session) == ["hint"], (brain.calls, kinds(session))



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
