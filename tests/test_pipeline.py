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

    def analyze(self, page_jpg, crop_jpg=None, context="", shape_hint=None):
        self.calls.append({"full": crop_jpg is None, "shape": shape_hint, "context": context})
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


def test_old_writing_fades_out_of_the_close_up():
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
