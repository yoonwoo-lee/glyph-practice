"""The same end-to-end flow as test_pipeline, on a worse camera.

Each case degrades the simulated frames the way a real desk does (lamp on one
side, glare, soft focus, a dim room, a tilted camera, sensor grain) and checks
that Glyph still gives one hint, one definition and two highlights.

    python -m tests.test_rough
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from glyph import config, demo  # noqa: E402
from glyph.engine import Engine, Settings  # noqa: E402
from glyph.page import find_page_quad  # noqa: E402
from glyph.session import Session  # noqa: E402
from tests.test_pipeline import FAST, ScriptedBrain, kinds  # noqa: E402


class LiveSource:
    """Plays still frames like a camera would: every read gets fresh grain and flicker."""

    label = "rough"
    error = None

    def __init__(self, frames, hold, noise=0.0, flicker=0.0):
        self.frames, self.hold, self.noise, self.flicker = frames, hold, noise, flicker
        self.rng = np.random.RandomState(3)
        self._t0 = time.time()

    def start(self):
        self._t0 = time.time()

    def stop(self):
        pass

    def read(self):
        f = self.frames[min(int((time.time() - self._t0) / self.hold), len(self.frames) - 1)]
        if self.noise or self.flicker:
            return demo.sensor(f, self.rng, self.noise, self.flicker)
        return f


def flow(change=None, corners=None, noise=0.0, flicker=0.0, hold=1.8):
    s = demo.build_steps(corners)
    frames = [s["blank"], s["spark"], s["underline"], s["highlights"]]
    if change:
        frames = [change(f) for f in frames]
    quad, _ = find_page_quad(frames[0])
    assert quad is not None, "sheet not found"
    legend = config.load_legend()
    brain = ScriptedBrain(legend)
    session = Session(Path(tempfile.mkdtemp(prefix="glyph_rough_")))
    source = LiveSource(frames, hold, noise, flicker)
    engine = Engine(source, brain, session, legend, settings=Settings(**FAST))
    source.start()
    engine.start()
    time.sleep(hold * len(frames) + 0.5)
    engine.running = False
    time.sleep(0.2)
    k = kinds(session)
    colors = sorted(e["meta"]["color"] for e in session.events_of("highlight"))
    assert k.count("hint") == 1, "hints: %r" % k
    assert k.count("define") == 1, "definitions: %r" % k
    assert colors == ["green", "yellow"], "highlights: %r" % colors
    assert len(brain.calls) <= 3, "too many looks (%d): noise is being read as ink" % len(brain.calls)
    assert "error" not in k, k


def test_lamp_on_one_side():
    flow(demo.lamp)


def test_lamp_very_uneven():
    flow(lambda f: demo.lamp(f, dark=0.4))


def test_glare_patch():
    flow(demo.glare)


def test_soft_focus():
    flow(demo.soft_focus)


def test_dim_room():
    flow(demo.dim)


def test_tilted_camera():
    flow(corners=demo.TILTED)


def test_sensor_grain_and_flicker():
    flow(noise=4.0, flicker=0.03)


def test_heavy_grain():
    flow(noise=8.0, flicker=0.05)


def test_typical_dorm_desk():
    flow(lambda f: demo.soft_focus(demo.lamp(f, dark=0.6), 5), corners=demo.TILTED, noise=4.0, flicker=0.03)


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    failed = 0
    for t in TESTS:
        t0 = time.time()
        try:
            t()
            print("ok    %-40s %.1fs" % (t.__name__, time.time() - t0))
        except AssertionError as e:
            failed += 1
            print("FAIL  %-40s %s" % (t.__name__, e))
    print("\n%d passed, %d failed" % (len(TESTS) - failed, failed))
    sys.exit(1 if failed else 0)
