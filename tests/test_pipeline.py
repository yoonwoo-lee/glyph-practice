"""End-to-end checks on simulated camera frames. No camera or key needed.

    python -m tests.test_pipeline
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from glyph import config, demo  # noqa: E402
from glyph.camera import FrameListSource  # noqa: E402
from glyph.engine import Engine, Settings  # noqa: E402
from glyph.page import find_page_quad  # noqa: E402
from glyph.session import Session  # noqa: E402

FAST = dict(settle=0.3, cooldown=0.2, big_hold=0.8, tick=0.05, max_calls_per_min=100, read_first_page=False)


class ScriptedBrain:
    """Answers by the shape of the new ink, and records every call."""

    name = "scripted"

    def __init__(self, legend, script=None):
        self.legend = legend
        self.script = script
        self.calls = []

    def analyze(self, page_jpg, crop_jpg=None, context="", shape_hint=None, mode=""):
        self.calls.append({"full": crop_jpg is None, "shape": shape_hint, "context": context, "mode": mode})
        if self.script is not None:
            return self.script(len(self.calls), crop_jpg, shape_hint)
        if crop_jpg is None or not shape_hint:
            return {"occluded": False, "triggers": []}
        w, h = shape_hint
        if w >= 5 * h:
            return {"occluded": False, "triggers": [{"kind": "underline", "symbol": None, "action": "define", "target": "inertia", "response": "resistance to change in motion"}]}
        if 0.5 <= w / max(h, 1) <= 2 and max(w, h) <= 160:
            return {"occluded": False, "triggers": [{"kind": "symbol", "symbol": "spark", "action": "hint", "target": "Problem 1", "response": "Which component of gravity points along the incline?"}]}
        return {"occluded": False, "triggers": []}

    def study_guide(self, items):
        return "\n".join("## {}\n- text {}".format(it["label"], i) for i, it in enumerate(items, 1))


def run(frames, hold=1.6, script=None, extra=0.0, **overrides):
    legend = config.load_legend()
    brain = ScriptedBrain(legend, script)
    session = Session(Path(tempfile.mkdtemp(prefix="glyph_test_")))
    settings = Settings(**dict(FAST, **overrides))
    source = FrameListSource(frames, hold=hold)
    engine = Engine(source, brain, session, legend, settings=settings)
    source.start()
    engine.start()
    time.sleep(hold * len(frames) + extra)
    engine.running = False
    time.sleep(0.2)
    return engine, brain, session


def kinds(session):
    return [e["kind"] for e in session.events_since(0)]


def test_full_flow():
    s = demo.build_steps()
    engine, brain, session = run([s["blank"], s["spark"], s["underline"], s["highlights"]])
    k = kinds(session)
    assert k.count("hint") == 1, k
    assert k.count("define") == 1, k
    assert k.count("highlight") == 2, k
    assert len(brain.calls) == 2, "highlighting must not trigger a look: %r" % brain.calls
    colors = sorted(e["meta"]["color"] for e in session.events_of("highlight"))
    assert colors == ["green", "yellow"], colors
    guide = engine.study_guide()
    assert "## Key ideas" in guide and "## Definitions" in guide, guide
    assert "Words you looked up" in guide and "inertia" in guide, guide
    assert "Where you asked for help" in guide, guide
    assert (session.dir / "study_guide.md").exists()
    assert (session.dir / "looks" / "001_new_ink.jpg").exists()


def test_half_drawn_symbol_is_seen_whole():
    page = demo.base_page()
    blank = demo.desk_scene(page)
    cx, cy, r = 640, 330, 30
    cv2.line(page, (cx - r, cy - 4), (cx + r, cy + 4), demo.PEN, 3, cv2.LINE_AA)  # one stroke only
    half = demo.desk_scene(page)
    demo.draw_spark(page, (cx, cy), r)
    whole = demo.desk_scene(page)

    def script(n, crop, shape):
        if n == 1:
            return {"occluded": False, "triggers": []}  # too early to tell
        return {"occluded": False, "triggers": [{"kind": "symbol", "symbol": "spark", "action": "hint", "target": "p1", "response": "hint"}]}

    engine, brain, session = run([blank, half, whole], script=script, recent=30)
    assert len(brain.calls) == 2, brain.calls
    w, h = brain.calls[1]["shape"]
    assert w > 50 and h > 50, "second look must show the whole symbol, got %r" % (brain.calls[1]["shape"],)
    assert kinds(session).count("hint") == 1


def test_hand_does_not_trigger_and_symbol_still_found():
    s = demo.build_steps()
    hand = demo.add_hand(s["blank"])
    engine, brain, session = run([s["blank"], hand, s["spark"]], hold=1.4)
    assert len(brain.calls) == 1 and not brain.calls[0]["full"], brain.calls
    w, h = brain.calls[0]["shape"]
    assert abs(w - 64) <= 2 and abs(h - 64) <= 2, brain.calls  # just the spark
    assert kinds(session) == ["hint"], kinds(session)


def test_symbol_is_read_while_a_hand_rests_elsewhere():
    s = demo.build_steps()
    engine, brain, session = run([s["blank"], demo.add_hand(s["blank"]), demo.add_hand(s["spark"])], hold=1.4)
    assert len(brain.calls) == 1, brain.calls
    w, h = brain.calls[0]["shape"]
    assert max(w, h) <= 80, "only the symbol should be shown, not the hand: %r" % (brain.calls[0]["shape"],)
    assert kinds(session) == ["hint"], kinds(session)


def test_object_left_on_page_is_accepted_after_a_while():
    s = demo.build_steps()
    hand = demo.add_hand(s["highlights"])
    engine, brain, session = run([s["highlights"], hand], hold=2.4, cover_hold=0.8)
    assert [c["full"] for c in brain.calls] == [True], brain.calls
    assert kinds(session).count("highlight") == 2, "highlights must not be saved twice: %r" % kinds(session)


def test_new_sheet_gets_one_full_look():
    first = demo.desk_scene(demo.base_page())
    page = np.full((demo.PAGE_H, demo.PAGE_W, 3), 244, np.uint8)
    for i in range(14):
        cv2.putText(page, "A completely different page of notes, line %d." % i, (60, 120 + 60 * i), demo.FONT, 0.8, demo.INK, 2, cv2.LINE_AA)
    second = demo.desk_scene(page)
    engine, brain, session = run([first, second], hold=2.2, big_hold=0.6)
    assert [c["full"] for c in brain.calls] == [True], brain.calls
    assert engine.store.page_no >= 1


def test_nudged_paper_is_not_new_ink():
    page = demo.base_page()
    engine, brain, session = run([demo.desk_scene(page), demo.desk_scene(page, shift=(9, 6))])
    assert brain.calls == [], brain.calls


def test_writing_that_got_no_answer_ages_out_of_the_close_up():
    page = demo.base_page()
    blank = demo.desk_scene(page)
    demo.draw_handwriting(page)
    written = demo.desk_scene(page)
    demo.draw_spark(page)
    spark = demo.desk_scene(page)

    def script(n, crop, shape):
        if n == 1:
            return {"occluded": False, "triggers": []}  # just handwriting
        return {"occluded": False, "triggers": [{"kind": "symbol", "symbol": "spark", "action": "hint", "target": "p1", "response": "hint"}]}

    engine, brain, session = run([blank, written, spark], hold=1.6, recent=0.5, script=script)
    assert len(brain.calls) == 2, brain.calls
    w, h = brain.calls[1]["shape"]
    assert max(w, h) <= 90, "old handwriting should have aged out, got %r" % (brain.calls[1]["shape"],)
    assert kinds(session) == ["hint"], kinds(session)


def test_full_look_does_not_repeat_answers():
    s = demo.build_steps()
    trigger = {"kind": "symbol", "symbol": "spark", "action": "hint", "target": "Problem 1. A 2.0 kg block", "response": "hint"}

    def script(n, crop, shape):
        t = dict(trigger)
        if n > 1:
            t["target"] = "Problem 1: A 2.0 kg block"  # read slightly differently
        return {"occluded": False, "triggers": [t]}

    legend = config.load_legend()
    brain = ScriptedBrain(legend, script)
    session = Session(Path(tempfile.mkdtemp(prefix="glyph_test_")))
    source = FrameListSource([s["spark"]], hold=10)
    engine = Engine(source, brain, session, legend, settings=Settings(**FAST))
    source.start()
    engine.start()
    time.sleep(0.8)
    engine.look_now()
    time.sleep(0.8)
    engine.look_now()
    time.sleep(0.8)
    engine.running = False
    assert len(brain.calls) == 2 and all(c["full"] for c in brain.calls), brain.calls
    assert kinds(session) == ["hint"], kinds(session)


def test_blocked_view_waits_for_movement_then_looks_again():
    s = demo.build_steps()

    def script(n, crop, shape):
        if n == 1:
            return {"occluded": True, "triggers": []}  # "a hand is in the way"
        return {"occluded": False, "triggers": [{"kind": "symbol", "symbol": "spark", "action": "hint", "target": "p1", "response": "hint"}]}

    engine, brain, session = run([s["blank"], s["spark"], s["spark"], demo.add_hand(s["spark"]), s["spark"]], hold=1.2, script=script)
    assert len(brain.calls) == 2, brain.calls
    assert kinds(session) == ["hint"], kinds(session)


def test_model_error_is_reported_once_and_retried_later():
    s = demo.build_steps()

    def script(n, crop, shape):
        raise RuntimeError("503 UNAVAILABLE")

    engine, brain, session = run([s["blank"], s["spark"]], hold=1.5, script=script)
    assert kinds(session) == ["error"], kinds(session)
    assert len(brain.calls) == 1, "must back off instead of hammering: %r" % len(brain.calls)
    assert engine.status()["text"] == "Waiting to retry the vision model", engine.status()


def test_no_sheet_falls_back_to_whole_frame():
    white_desk = np.full((1080, 1920, 3), 240, np.uint8)
    quad, clean = find_page_quad(white_desk)
    assert quad is None
    page = cv2.resize(demo.base_page(), (1485, 1920))[:1080, :]  # paper fills the frame
    quad, clean = find_page_quad(np.ascontiguousarray(page))
    assert quad is None



def _stepper(**overrides):
    """An engine that is not running: the test feeds it pictures and says what time it is."""
    legend = config.load_legend()
    session = Session(Path(tempfile.mkdtemp(prefix="glyph_test_")))
    engine = Engine(None, ScriptedBrain(legend), session, legend, settings=Settings(**dict(FAST, **overrides)))
    clock = [1000.0]

    def show(frame, seconds):
        end = clock[0] + seconds
        while clock[0] < end:
            engine._tick(frame, clock[0])
            clock[0] += 0.5
            for _ in range(40):  # let a model call finish, as it would between two real pictures
                if not engine._busy or not engine._results.empty():
                    break
                time.sleep(0.05)

    return engine, session, show


def test_first_look_at_a_sheet_is_not_called_reading_a_mark():
    """The web page says "Taking in the page" for the read of a new sheet, "Reading your mark" for a mark."""
    s = demo.build_steps()
    engine, session, show = _stepper(read_first_page=True)
    said = []
    plain = ScriptedBrain(engine.legend)

    def script(n, crop, shape):
        said.append(engine._reading)
        return plain.analyze(b"", crop, shape_hint=shape)

    engine.brain.script = script
    show(s["blank"], 6)
    show(s["spark"], 8)
    assert said == ["page", "mark"], said
    assert kinds(session) == ["hint"] and engine.status()["reading"] is None, (kinds(session), engine.status()["reading"])


def test_stuck_nudge_once_per_pause():
    s = demo.build_steps()
    engine, session, show = _stepper(stuck_seconds=20)
    show(s["blank"], 15)
    assert kinds(session).count("nudge") == 0, kinds(session)  # not yet
    show(s["blank"], 10)
    assert kinds(session).count("nudge") == 1, kinds(session)
    show(s["blank"], 60)
    assert kinds(session).count("nudge") == 1, kinds(session)  # waiting longer: still one
    nudge = [e for e in session.events_since(0) if e["kind"] == "nudge"][0]
    assert nudge["title"] == "Still with it?" and nudge["body"]


def test_stuck_nudge_again_after_new_writing():
    s = demo.build_steps()
    engine, session, show = _stepper(stuck_seconds=20)
    show(s["blank"], 30)
    assert kinds(session).count("nudge") == 1, kinds(session)
    show(s["spark"], 15)  # the student writes: the clock starts again
    assert "hint" in kinds(session), kinds(session)
    assert kinds(session).count("nudge") == 1, kinds(session)
    show(s["spark"], 30)
    assert kinds(session).count("nudge") == 2, kinds(session)
    bodies = [e["body"] for e in session.events_since(0) if e["kind"] == "nudge"]
    assert bodies[0] != bodies[1], bodies


def test_stuck_nudge_waits_while_the_page_is_covered():
    s = demo.build_steps()
    engine, session, show = _stepper(stuck_seconds=20, cover_hold=300)
    show(s["blank"], 5)
    show(demo.add_hand(s["blank"]), 40)
    assert kinds(session).count("nudge") == 0, kinds(session)
    show(s["blank"], 5)  # hand gone, and it has been long enough
    assert kinds(session).count("nudge") == 1, kinds(session)


def test_stuck_nudge_can_be_turned_off():
    s = demo.build_steps()
    engine, session, show = _stepper(stuck_seconds=0)
    show(s["blank"], 120)
    assert "nudge" not in kinds(session), kinds(session)


def test_camera_view_gets_the_same_boxes_as_the_page_view():
    """Highlights are also sent as they lie in the camera picture; mapped back they match the page."""
    from glyph.page import page_matrix

    s = demo.build_steps()
    fh, fw = s["blank"].shape[:2]
    for turns in (0, 1):
        engine, session, show = _stepper()
        engine._rotate = turns
        show(s["blank"], 3)
        show(s["highlights"], 6)
        v = engine.status()["view"]
        pw, ph = v["page_size"]
        assert v["cam"] and len(v["cam"]["highlights"]) == len(v["highlights"]) >= 2, v["cam"]
        m = page_matrix(engine.quad)[0]
        for h, c in zip(v["highlights"], v["cam"]["highlights"]):
            pts = cv2.perspectiveTransform(np.array([[[x * fw, y * fh] for x, y in c["pts"]]], np.float32), m)[0]
            w = pw if turns % 2 == 0 else ph  # width of the page before it was turned
            for _ in range(turns):
                pts = np.array([[y, w - 1 - x] for x, y in pts])
            got = [pts[:, 0].min() / pw, pts[:, 1].min() / ph, pts[:, 0].max() / pw, pts[:, 1].max() / ph]
            assert max(abs(a - b) for a, b in zip(h["box"], got)) < 0.004, (turns, h["box"], got)


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
