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
from tests.test_pipeline import _stepper, kinds, run  # noqa: E402


def _page(step="highlights", change=None):
    f = demo.build_steps()[step]
    if change:
        f = change(f)
    quad, _ = find_page_quad(f)
    return warp_page(f, quad)


def _page_of(scene):
    quad, _ = find_page_quad(scene)
    return warp_page(scene, quad)


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
    b._types, b.legend, b.system, b.last_model, b._systems = types, config.load_legend(), "s", "", {}
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


def test_two_timeouts_in_a_row_end_the_round():
    """Nov 21: all four models timed out one after another: 39 seconds and four requests for
    nothing. Two in a row is the connection; the other two are asked first next time."""
    from glyph import brain as brain_mod

    down = [True]

    def behave(model, cfg, n):
        if down[0]:
            raise TimeoutError("timed out")
        return OK

    b = _brain_with(["a", "b", "c", "d"], behave)
    try:
        b.analyze(b"jpg")
        raise AssertionError("expected an error")
    except brain_mod.BrainError as e:
        assert str(e).count("too slow") == 2, str(e)
    assert b._client.models.asked == ["a", "b"] and b.models == ["c", "d", "a", "b"], (b._client.models.asked, b.models)
    down[0] = False
    b.analyze(b"jpg")
    assert b.last_model == "c", b.last_model


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
    steps = demo.build_steps()
    first, blank1 = steps["highlights"], steps["underline"]  # highlighted while in view (Nov 22: ones already there are not saved)
    page2 = _second_sheet()
    blank2 = demo.desk_scene(page2)
    tint = np.array(demo.MARKER["yellow"], np.float32) / 255.0
    page2[690:730, 60:640] = (page2[690:730, 60:640].astype(np.float32) * tint).astype(np.uint8)
    marked2 = demo.desk_scene(page2)
    # Sheet 1, sheet 2, then sheet 1 again: still two pages, not three.
    engine, brain, session = run([blank1, blank1, first, blank2, marked2, first], hold=2.6, big_hold=0.6)
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
    session.add_event("hint", "Hint", "try the power rule", target="problem 1", page=1)
    session.add_event("define", "Definition: panzootic", "a very wide outbreak", target="panzootic", page=2)
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

def test_sheet_is_found_on_a_light_gray_desk():
    """Nov 21: a gray table by a window. Desk and paper are both "not colorful, not dark", and
    the desk is nearly as bright as the paper at one corner. The whole table was read as a page."""
    from glyph.page import find_sheet

    s = demo.build_steps()
    want, _ = find_page_quad(s["blank"])
    seen = {}
    quad, clean, touches, fill, cut_off = find_sheet(demo.on_gray_desk(s["blank"]), seen)
    assert quad is not None and clean and seen.get("way") == "edges", (clean, seen)
    assert float(np.abs(quad - want).max()) < 12, np.abs(quad - want).max()
    # with an arm across it the outline is unclear, but it is neither "out of view" nor gone
    quad, clean, touches, fill, cut_off = find_sheet(demo.add_hand(demo.on_gray_desk(s["blank"])), seen)
    assert quad is not None and not clean and not cut_off, (clean, cut_off)
    # the bare table is not a sheet
    bare = demo.on_gray_desk(np.zeros_like(s["blank"]))
    bare = cv2.resize(bare[60:260, 600:1000], (1920, 1080))
    assert not find_sheet(bare)[1]


def test_spark_on_a_light_gray_desk_gets_a_hint():
    s = demo.build_steps()
    g = demo.on_gray_desk
    engine, brain, session = run([g(s["blank"]), g(s["spark"])], hold=1.6)
    assert kinds(session) == ["hint"], kinds(session)
    assert engine.quad is not None, "the whole picture was taken for the page"
    # a gray ceiling or a bare table, with a lamp at the edge, is not a page: no request
    bare = cv2.resize(g(np.zeros_like(s["blank"]))[60:260, 600:1000], (1920, 1080))
    cv2.circle(bare, (60, 1040), 220, (190, 235, 245), -1)
    engine, brain, session = run([bare], hold=1.6)
    assert not brain.calls and engine.baseline is None, (brain.calls,)
    # starting with a hand on the sheet: nothing is read until the sheet is clear
    engine, brain, session = run([demo.add_hand(g(s["blank"]))], hold=1.6)
    assert not brain.calls and engine.baseline is None, (brain.calls,)


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


# ---- from the Nov 19 camera session ------------------------------------------------------------

WOOD = (60, 130, 190)  # orange-brown desk, as (B, G, R)


def _on_wood(scene):
    out = scene.copy()
    paper = cv2.inRange(scene, (150, 150, 150), (255, 255, 255))
    out[paper == 0] = WOOD
    return out


def test_gray_clothing_next_to_the_sheet_is_not_taken_for_paper():
    """A gray sleeve touching the sheet used to be flattened as part of the page, hands and all."""
    scene = _on_wood(demo.build_steps()["blank"])
    want, clean = find_page_quad(scene)
    assert want is not None and clean
    right = int(want[:, 0].max())
    cv2.rectangle(scene, (right - 4, 60), (1919, 1079), (128, 130, 134), -1)  # sweatshirt beside the sheet
    quad, clean = find_page_quad(scene)
    assert quad is not None and clean, "sheet not found next to gray cloth"
    assert float(np.abs(quad - want).max()) < 14, np.abs(quad - want).max()


def test_bare_desk_is_not_read_as_a_page():
    """Take the sheet away: nothing is sent, nothing is saved as a highlight, and the outline is dropped."""
    sheet = _on_wood(demo.build_steps()["blank"])
    desk = np.full(sheet.shape, WOOD, np.uint8)
    engine, brain, session = run([sheet, desk], hold=2.6, read_first_page=True)
    assert [c["full"] for c in brain.calls] == [True], brain.calls  # the sheet once; the desk never
    assert engine.quad is None and engine.baseline is None
    assert engine.status()["text"] == engine_mod.NO_SHEET_TEXT, engine.status()
    assert engine.store.all() == [], "wood must not be saved as a highlight"
    assert engine.status()["view"]["phase"] == "none", engine.status()["view"]


def test_close_up_shows_the_new_ink_in_pink_and_nothing_else():
    from glyph import page as P

    before, after = _page("spark"), _page("underline")
    old, now = P.ink_strength(before), P.ink_strength(after)
    fresh = P.marks_only(P.remove_small(P.new_ink(now, old), 8))
    crop, box = P.make_focus_crop(after, fresh, ink=P.strength_to_mask(now), old=P.strength_to_mask(old))
    assert crop is not None and max(crop.shape[:2]) >= 400, crop.shape  # small marks are enlarged
    pink = cv2.inRange(crop, np.array(P.NEW_INK_COLOR) - 30, np.array(P.NEW_INK_COLOR) + 30)
    share = cv2.countNonZero(pink) / float(pink.size)
    assert 0.001 < share < 0.1, "the underline should be pink and the rest of the close-up untouched: %.4f" % share
    # the word above the underline is still there at full contrast: not faded, not pink
    assert (cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) < 90).sum() > 500, "the writing above the underline was faded out"


def test_a_small_spark_stays_a_spark_in_the_close_up():
    """A spark a few millimetres across, as the camera sees it: pink arms, not a pink blob."""
    import math

    from glyph import page as P

    before = _page("blank")
    big = cv2.resize(before, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    cx, cy = 4 * 640, 4 * 310
    for i in range(4):  # eight arms, 12 px long and under 2 px wide once shrunk back
        dx, dy = math.cos(i * math.pi / 4) * 48, math.sin(i * math.pi / 4) * 48
        cv2.line(big, (int(cx - dx), int(cy - dy)), (int(cx + dx), int(cy + dy)), (40, 36, 34), 6, cv2.LINE_AA)
    after = cv2.GaussianBlur(cv2.resize(big, (before.shape[1], before.shape[0]), interpolation=cv2.INTER_AREA), (3, 3), 0)
    old, now = P.ink_strength(before), P.ink_strength(after)
    fresh = P.marks_only(P.remove_small(P.new_ink(now, old), 8))
    assert cv2.countNonZero(fresh) > 0
    crop, box = P.make_focus_crop(after, fresh, ink=P.strength_to_mask(now), old=P.strength_to_mask(old))
    pink = cv2.inRange(crop, np.array(P.NEW_INK_COLOR) - 40, np.array(P.NEW_INK_COLOR) + 40)
    x, y, w, h = cv2.boundingRect(cv2.findNonZero(pink))
    filled = cv2.countNonZero(pink) / float(w * h)
    assert w > 40 and h > 40, (w, h)
    assert 0.08 < filled < 0.5, "the spark came out as a solid patch of pink: %.2f of its box" % filled


def test_marks_only_drops_specks_and_what_comes_in_from_the_edge():
    from glyph import page as P

    mask = np.zeros((1100, 850), np.uint8)
    cv2.rectangle(mask, (400, 500), (403, 503), 255, -1)  # a speck
    cv2.line(mask, (300, 700), (360, 702), 255, 3)  # an underline
    cv2.line(mask, (12, 900), (60, 930), 255, 5)  # a fingertip's outline at the edge of the sheet
    kept = P.marks_only(mask)
    assert kept[701, 330] and not kept[501, 401] and not kept[915, 36], "kept the wrong bits"


def test_remembered_page_is_lined_up_with_a_page_that_turned_a_little():
    """Print that lands two pixels off must not count as new ink; a different page must be noticed."""
    from glyph import page as P

    page = _page("underline")
    h, w = page.shape[:2]
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = src + np.float32([[12, -6], [4, 10], [-14, 8], [6, -12]])  # corners measured a little differently
    turned = cv2.warpPerspective(page, cv2.getPerspectiveTransform(src, dst), (w, h), borderValue=(244, 244, 244))
    old, now = P.ink_strength(page), P.ink_strength(turned)
    off = cv2.countNonZero(P.marks_only(P.remove_small(P.new_ink(now, old), 8)))
    m, sure = P.register(old, now)
    assert sure and m is not None, (sure, m)
    left = cv2.countNonZero(P.marks_only(P.remove_small(P.new_ink(now, P.move(old, m)), 8)))
    assert off > 1500 and left < 0.02 * off, "lining up should explain nearly all of it: %d -> %d" % (off, left)
    quad, _ = find_page_quad(demo.build_steps()["blank"])
    other = P.ink_strength(warp_page(demo.desk_scene(_second_sheet()), quad))
    assert P.register(old, other)[1] is False, "a different page cannot be lined up"
    assert P.register(old, old) == (None, True)


def test_an_answer_is_not_repeated_for_the_same_mark():
    """Whatever the model says, the same definition for the same word on the same sheet is shown once."""
    page = demo.base_page()
    blank = demo.desk_scene(page)
    demo.draw_underline(page)
    underlined = demo.desk_scene(page)
    demo.draw_handwriting(page)  # something else is written: the model is asked again
    more = demo.desk_scene(page)

    def script(n, crop, shape):  # a model that answers the old underline every time it is asked
        return {"occluded": False, "triggers": [{"kind": "underline", "symbol": None, "action": "define", "target": "inertia", "response": "resistance to change in motion"}]}

    engine, brain, session = run([blank, underlined, more], hold=1.8, script=script)
    assert len(brain.calls) == 2, brain.calls
    assert kinds(session) == ["define"], kinds(session)


def test_a_second_spark_by_the_same_problem_gets_a_second_hint():
    page = demo.base_page()
    blank = demo.desk_scene(page)
    demo.draw_spark(page)
    one = demo.desk_scene(page)
    demo.draw_spark(page, center=(700, 440), radius=26)
    two = demo.desk_scene(page)

    def script(n, crop, shape):
        return {"occluded": False, "triggers": [{"kind": "symbol", "symbol": "spark", "action": "hint", "target": "Problem 1", "response": "hint number %d" % n}]}

    engine, brain, session = run([blank, one, two], hold=1.8, script=script)
    assert kinds(session) == ["hint", "hint"], kinds(session)


def _answers_everything(n, crop, shape):
    """A model that reports a spark and an underline every time it is asked."""
    return {"occluded": False, "triggers": [
        {"kind": "symbol", "symbol": "spark", "action": "hint", "target": "Problem 1", "response": "hint number %d" % n},
        {"kind": "underline", "symbol": None, "action": "define", "target": "inertia", "response": "resistance to change in motion"},
    ]}


def test_a_spark_the_first_read_answered_is_not_answered_again():
    """Camera run of Nov 20: a spark drawn while the first read of the sheet was still waiting.

    The read went out with the spark in its picture and gave a hint. The spark was not part of
    the remembered page, so it then counted as new ink and got a second hint.
    """
    page = demo.base_page()
    blank = demo.desk_scene(page)
    demo.draw_spark(page)
    spark = demo.desk_scene(page)
    engine, session, show = _stepper(read_first_page=True)
    engine.brain.script = lambda n, crop, shape: {"occluded": False, "triggers": _answers_everything(n, crop, shape)["triggers"][:1]}
    engine._backoff_until = 1000.0 + 4.0  # the first read has to wait a few seconds
    show(blank, 3)
    assert engine.brain.calls == [] and engine.baseline is not None
    show(spark, 9)
    assert [c["full"] for c in engine.brain.calls] == [True], engine.brain.calls
    assert kinds(session) == ["hint"], kinds(session)


def test_underlines_already_on_a_sheet_are_left_alone():
    """A sheet that arrives with underlines from another day: no definitions until asked for."""
    page = demo.base_page()
    demo.draw_underline(page)
    demo.draw_spark(page)
    marked = demo.desk_scene(page)
    engine, session, show = _stepper(read_first_page=True)
    engine.brain.script = _answers_everything
    show(marked, 4)
    assert [c["full"] for c in engine.brain.calls] == [True], engine.brain.calls
    assert kinds(session) == ["hint"], kinds(session)  # the spark, not the old underline
    engine.look_now()  # the student asks for the whole sheet to be read
    show(marked, 3)
    assert kinds(session) == ["hint", "define"], kinds(session)


def _check(verdict="right", response="That is right. Splitting the weight was the step.", target="Problem 1"):
    return {"kind": "box", "symbol": None, "action": "check", "target": target,
            "work": "a = g sin(30) = 4.9", "verdict": verdict, "response": response}


def test_a_check_mark_gets_a_verdict_and_the_working_stays_off_the_page():
    """A line of working with a check after it (the demo sheet's last step)."""
    s = demo.build_steps()

    def script(n, crop, shape):
        w, h = shape or (0, 0)
        return {"occluded": False, "triggers": [_check()] if crop is not None and w >= 4 * h and h > 30 else []}

    engine, brain, session = run([s["highlights"], s["check"]], hold=1.8, script=script)
    events = session.events_of("check")
    assert len(events) == 1, kinds(session)
    e = events[0]
    assert e["title"] == "Looks right" and e["meta"]["verdict"] == "right", e
    assert "work" not in e["meta"], "the model's own solution must not be sent to the web page"
    kept = list((session.dir / "looks").glob("*_check.txt"))
    assert len(kept) == 1 and "4.9" in kept[0].read_text(), kept
    guide = engine.study_guide()
    assert "Answers you checked" in guide and "**Looks right.**" in guide, guide


def test_a_second_check_by_the_same_problem_is_answered_again():
    """ "Not yet", the student tries again and draws another check: answered, even in the same words."""
    page = demo.base_page()
    blank = demo.desk_scene(page)
    demo.draw_check(page, (640, 440))
    one = demo.desk_scene(page)
    demo.draw_check(page, (720, 462))
    two = demo.desk_scene(page)

    def script(n, crop, shape):
        return {"occluded": False, "triggers": [_check("wrong", "Not right yet. Look at the second line again.")]}

    engine, brain, session = run([blank, one, two], hold=1.8, script=script)
    assert [e["title"] for e in session.events_of("check")] == ["Not yet", "Not yet"], kinds(session)
    assert "verdict wrong" in brain.calls[-1]["context"], brain.calls[-1]["context"]  # the model is told what it said before


def test_a_check_drawn_before_the_sheet_was_taken_in_is_answered():
    """Nov 21: the first check of the session was drawn while Glyph was still getting a steady
    view of the sheet, and got no answer."""
    page = demo.base_page()
    demo.draw_boxed_answer(page)
    marked = demo.desk_scene(page)
    engine, session, show = _stepper(read_first_page=True)
    engine.brain.script = lambda n, crop, shape: {"occluded": False, "triggers": [_check()]}
    show(marked, 4)
    assert [c["full"] for c in engine.brain.calls] == [True], engine.brain.calls
    assert kinds(session) == ["check"], kinds(session)
    show(marked, 6)
    assert kinds(session) == ["check"] and len(engine.brain.calls) == 1, "answered once, and not looked at again"


def test_a_sheet_covered_in_ticks_is_left_alone():
    """A marked sheet (a teacher's ticks): nothing until the student asks for it to be read."""
    page = demo.base_page()
    demo.draw_boxed_answer(page)
    marked = demo.desk_scene(page)
    engine, session, show = _stepper(read_first_page=True)
    about = ["the block on the incline", "the pulley", "momentum of the cart", "energy at the top"]
    engine.brain.script = lambda n, crop, shape: {"occluded": False, "triggers": [_check(target=t) for t in about]}
    show(marked, 4)
    assert kinds(session) == [], kinds(session)
    assert "asked for the whole page" not in engine.brain.calls[0]["context"]
    engine.look_now()  # the student asks for the whole sheet to be read
    show(marked, 3)
    assert kinds(session) == ["check"] * 4, kinds(session)
    assert "asked for the whole page" in engine.brain.calls[-1]["context"]


def test_a_check_without_a_clear_verdict_is_never_right():
    from glyph.brain import build_system_prompt, clean_result

    legend = config.legend_for(config.load_legend(), "student")  # where a box round an answer checks it

    def one(legend=legend, **kw):
        t = dict(kind="box", symbol=None, action="check", target="p1", response="ok")
        t.update(kw)
        return clean_result({"triggers": [t]}, legend)["triggers"]

    assert one(verdict="Right")[0]["verdict"] == "right"
    assert one(verdict="incorrect")[0]["verdict"] == "wrong"
    assert one(verdict="probably")[0]["verdict"] == "unsure"
    assert one()[0]["verdict"] == "unsure"
    # Where a box does not check answers (editor mode), the action is not accepted and not asked for.
    bare = config.legend_for(config.load_legend(), "editor")
    assert one(legend=bare, verdict="right") == []
    assert '"verdict"' in build_system_prompt(legend) and '"verdict"' not in build_system_prompt(bare)


def test_the_demo_ends_with_a_checked_answer():
    from glyph.brain import MockBrain

    engine, session, show = _stepper()
    engine.brain = MockBrain(engine.legend, demo=True)
    for frame in demo.demo_frames():
        show(frame, 5)
    assert kinds(session) == ["hint", "define", "highlight", "highlight", "check", "practice", "answer"], kinds(session)
    assert session.events_of("check")[0]["title"] == "Looks right"
    assert session.events_of("practice")[0]["title"] == "Try this one"
    assert session.events_of("answer")[0]["title"] == "Answer" and "4.9" in session.events_of("answer")[0]["body"]
    guide = engine.study_guide()
    assert "Problems to try" in guide and "Worked answers" in guide, guide


def test_a_short_underline_right_under_a_small_word_is_looked_at():
    """Camera run of Nov 20: "ball" in small print, underlined close to the letters, got no look.

    Ink within a few pixels of print is never counted as new, so what was left of the line was
    under the size at which a look is sent.
    """
    from glyph import page as P

    page = demo.base_page()
    blank = demo.desk_scene(page)
    x0, x1, y = demo._word_span(1, "net")
    cv2.line(page, (x0, y + 7), (x0 + 24, y + 7), demo.PEN, 2, cv2.LINE_AA)
    lined = demo.desk_scene(page)
    new = P.remove_small(P.new_ink(P.ink_strength(_page_of(lined)), P.ink_strength(_page_of(blank))), 8)
    assert 0 < cv2.countNonZero(new) < config.MIN_NEW_INK_PX, cv2.countNonZero(new)  # too little for the old rule
    engine, brain, session = run([blank, lined], hold=1.8)
    assert len(brain.calls) == 1 and not brain.calls[0]["full"], brain.calls
    assert kinds(session) == ["define"], kinds(session)


def test_a_pale_thin_highlight_over_small_print_is_found():
    """Camera run of Nov 20: one line of small print in pale green highlighter was not saved.

    The stroke was 13 pixels tall, broken up by the letters, and half of it was paler than the
    color range allows. Paler parts now count when they are joined to a part that is in range.
    """
    from glyph.highlights import detect_highlights

    page = np.full((demo.PAGE_H, demo.PAGE_W, 3), 236, np.uint8)
    x0, x1, y0, y1 = 140, 580, 500, 513
    fade = np.linspace(0.0, 1.0, x1 - x0, dtype=np.float32)[None, :, None]
    strong, pale = np.array([0.74, 1.0, 0.80], np.float32), np.array([0.87, 1.0, 0.91], np.float32)
    page[y0:y1, x0:x1] = (page[y0:y1, x0:x1].astype(np.float32) * (strong * (1 - fade) + pale * fade)).astype(np.uint8)
    for i, line in enumerate(["A ball is thrown and follows the parabolic path shown above. Air friction", "point on the path. Points P and R are the same height above the ground."]):
        cv2.putText(page, line, (144, 510 + 17 * i), demo.FONT, 0.36, demo.INK, 1, cv2.LINE_AA)
    page = cv2.GaussianBlur(page, (3, 3), 0)
    regions, mask = detect_highlights(page)
    assert [r["color"] for r in regions] == ["green"], regions
    x, y, w, h = regions[0]["bbox"]
    assert x <= x0 + 12 and x + w >= x1 - 45 and h <= 22, regions  # nearly the whole stroke, pale end included
    plain = np.full((demo.PAGE_H, demo.PAGE_W, 3), 236, np.uint8)
    plain[:, :, 0] = 228  # paper under a warm lamp is not a highlight
    assert detect_highlights(plain)[0] == []


def test_pages_are_numbered_in_order_and_keep_their_number():
    from glyph import page as P
    from glyph.highlights import HighlightStore

    quad, _ = find_page_quad(demo.build_steps()["blank"])
    first = P.page_signature(_page("blank"))
    second = P.page_signature(warp_page(demo.desk_scene(_second_sheet()), quad))
    empty = P.page_signature(np.full((demo.PAGE_H, demo.PAGE_W, 3), 244, np.uint8))
    store = HighlightStore(Path(tempfile.mkdtemp(prefix="glyph_pg_")), {})
    seen = []
    for sig in (first, second, first, np.ascontiguousarray(first[::-1, ::-1]), empty, empty):
        store.new_page()
        assert store.page_no == 0, "no number until the sheet has been looked at"
        known = store.identify(sig)
        seen.append((store.page_no, known))
    # sheet 1, sheet 2, sheet 1 again, sheet 1 the other way up, a blank sheet, a blank sheet again
    assert seen == [(1, False), (2, False), (1, True), (1, True), (3, False), (3, False)], seen
    assert store.pages() == [1, 2, 3]
    assert store.merge(2) == 3 and store.page_no == 2 and store.pages() == [1, 2]  # "this is page 2"
    store.turn()  # the view was turned a quarter turn: sheets are still recognised
    store.new_page()
    turned = P.page_signature(np.ascontiguousarray(np.rot90(_page("blank"))))  # the page as it is seen after Rotate
    assert store.identify(turned) and store.page_no == 1


def test_rotate_keeps_the_page_number():
    """Camera run of Nov 20: the sheet became "page 2" when the view was turned upright."""
    s = demo.build_steps()
    engine, session, show = _stepper(read_first_page=True)
    show(s["blank"], 3)
    assert engine.store.page_no == 1 and len(engine.brain.calls) == 1, (engine.store.page_no, engine.brain.calls)
    engine.rotate()
    show(s["blank"], 4)
    assert engine.status()["view"]["page_size"] == [demo.PAGE_H, demo.PAGE_W] or engine._shape[0] < engine._shape[1], engine._shape
    assert engine.store.page_no == 1 and engine.store.pages() == [1], engine.store.pages()
    assert len(engine.brain.calls) == 1, "the same sheet is not read in full a second time"


# ---- Nov 21: a sheet in a warm shadow, and the picture of the mark on the card ---------------------


def test_a_sheet_in_a_warm_shadow_is_still_a_sheet():
    from glyph.page import PAPER_SAT, find_sheet

    page = demo.base_page()
    clear, info = demo.desk_scene(page, desk_color=demo.WOOD), {}
    quad, clean = find_sheet(clear, info)[:2]
    assert clean and info["sat_limit"] == PAPER_SAT, info  # in ordinary light nothing changes
    for top in (0, 360):  # the whole sheet in shadow, and the lower two thirds
        info = {}
        shaded, is_clean = find_sheet(demo.desk_scene(demo.warm_shadow(page, top), desk_color=demo.WOOD), info)[:2]
        assert is_clean and info["sat_limit"] > PAPER_SAT, (top, is_clean, info)
        assert float(np.abs(shaded - quad).max()) < 12, (top, shaded, quad)  # and it is the same outline
    # A bare wooden desk is not split into "paper" and "desk".
    bare, info = demo.desk_scene(page, desk_color=demo.WOOD, corners=[[3000, 3000], [3100, 3000], [3100, 3100], [3000, 3100]]), {}
    assert not find_sheet(bare, info)[1] and info["sat_limit"] == PAPER_SAT, info


def test_a_mark_drawn_in_a_warm_shadow_is_read():
    """Nov 21: leaning over the sheet to write on its last question turned the paper beige. The
    sheet was "not in view", and when it was found again the new check marks counted as old."""
    for top in (0, 450):  # the whole sheet in shadow, and the part below the working
        page = demo.base_page()
        clear = demo.desk_scene(page, desk_color=demo.WOOD)
        demo.draw_spark(page)
        shaded = demo.desk_scene(demo.warm_shadow(page, top), desk_color=demo.WOOD)
        engine, session, show = _stepper()
        show(clear, 3)
        show(shaded, 5)
        status = engine.status()
        assert kinds(session) == ["hint"], (top, kinds(session), status["text"])
        assert status["view"]["phase"] == "watching" and status["page_no"] == 1, (top, status["text"])
        # A forearm across the shaded sheet (skin, as dark and warm as that light makes it) is
        # still an object: the print under it is hidden.
        show(demo.add_hand(shaded, skin=(70, 105, 160)), 3)
        assert engine.status()["view"]["covers"], (top, engine.status()["text"])


def test_the_card_shows_the_one_mark_that_was_answered():
    """Nov 21: the picture took in the circled letter, the check mark and two older checks."""
    from glyph.page import ink_mask, pick_mark

    blank = np.full((1100, 850, 3), 244, np.uint8)

    def drawn(*draw):
        sheet = blank.copy()
        for d in draw:
            d(sheet)
        return ink_mask(sheet)

    circle = lambda im: cv2.ellipse(im, (150, 400), (30, 24), 0, 0, 360, demo.PEN, 3, cv2.LINE_AA)
    check = lambda im: demo.draw_check(im, (640, 520), 60)
    spark = lambda im: demo.draw_spark(im, (600, 300), 28)
    words = lambda im: demo.draw_handwriting(im, "a = F / m", (120, 300))
    under = lambda im: cv2.line(im, (300, 700), (400, 701), demo.PEN, 3, cv2.LINE_AA)
    box = lambda im: cv2.rectangle(im, (500, 800), (600, 840), demo.PEN, 3, cv2.LINE_AA)

    def inside(found, x, y):
        return found[0] <= x <= found[2] and found[1] <= y <= found[3]

    both = drawn(circle, check)
    got = pick_mark(both, "answer")
    assert inside(got, 650, 500) and not inside(got, 150, 400), got  # the check mark, not the circled letter
    got = pick_mark(drawn(check, box), "check")
    assert inside(got, 550, 820) and not inside(got, 650, 500), got  # checking an answer: the box round it
    got = pick_mark(both, "synonym")
    assert inside(got, 150, 400) and not inside(got, 650, 500), got  # asked about a circle: the circle
    got = pick_mark(drawn(words, spark), "hint")
    assert inside(got, 600, 300) and got[0] > 450, got  # the spark, not the line of working
    got = pick_mark(drawn(circle, under), "define")
    assert inside(got, 350, 700) and got[3] - got[1] < 20, got
    got = pick_mark(drawn(check, box), "find")
    assert inside(got, 550, 820) and not inside(got, 650, 500), got
    assert pick_mark(np.zeros((1100, 850), np.uint8), "check") is None

    # End to end: a circled letter far to the left and a check mark far to the right. The picture
    # saved for the card is a close one of the check: no circle in it, and the tick fills a good part.
    page = demo.base_page()
    scene0 = demo.desk_scene(page)
    cv2.ellipse(page, (120, 900), (30, 22), 0, 0, 360, demo.PEN, 3, cv2.LINE_AA)  # in the blank foot of the sheet
    demo.draw_check(page, (650, 960), 60)
    engine, brain, session = run([scene0, demo.desk_scene(page)], hold=1.8, script=lambda n, crop, shape: {"occluded": False, "triggers": [_check()] if crop is not None else []})
    events = session.events_of("check")
    assert len(events) == 1 and events[0]["meta"].get("snip"), kinds(session)
    snip = cv2.imread(str(session.dir / "snips" / "{}.jpg".format(events[0]["meta"]["snip"])), cv2.IMREAD_GRAYSCALE)
    dark = snip < 140
    assert snip.shape == (360, 540) and dark[:, 180:400].sum() > 300, dark.sum()
    cols = np.where(dark.any(axis=0))[0]
    assert cols.max() - cols.min() > 100 and cols.min() > 60, (cols.min(), cols.max())  # one mark, large, with clear paper round it


# ---- student mode and editor mode --------------------------------------------------------------


def test_each_mode_has_its_own_marks():
    from glyph.brain import build_system_prompt, clean_result

    legend = config.load_legend()
    student, editor = config.legend_for(legend, "student"), config.legend_for(legend, "editor")
    assert [m["id"] for m in config.modes_of(legend)] == ["student", "editor"]
    assert config.actions_of(student) == ["hint", "explain", "define", "answer", "check", "practice"], config.actions_of(student)
    assert student["marks"]["box"] == "check" and editor["marks"]["box"] == "find"  # one mark, a job per mode
    assert [m["label"] for m in config.modes_of(legend)] == ["STEM", "Humanities"]
    assert config.mode_id(legend, "stem") == "student" and config.mode_id(legend, "Humanities") == "editor" and config.mode_id(legend, "x") == ""
    assert config.actions_of(editor) == ["explain", "define", "find", "synonym", "summarize"], config.actions_of(editor)
    assert editor["order"] == ["define", "find", "synonym", "summarize", "explain"], editor["order"]
    # The model is only told about the marks of the mode that is on, and only those come back.
    told = build_system_prompt(editor)
    assert '"box"' in told and '"margin line"' in told and '"spark"' not in told and '"verdict"' not in told
    assert '"find"' not in build_system_prompt(student) and '"answer"' in build_system_prompt(student)
    raw = {"triggers": [
        {"kind": "symbol", "symbol": "spark", "action": "hint", "target": "p1", "response": "a hint"},
        {"kind": "box", "action": "find", "target": "heat", "response": "", "places": [{"box_2d": [100, 200, 130, 260]}]},
        {"kind": "Margin_Line", "action": "summarize", "target": "The effect is", "response": "short"},
        {"kind": "circle", "action": "find", "target": "x", "response": "a circle does not find"},
    ]}
    assert [(t["kind"], t["action"]) for t in clean_result(raw, editor)["triggers"]] == [("box", "find"), ("margin line", "summarize")]
    assert [t["action"] for t in clean_result(raw, student)["triggers"]] == ["hint"]
    # A legend with no modes works as before: every mark, one mode.
    plain = {k: v for k, v in legend.items() if k != "modes"}
    assert config.modes_of(plain) == [] and len(config.actions_of(config.legend_for(plain, "student"))) == 8  # (no check: without modes a box finds)


def test_found_places_must_be_the_size_of_a_word():
    from glyph.brain import clean_result

    editor = config.legend_for(config.load_legend(), "editor")
    places = [
        {"box_2d": [100, 200, 130, 260]},      # on the 0 to 1000 scale
        {"box_2d": [0.5, 0.2, 0.53, 0.26]},    # a model that answers from 0 to 1
        {"box_2d": [0, 0, 900, 900]},          # most of the page: not a word
        {"box_2d": "here"},                    # not a box at all
    ]
    t = clean_result({"triggers": [{"kind": "box", "action": "find", "target": "heat", "response": "", "places": places}]}, editor)["triggers"][0]
    assert t["count"] == 4 and t["places"] == [[0.2, 0.1, 0.26, 0.13], [0.2, 0.5, 0.26, 0.53]], t


def test_editor_demo_box_circle_and_margin_line():
    """The reading sheet: an underline, a box (find), a circle (synonyms), a highlight, a margin line."""
    from glyph.brain import MockBrain

    s = demo.build_reading_steps()
    engine, session, show = _stepper()
    engine.brain = MockBrain(engine.legend, demo=True)
    assert engine.set_mode("editor") == "editor"
    for step in ("blank", "underline", "box"):
        show(s[step], 5)
    assert kinds(session) == ["define", "find"], kinds(session)
    find = session.events_of("find")[0]
    assert find["title"] == "Find: heat" and find["meta"]["count"] == 6 and "6 more times" in find["body"], find
    # The six other places are sent to the web page as boxes on the page, and as they lie on the desk.
    view = engine.status()["view"]
    assert view["found_term"] == "heat" and len(view["found"]) == 6 and len(view["cam"]["found"]) == 6, view
    want = [[x0 / 1000.0, y0 / 1000.0, x1 / 1000.0, y1 / 1000.0] for y0, x0, y1, x1 in demo.reading_places("heat")]
    assert max(abs(a - b) for got, exp in zip(view["found"], want) for a, b in zip(got, exp)) < 0.002
    for step in ("circle", "highlight", "margin"):
        show(s[step], 5)
    assert kinds(session) == ["define", "find", "synonym", "highlight", "summarize"], kinds(session)
    assert engine.status()["view"]["found"] == [], "a newer answer takes the outlines away"
    guide = engine.study_guide()
    assert "## Synonyms" in guide and "**exacerbate**" in guide and "## Summaries" in guide, guide
    # The close-up for the margin line runs the width of the page, so the passage is in it.
    import cv2 as _cv2

    looks = sorted((session.dir / "looks").glob("*_new_ink.jpg"))
    assert _cv2.imread(str(looks[-1])).shape[1] >= 850, _cv2.imread(str(looks[-1])).shape


def test_marks_on_words_already_on_a_sheet_are_left_alone_in_editor_mode():
    page = demo.reading_page()
    demo.draw_box(page)
    marked = demo.desk_scene(page)
    engine, session, show = _stepper(read_first_page=True)
    engine.set_mode("editor")
    engine.brain.script = lambda n, crop, shape: {"occluded": False, "triggers": [
        {"kind": "box", "symbol": None, "action": "find", "target": "heat", "response": "", "count": 2, "places": []},
        {"kind": "symbol", "symbol": "circled question mark", "action": "explain", "target": "paragraph 1", "response": "In plain words."},
    ]}
    show(marked, 4)
    assert [(c["full"], c["mode"]) for c in engine.brain.calls] == [(True, "editor")], engine.brain.calls
    # Nothing: the old box, and the question mark too. A printed question mark on a page of
    # reading passed for a drawn one (Nov 22), so question marks wait like marks on words do.
    assert kinds(session) == [], kinds(session)
    engine.look_now()
    show(marked, 3)
    assert kinds(session) == ["find", "explain"], kinds(session)
    assert session.events_of("find")[0]["body"] == "It appears 2 more times on this page.", session.events_of("find")[0]["body"]


def test_switching_mode_reads_nothing_and_the_next_mark_is_read_in_the_new_mode():
    s = demo.build_steps()
    engine, session, show = _stepper()
    show(s["blank"], 3)
    assert engine.status()["work_mode"] == "student" and len(engine.status()["modes"]) == 2
    assert engine.set_mode("editor") == "editor" and engine.set_mode("no such mode") == "editor"
    show(s["blank"], 4)
    assert engine.brain.calls == [], "switching mode must not spend a request"
    show(s["spark"], 4)
    assert [c["mode"] for c in engine.brain.calls] == ["editor"], engine.brain.calls
    assert engine.legend_now()["mode"] == "editor" and "box" in engine.legend_now()["marks"]


def test_no_keep_going_card_in_editor_mode():
    s = demo.build_steps()
    engine, session, show = _stepper(stuck_seconds=20)
    engine.set_mode("editor")
    show(s["blank"], 60)
    assert "nudge" not in kinds(session), kinds(session)
    engine.set_mode("student")  # back to problems: the wait starts from here
    show(s["blank"], 12)
    assert "nudge" not in kinds(session), kinds(session)
    show(s["blank"], 15)
    assert kinds(session).count("nudge") == 1, kinds(session)


def test_demo_puts_the_other_sheet_under_the_camera_and_comes_back_where_it_was():
    from glyph.camera import DemoSource

    a0, a1, b0, b1 = [np.full((4, 4, 3), v, np.uint8) for v in (10, 20, 30, 40)]
    src = DemoSource({"student": [a0, a1], "editor": [b0, b1]}, "student", hold=0.2)
    src.start()
    assert src.read() is a0
    time.sleep(0.25)
    assert src.read() is a1
    src.set_mode("editor")
    assert src.read() is b0
    time.sleep(0.25)
    assert src.read() is b1
    src.set_mode("student")
    assert src.read() is a1, "the first sheet is shown as it was left, not from the start"


def test_the_turn_of_the_page_view_is_kept_for_the_next_start():
    """Nov 21: after a restart the page was on its side again, and was read that way."""
    from fastapi.testclient import TestClient
    from glyph.app import create_app

    was = config.VIEW_FILE
    config.VIEW_FILE = Path(tempfile.mkdtemp(prefix="glyph_view_")) / "view.json"
    try:
        assert config.saved_rotation() == 0  # nothing saved yet
        s = demo.build_steps()
        engine, brain, session = run([s["blank"]], hold=1.0)
        client = TestClient(create_app(engine))
        assert client.post("/api/rotate").json()["degrees"] == 90
        assert config.saved_rotation() == 0, "pictures from a file or the demo are not the camera: nothing is kept"
        engine.source.label = "camera 0"
        assert client.post("/api/rotate").json()["degrees"] == 180
        assert config.saved_rotation() == 180
        config.VIEW_FILE.write_text("not json")
        assert config.saved_rotation() == 0
    finally:
        config.VIEW_FILE = was


def test_web_page_switches_mode():
    from fastapi.testclient import TestClient
    from glyph.app import create_app

    s = demo.build_steps()
    engine, brain, session = run([s["blank"]], hold=1.2)
    client = TestClient(create_app(engine))
    assert 'id="modes"' in client.get("/").text
    state = client.get("/api/state").json()
    assert state["status"]["work_mode"] == "student" and state["legend"]["mode"] == "student", state["status"]
    r = client.post("/api/mode", json={"mode": "editor"})
    assert r.status_code == 200 and r.json()["mode"] == "editor" and r.json()["legend"]["order"][0] == "define", r.text
    state = client.get("/api/state").json()
    assert state["status"]["work_mode"] == "editor" and "box" in state["legend"]["marks"], state["legend"]
    assert client.post("/api/mode", json={"mode": "x"}).status_code == 400


def test_web_page_carries_the_name_and_the_page_numbers():
    from fastapi.testclient import TestClient
    from glyph.app import create_app

    s = demo.build_steps()
    engine, brain, session = run([s["blank"]], hold=1.2)
    client = TestClient(create_app(engine))
    html = client.get("/").text
    assert "__NAME__" not in html and "<title>%s</title>" % config.APP_NAME in html
    status = client.get("/api/state").json()["status"]
    assert status["page_no"] == 1 and status["pages"] == [1], status
    view = status["view"]
    assert view["phase"] in ("watching", "settling") and len(view["quad"]) == 4 and view["page_size"] == [850, 1100], view
    assert client.post("/api/page", json={"same_as": 1}).status_code == 200
    assert client.post("/api/page", json={"same_as": "x"}).status_code == 400


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
