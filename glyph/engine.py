"""The loop that watches the page and decides when to ask the tutor.

Every tick: grab a frame, flatten the page, find highlights and ink, compare
the ink with what was there before, and if something new has appeared and the
picture is holding still, send it to the vision model.

Only this loop's thread changes the page state. Model calls run on a worker
thread and hand their results back through a queue.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import List, Optional, Tuple

import cv2
import numpy as np

from . import config
from .highlights import HighlightStore, detect_highlights
from .page import (
    PAPER_SAT,
    Stability,
    find_sheet,
    ink_groups,
    marks_only,
    move,
    paper_share,
    register,
    page_signature,
    full_frame_page,
    looks_written_on,
    cover_mask,
    ink_strength,
    new_ink,
    steady_strength,
    strength_to_mask,
    make_focus_crop,
    mask_bbox,
    pick_mark,
    page_gray,
    page_saturation,
    see_through,
    remove_small,
    short_underline,
    page_matrix,
    warp_page,
)
from .session import Session

log = logging.getLogger("glyph")

_K3 = np.ones((3, 3), np.uint8)
_K9 = np.ones((9, 9), np.uint8)
_K13 = np.ones((13, 13), np.uint8)
_K15 = np.ones((15, 15), np.uint8)
_K31 = np.ones((31, 31), np.uint8)
_K61 = np.ones((61, 61), np.uint8)
CUT_OFF_TEXT = "Part of the sheet is outside the camera's view. Slide it back, or raise the phone."
NO_SHEET_TEXT = "No sheet in view. Put your page under the camera."

TITLES = {
    "hint": "Hint", "explain": "Explanation", "define": "Definition", "check": "Check", "answer": "Answer",
    "practice": "Try this one", "find": "Find", "synonym": "Synonyms", "summarize": "Summary",
}
VERDICT_TITLES = {"right": "Looks right", "wrong": "Not yet", "unsure": "Could not tell"}
ANSWERS = config.ACTIONS  # the kinds of event that answer a mark
NAMED = {"define": "Definition", "find": "Find", "synonym": "Synonyms"}  # titled with the word they are about
# A second mark by the same problem or passage may be answered again: a stronger hint, another
# try at the answer, one more practice problem. A mark on a word is answered once.
REPEATABLE = ("hint", "explain", "check", "practice")
FIRST_LOOK_CHECKS = 3  # boxed answers, or check marks, already on a sheet when it is first seen: this many are answered
COUNTED = ("check", "answer")  # the actions that rule applies to

# Shown when the student has not written anything for a while. Never an answer, no model call.
NUDGES = [
    "Try writing down what you know so far.",
    "Stuck? Draw a spark next to the problem for a hint.",
    "Read the question once more and underline the word that trips you up.",
    "Start with the smallest step you are sure of.",
    "Sketch it: a quick drawing often shows the next move.",
]


@dataclass
class Settings:
    settle: float = config.SETTLE_SECONDS
    cooldown: float = config.COOLDOWN_SECONDS
    max_calls_per_min: int = config.MAX_CALLS_PER_MIN
    min_new_px: int = config.MIN_NEW_INK_PX
    big_frac: float = config.BIG_CHANGE_FRAC
    missing_frac: float = config.MISSING_FRAC
    big_hold: float = config.BIG_CHANGE_HOLD
    recent: float = config.RECENT_SECONDS
    cover_hold: float = config.COVER_HOLD
    tick: float = 0.125
    # Read a sheet in full as soon as it is first seen. Off since Nov 22 (Yoon Woo): marks already on a
    # sheet are left alone, and a new sheet costs no request. POST /api/look still reads the whole page.
    read_first_page: bool = config.READ_FIRST_PAGE
    # ...but only if at least this share of it is writing or print. A sheet with one line of
    # handwriting has about 0.15% (Nov 19); specks of camera noise are not counted.
    min_page_ink: float = 0.0004
    # Seconds without new writing before one "keep going" card is shown. 0 turns it off.
    stuck_seconds: float = config.STUCK_SECONDS


def _jpg(img: np.ndarray, quality: int = 80) -> bytes:
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    return buf.tobytes() if ok else b""


def _norm(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum() or ch == " ").strip()[:80]


class Engine:
    def __init__(self, source, brain, session: Session, legend: dict, rotate: int = 0, settings: Optional[Settings] = None) -> None:
        self.source = source
        self.brain = brain
        self.session = session
        self.legend = legend
        modes = [m["id"] for m in config.modes_of(legend)]
        self.mode = config.mode_id(legend, config.START_MODE) or (modes[0] if modes else "")
        self._mode_was = self.mode
        self._legends: dict = {}  # mode -> the legend as that mode uses it
        self._found: Optional[dict] = None  # the places a boxed word was found, drawn on the page view
        self.settings = settings or Settings()
        self.store = HighlightStore(session.dir / "highlights", legend.get("highlight_colors", {}))
        self.running = False

        # Shared with the web server (guarded by _lock).
        self._lock = threading.Lock()
        self._raw_jpg = b""
        self._page_jpg = b""
        self._status = {"text": "Starting", "page_found": False, "stable": False, "busy": False}
        self._rotate = rotate % 4
        self._reset_requested = False
        self._look_requested = False

        # Page state (loop thread only).
        self.quad: Optional[np.ndarray] = None
        self.baseline: Optional[np.ndarray] = None
        self.base_strength: Optional[np.ndarray] = None  # how dark the remembered ink was, spot by spot
        self.base_gray: Optional[np.ndarray] = None
        self.base_sat: Optional[np.ndarray] = None
        self._base_gray_time = 0.0
        self._cover_since: Optional[float] = None
        self._cover: Optional[np.ndarray] = None
        self.pending: List[Tuple[np.ndarray, float, np.ndarray]] = []  # (new ink, when, ink strength then)
        self.epoch = 0
        self._shape: Optional[Tuple[int, int]] = None
        self._big_since: Optional[float] = None
        self._wait_for_motion = False
        self._want_full: Optional[str] = None
        self._stability = Stability()
        self._trigger_box: Optional[Tuple[int, int, int, int]] = None
        self._trigger_time = 0.0

        # Model calls.
        self._pool = ThreadPoolExecutor(max_workers=1)
        self._results: "queue.Queue" = queue.Queue()
        self._busy = False
        self._reading: Optional[str] = None  # what a running read is of: "page" (taking a sheet in) or "mark"
        self._last_call = 0.0
        self._call_times: deque = deque()
        self._backoff_until = 0.0
        self._errors_in_a_row = 0
        self._last_error = ""
        self._looks = 0
        self._handled: List[Tuple[str, str, int]] = []  # (action, what it was about, page number)
        self._prev_fresh_px = 0
        self._fresh_since: Optional[float] = None  # when the ink now waiting to be read first showed up
        self._last_page: Optional[np.ndarray] = None  # clean flattened page, for the tuner
        self._answer_times: List[float] = []
        self._ink_hist: deque = deque(maxlen=2)  # the last two ink masks, to ignore ink that flickers
        self._page_unnamed = True  # the page on view has not been matched to an earlier sheet yet
        self._seen_whole = False  # the full sheet has been in view at least once
        self._page_known = False  # the sheet on view was already read earlier this session
        self._debug_last, self._debug_saved = 0.0, 0
        self._cover_shot, self._cover_shots = 0.0, 0
        self._hl_old_until = 0.0
        self._sat0: Optional[np.ndarray] = None  # the page's colorfulness when it was taken in (never refreshed)
        self._quads: deque = deque(maxlen=7)  # recent sightings of the sheet's corners
        self._fills: deque = deque(maxlen=7)  # ...and how much of each outline was visibly paper
        self._quad_fill = 1.0  # the same, for the outline in use
        self._outline_held_since: Optional[float] = None  # since when a moved outline has been held back
        self._check_alignment = False
        self._hl = None  # (highlights found, their mask) from the last time they were looked for
        self._hl_clean = None  # the same, from the last time the sheet was in ordinary light
        self._tinted_until = 0.0  # colored light (a warm shadow) lies on the sheet until then
        self._recent_frames: deque = deque(maxlen=8)  # the last second of camera pictures
        self._bursts_saved = 0
        self._hl_age = 0
        self._show_quad = True
        self._live_raw: Tuple[Optional[int], bytes] = (None, b"")
        self._no_sheet_since: Optional[float] = None  # since when the view has not looked like paper
        self._paper_sat = float(PAPER_SAT)  # how colorful the sheet on view may be and still be paper
        self._aligned_at = 0.0  # when the remembered page was last checked against the page on view
        self._in_place = "same"  # what that check found: "same", "moved" (put right) or "lost"
        self._merge_requested = 0
        self._turned = 0  # quarter turns asked for since the last pass
        self._ticks: deque = deque(maxlen=24)  # times of recent passes, for the rate shown on screen
        self._overlay: dict = {}  # what the web page draws over the pictures
        self._last_ink: Optional[float] = None  # when the student last wrote or highlighted (None: no sheet)
        self._ink_seen = 0  # how much new ink there was on the last pass
        self._nudged = False  # the "keep going" card for this pause has been shown
        self._nudges = 0
        self._publish_turns = self._rotate  # quarter turns of the page picture being published

    # ---- controls used by the web server ----------------------------------

    def start(self) -> None:
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the loop and wait for it, so nothing is mid-frame when Python exits."""
        self.running = False
        thread = getattr(self, "_thread", None)
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=3)
        self._pool.shutdown(wait=False)

    def rotate(self) -> int:
        with self._lock:
            self._rotate = (self._rotate + 1) % 4
            self._reset_requested = True
            self._turned += 1
            return self._rotate * 90

    def set_mode(self, mode: str) -> str:
        """Switch between the modes of the legend (student, editor). Marks already on the page
        stay as they are: nothing is read again, and no request is spent."""
        with self._lock:
            if mode in (self.legend.get("modes") or {}):
                self.mode = mode
            mode = self.mode
        follow = getattr(self.source, "set_mode", None)
        if follow:  # the demo puts the other mode's sheet under the "camera"
            follow(mode)
        return mode

    def legend_now(self, mode: Optional[str] = None) -> dict:
        mode = self.mode if mode is None else mode
        if mode not in self._legends:
            self._legends[mode] = config.legend_for(self.legend, mode)
        return self._legends[mode]

    def same_sheet_as(self, page_no: int) -> None:
        """The user says the sheet on view is page `page_no` (Glyph gave it a new number)."""
        with self._lock:
            self._merge_requested = int(page_no)

    def look_now(self) -> None:
        with self._lock:
            self._look_requested = True

    def jpg(self, which: str) -> bytes:
        with self._lock:
            return self._raw_jpg if which == "raw" else self._page_jpg

    def status(self) -> dict:
        with self._lock:
            s = dict(self._status)
        s["mode"] = getattr(self.brain, "name", "?")  # which brain answers: "gemini" or "mock"
        s["work_mode"] = self.mode  # student or editor
        s["modes"] = config.modes_of(self.legend)
        s["model"] = getattr(self.brain, "last_model", "") or ""
        s["camera"] = getattr(self.source, "label", "")
        s["highlights"] = len(self.store.all())
        s["looks"] = self._looks
        s["page_no"] = self.store.page_no
        s["pages"] = self.store.pages()
        times = list(self._answer_times)
        s["last_seconds"] = round(times[-1], 1) if times else None
        s["avg_seconds"] = round(sum(times) / len(times), 1) if times else None
        s["session_seconds"] = int(time.time() - self.session.started)
        return s

    def _outlined(self, frame: np.ndarray) -> np.ndarray:
        """The camera picture, smaller. (The web page draws the sheet's outline over it.)"""
        h, w = frame.shape[:2]
        scale = 960.0 / w
        return cv2.resize(frame, (960, max(1, int(round(h * scale)))), interpolation=cv2.INTER_AREA)

    def live_raw_jpg(self) -> bytes:
        """The newest camera frame, straight from the camera.

        The main loop does heavy work on every frame, so the picture it publishes updates only a
        few times a second. The camera view on the web page uses this instead, so it stays smooth.
        """
        frame = self.source.read() if self.source is not None else None
        if frame is None:
            return self.jpg("raw")
        key, jpg = self._live_raw
        if key != id(frame):
            jpg = _jpg(self._outlined(frame), 70)
            self._live_raw = (id(frame), jpg)
        return jpg

    def last_page(self) -> Optional[np.ndarray]:
        with self._lock:
            return None if self._last_page is None else self._last_page.copy()

    def request_reset(self) -> None:
        """Forget the remembered page (used after tuning changes how ink is seen)."""
        with self._lock:
            self._reset_requested = True

    # ---- the loop ------------------------------------------------------------

    def _loop(self) -> None:
        while self.running:
            t0 = time.time()
            try:
                frame = self.source.read()
                if frame is not None:
                    self._tick(frame, t0)
            except Exception:
                log.exception("tick failed")
            time.sleep(max(0.01, self.settings.tick - (time.time() - t0)))

    def _calm_highlights(self, page: np.ndarray):
        """The highlights as they were found the last time the sheet was in ordinary light."""
        if self._hl_clean is not None and self._hl_clean[1].shape == page.shape[:2]:
            return self._hl_clean
        return [], np.zeros(page.shape[:2], np.uint8)

    def _reset_page(self) -> None:
        self.baseline = None
        self.base_strength = None
        self.base_gray = None
        self.base_sat = None
        self.pending = []
        self.epoch += 1
        self._big_since = None
        self._cover_since = None
        self._cover = None
        self._wait_for_motion = False
        self._ink_hist.clear()
        self._page_unnamed = True
        self._in_place = "same"
        self._found = None
        self._hl_clean = None
        self.store.new_page()

    def _forget_sheet(self) -> None:
        """Nothing under the camera looks like a sheet of paper any more."""
        if self.quad is None and self.baseline is None:
            return
        self.quad = None
        self._quads.clear()
        self._fills.clear()
        self._outline_held_since = None
        self._shape = None
        self._hl = None
        self._paper_sat = float(PAPER_SAT)
        self._last_ink = None
        self._reset_page()

    def _tick(self, frame: np.ndarray, now: float) -> None:
        s = self.settings
        self._apply_results(now)
        self._ticks.append(now)
        if self.mode != self._mode_was:
            self._mode_was = self.mode
            if self._last_ink is not None:
                self._wrote(now)  # a fresh start: no "keep going" card for time spent in the other mode

        stable_for = self._stability.update(frame, now)
        stable = stable_for >= s.settle
        self._recent_frames.append(frame)

        seen: dict = {}
        quad, clean, touches, fill, cut_off = find_sheet(frame, seen)
        outline_unsure = False
        if stable_for == 0.0:
            self._quads.clear()  # the picture moved: corners seen before no longer apply
            self._fills.clear()
        if quad is not None and clean and stable_for >= min(0.25, s.settle):
            self._seen_whole = True
            # Corners wobble by a few pixels from frame to frame, which would make the flattened
            # page shake and old ink look new. Until a page has been accepted, use the middle of
            # the last few sightings. After that, keep the outline fixed and move it only when
            # four sightings in a row agree that the sheet now lies somewhere else.
            self._quads.append(quad)
            self._fills.append(fill)
            tolerance = max(3.0, 0.002 * frame.shape[1])
            if self.quad is None or self.baseline is None:
                self.quad = np.median(np.array(self._quads), axis=0).astype(np.float32)
                self._quad_fill = float(np.median(self._fills))
            elif float(np.abs(quad - self.quad).max()) > tolerance:
                outline_unsure = True  # maybe the sheet slid, maybe one noisy frame: wait and see
                last = np.array(list(self._quads)[-4:])
                middle = np.median(last, axis=0).astype(np.float32)
                moved = len(last) == 4 and all(float(np.abs(q - self.quad).max()) > tolerance for q in last)
                # A hand reaching onto the sheet bends the outline too, and less of the outline is
                # visibly paper then. Keep the outline Glyph trusts until the sheet is clear again.
                # (Whether something "covers" the page cannot be used here: a sheet that has slid
                # looks covered until the outline has followed it.)
                clear = min(list(self._fills)[-4:]) >= self._quad_fill - 0.015
                # A sheet put down somewhere else (far more than a hand could bend the outline) is
                # followed at once: holding on to the old outline would flatten desk, not paper.
                clear = clear or float(np.abs(middle - self.quad).max()) > 12 * tolerance
                if moved and not clear:
                    # ...but not for ever: something may have been put down on the sheet to stay.
                    if self._outline_held_since is None:
                        self._outline_held_since = now
                    clear = now - self._outline_held_since > 5.0
                if moved and clear and float(np.abs(last - middle).max()) <= 1.5 * tolerance:
                    self.quad = middle
                    self._quad_fill = float(np.median(list(self._fills)[-4:]))
                    self._check_alignment = True
                    self._outline_held_since = None
                    self._ink_hist.clear()
            else:
                self._outline_held_since = None
        # Keep a few camera pictures from moments when no clean sheet outline was found, so the
        # detection can be tuned afterwards against what the camera really saw.
        if not (quad is not None and clean) and stable and now - self._debug_last > 15 and self._debug_saved < 12:
            self._debug_last, self._debug_saved = now, self._debug_saved + 1
            try:
                folder = self.session.dir / "camera"
                folder.mkdir(exist_ok=True)
                cv2.imwrite(str(folder / "no_sheet_{:02d}.jpg".format(self._debug_saved)), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            except OSError:
                pass
        if self._seen_whole and not clean and cut_off:
            # The paper runs off the edge of the picture: the sheet slid partly out of view.
            # Flattening it now would give a skewed, zoomed-in page and junk "new ink", so hold the
            # last good view until it is back. (This is judged on the paper alone. Judged on the
            # rough outline, a hand on a corner next to a gray sleeve looked like this too.)
            with self._lock:
                held = self._last_page
            self._big_since = None
            self._ink_hist.clear()
            if held is not None and self.baseline is not None:
                text = "Thinking" if self._busy else CUT_OFF_TEXT
                self._publish(frame, held, None, now, text, stable, show_quad=False, phase="held")
                return

        with self._lock:
            turns = self._rotate
            reset, self._reset_requested = self._reset_requested, False
            look, self._look_requested = self._look_requested, False
            turned, self._turned = self._turned, 0
            merge, self._merge_requested = self._merge_requested, 0
        if look:
            self._want_full = "you asked"
        for _ in range(turned % 4):
            self.store.turn()  # the sheets seen so far are remembered the way the view is turned
        if merge:
            self._merge_into(merge)

        self._publish_turns = turns
        page = warp_page(frame, self.quad, turns) if self.quad is not None else full_frame_page(frame, turns)

        # Is there a sheet of paper here at all? Without this check the outline of a sheet that
        # has been taken away stays in use, and the bare desk under it is read as a new page
        # (Nov 19: wood grain was sent to the model, and the whole desk saved as a highlight).
        # A flattened sheet is nearly all paper even with a hand on it. The whole camera picture
        # only counts as "the page" when it is nearly all paper: a white desk, or a close-up.
        if quad is not None and clean:
            papery = True
        else:
            # (In a warm shadow the paper is more colorful than usual: go by what the picture as a
            # whole says paper looks like just now. Only for a sheet already being followed.)
            limit = max(self._paper_sat, float(seen.get("sat_limit", PAPER_SAT))) if self.baseline is not None else self._paper_sat
            papery = paper_share(page, limit) >= (0.45 if self.quad is not None else 0.8)
            if papery and self.quad is None and self.baseline is None and not looks_written_on(page):
                papery = False  # all gray or white with nothing on it: a ceiling, a wall, a bare table
            if self.quad is None and seen.get("way") == "edges":
                # A sheet on a light gray desk, its outline not clear yet (a hand on it). The
                # whole picture is gray and white, but it is not a page: wait for the outline.
                # (Nov 21: the desk, the chair and a pair of jeans were read as page 2.)
                papery = False
        if papery:
            self._no_sheet_since = None
        elif self._no_sheet_since is None:
            self._no_sheet_since = now
        if not papery:
            if self.baseline is None or (stable and now - self._no_sheet_since >= 1.5):
                self._forget_sheet()
                if self._want_full != "you asked":
                    self._want_full = None
                self._publish(frame, full_frame_page(frame, turns), None, now, "Thinking" if self._busy else NO_SHEET_TEXT, stable, show_quad=False, phase="none")
                return
            # Most of the sheet is hidden, or it is being lifted away. Nothing seen now is worth
            # judging: no ink, no highlights (wood under a lamp passes for yellow highlighter).
            self._big_since = None
            self._ink_hist.clear()
            self._publish(frame, page, None, now, "Thinking" if self._busy else "Page is covered or being moved", stable, phase="moving")
            return

        if reset:
            # The view was turned: highlights from this page will be captured again the right way up.
            self.store.forget_this_page()
        if reset or self._shape != page.shape[:2]:
            self._reset_page()
            self._shape = page.shape[:2]

        # Finding highlighter is the slowest step and highlights do not change from one frame to
        # the next, so do it on every third pass and reuse the result in between.
        self._hl_age += 1
        if self._hl is None or self._hl_age >= 3 or self._hl[1].shape != page.shape[:2] or not stable:
            self._hl, self._hl_age, hl_new = detect_highlights(page), 0, True
        else:
            hl_new = False
        regions, hl_mask = self._hl
        # Colored light on part of the sheet (a warm shadow) throws the color balance, and print in
        # the part still in white light then passes for pale blue highlighter. While such light is
        # on the sheet, go by the highlights found before it came; new ones wait until it has gone.
        if float(seen.get("sat_limit", PAPER_SAT)) > PAPER_SAT:
            self._tinted_until = max(self._tinted_until, now + 1.0)
        tinted = now < self._tinted_until
        if tinted:
            regions, hl_mask = self._calm_highlights(page)
        strength_now = ink_strength(page)
        if self._check_alignment:
            self._check_alignment = False
            if self.baseline is not None and self.base_strength.shape == strength_now.shape:
                self._in_place, self._aligned_at = self._line_up(strength_now, strength_now), now
        # Faint pencil and camera noise make bits of ink blink on and off. Judge ink by the middle
        # of the last three pictures, and remember the darkest each spot has been as "old".
        strength, strength_any = strength_now, strength_now
        if stable:
            before = list(self._ink_hist)
            strength = steady_strength(strength_now, before)
            for old_strength in before:
                strength_any = cv2.max(strength_any, old_strength)
            steady_ink = len(before) == self._ink_hist.maxlen
            self._ink_hist.append(strength_now)
        else:
            self._ink_hist.clear()
            steady_ink = False
        ink = strength_to_mask(strength)
        text = "Watching"
        phase = "watching"
        fresh_box = None
        fresh_px = 0

        if self.baseline is None:
            text = "Getting a steady view of the page"
            phase = "settling"
            if stable and steady_ink:
                self._accept_page(strength_any, page, now)
                # Highlights already on the sheet were made some other time: not saved (Nov 22).
                # Watched for a few seconds, since one look can miss a highlight in glare.
                self.store.already_there(regions)
                self._hl_old_until = now + 3.0
                self.store.update(regions, page)
                if s.read_first_page and not self._page_known:
                    self._want_full = "new page"  # marks already on the sheet get answered straight away
        else:
            self._age_pending(now)
            # Anything wide lying on the sheet? Ignore the ink around it.
            sat_now = page_saturation(page)
            cover = cover_mask(page_gray(page), self.base_gray, hl_mask, sat_now, self.base_sat)
            # Light of another color (a warm shadow) passes for an object by its color, but the
            # print under it can still be read. An object hides the print.
            solid = cv2.countNonZero(cover)
            cover = see_through(cover, self.baseline, ink)
            if solid - cv2.countNonZero(cover) > 0.04 * cover.size:
                self._tinted_until = now + 1.5
                if not tinted:  # it has just arrived: what was found in this picture cannot be trusted
                    tinted = True
                    regions, hl_mask = self._calm_highlights(page)
            elif not tinted and hl_new:
                self._hl_clean = self._hl
            covered = cv2.countNonZero(cover) > 0
            # Ignore ink for a good finger's width around whatever lies on the sheet: the edge of a
            # hand and the shadow right under it are not writing.
            clear = cv2.bitwise_not(cv2.dilate(cover, _K61)) if covered else None
            self._cover = cover if covered else None

            fresh = new_ink(strength, self.base_strength)
            fresh = cv2.bitwise_and(fresh, cv2.bitwise_not(cv2.dilate(hl_mask, _K9)))
            missing = cv2.bitwise_and(self.baseline, cv2.bitwise_not(cv2.dilate(ink, _K9)))
            old = self.baseline
            if covered:
                fresh = cv2.bitwise_and(fresh, clear)
                missing = cv2.bitwise_and(missing, clear)
                old = cv2.bitwise_and(old, clear)
            fresh = remove_small(fresh, 8)
            fresh_px = cv2.countNonZero(fresh)
            old_px = cv2.countNonZero(old)
            miss_frac = cv2.countNonZero(missing) / float(old_px) if old_px > 800 else 0.0
            big = fresh_px / float(ink.size) > s.big_frac or miss_frac > s.missing_frac
            # Old ink that lands a few pixels off shows up as slivers of "new" ink beside nearly
            # every word on the page. Real writing does not look like that: it sits in a few
            # places, or out in the blank parts of the sheet.
            sprawl = False
            if fresh_px and not big:
                groups = ink_groups(fresh)
                if len(groups) >= 8:
                    beside_old = cv2.countNonZero(cv2.bitwise_and(fresh, cv2.dilate(self.baseline, _K13)))
                    sprawl = beside_old >= 0.8 * fresh_px
            if fresh_px and not big and not sprawl:
                # What is left has to be something drawn on the sheet: not a speck, and not the
                # outline of a fingertip or a pen coming in over the edge of the paper.
                fresh = marks_only(fresh)
                fresh_px = cv2.countNonZero(fresh)
            # A short underline close under a word is far smaller than anything else worth a look.
            small_mark = bool(fresh_px) and fresh_px < s.min_new_px and not big and not sprawl and short_underline(fresh, self.baseline)
            if (big or sprawl or self._in_place != "same" or fresh_px >= s.min_new_px or small_mark) and stable and steady_ink and not outline_unsure:
                # Before believing any of it, check that the remembered page still sits exactly on
                # the page as it is now, and put it right if not. Nothing is sent to the model
                # until a check has found the two in place. If they cannot be matched up at all,
                # this is a page that moved too far or a different page: wait, then start afresh.
                if now - self._aligned_at > 1.0:
                    self._aligned_at = now
                    self._in_place = self._line_up(strength, strength_any, cv2.dilate(cover, _K61) if covered else None)
                    if self._in_place == "moved":
                        big = sprawl = False
                if self._in_place != "same":
                    fresh_px = 0
                    fresh = np.zeros_like(fresh)
                if self._in_place == "lost":
                    big = True

            if big or sprawl:
                # The visible part of the page no longer matches: moved or swapped.
                text = "Page is moving or was changed"
                phase = "moving"
                self._cover_since = None
                fresh_px = 0
                if not stable:
                    self._big_since = None
                elif self._big_since is None:
                    self._big_since = now
                elif now - self._big_since >= s.big_hold and not outline_unsure and ((quad is not None and clean) or self.quad is None or now - self._big_since >= s.cover_hold):
                    # Accept it as the page now: but only once the outline has caught up with the
                    # sheet and nothing is lying across it. Otherwise a sheet with an arm on it, or
                    # one seen through the outline of where it used to lie, becomes a "new page".
                    self._reset_page()
                    self._accept_page(strength_any, page, now)
                    if not self._page_known:  # a sheet that was read before is not read in full again
                        self._want_full = "new page"
            else:
                self._big_since = None
                fresh_box = mask_bbox(fresh) if fresh_px else None
                # For the timing log: note the moment new ink first shows up.
                if fresh_px == 0:
                    self._fresh_since = None
                elif self._fresh_since is None and fresh_px > self._prev_fresh_px + s.min_new_px // 2:
                    self._fresh_since = now
                self._prev_fresh_px = fresh_px
                if covered:
                    text = "Watching (part of the page is covered)"
                    phase = "covered"
                    # A few camera pictures of what counted as covering the page (a shadow should not).
                    if stable and now - self._cover_shot > 4 and self._cover_shots < 10:
                        self._cover_shot, self._cover_shots = now, self._cover_shots + 1
                        try:
                            folder = self.session.dir / "camera"
                            folder.mkdir(exist_ok=True)
                            cv2.imwrite(str(folder / "covered_{:02d}.jpg".format(self._cover_shots)), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                            cv2.imwrite(str(folder / "covered_{:02d}_mask.png".format(self._cover_shots)), cover)
                        except OSError:
                            pass
                    if not stable:
                        self._cover_since = None
                    elif self._cover_since is None:
                        self._cover_since = now
                    elif now - self._cover_since >= s.cover_hold:
                        # It is not going away (a pen left on the sheet): treat it as the page.
                        self._reset_page()
                        self._accept_page(strength_any, page, now)
                        self.store.already_there(regions)  # the same sheet: its highlights are not new
                        self._hl_old_until = now + 3.0
                        self._want_full = "page changed"
                        fresh_px = 0
                else:
                    self._cover_since = None
                    if stable and now - self._base_gray_time > 2.0:
                        self.base_gray, self._base_gray_time = page_gray(page), now
                        self.base_sat = sat_now
                if stable and self.baseline is not None and (not steady_ink or outline_unsure):
                    fresh_px = 0  # not sure yet which ink is really there
                # The student is writing: the "stuck" clock starts again.
                if fresh_px > self._ink_seen + s.min_new_px // 2:
                    self._wrote(now)
                self._ink_seen = fresh_px
                if stable and self.baseline is not None:
                    if hl_new and now < self._hl_old_until:
                        self.store.already_there(regions)
                        self.store.update(regions, page)
                    elif hl_new:
                        self._add_highlights(self.store.update(self._drawn_since(regions, hl_mask, page), page))
                        if len(regions) > len(self.store.on_this_page()):
                            self._hl_age = 3  # a highlight is waiting to be confirmed: look again next pass
                    if self._want_full and self._want_full != "you asked" and cv2.countNonZero(marks_only(ink, edge=-1)) < s.min_page_ink * ink.size:
                        # Nothing here worth a request: a blank sheet, a covered lens, or the phone
                        # off its mount looking at the desk.
                        self._want_full = None
                    if self._want_full:
                        text = self._try_look(now, page, ink, None, full=True, strength=strength_any) or text
                    elif fresh_px:
                        unread = fresh
                        if self.pending:
                            seen = self.pending[0][0].copy()
                            for item in self.pending[1:]:
                                seen = cv2.bitwise_or(seen, item[0])
                            unread = cv2.bitwise_and(fresh, cv2.bitwise_not(cv2.dilate(seen, _K9)))
                            unread = remove_small(unread, 8)
                        enough = cv2.countNonZero(unread) >= s.min_new_px or (small_mark and short_underline(unread, self.baseline))
                        if enough and not self._wait_for_motion:
                            text = self._try_look(now, page, ink, fresh, full=False, strength=strength_any) or text
        if not stable:
            self._wait_for_motion = False
        if self._busy:
            text = "Thinking"
            phase = "reading"
        err = getattr(self.source, "error", None)
        if err:
            text = err
        # Stuck nudge: a sheet in plain view, nothing being read, and no writing for a while.
        # One card per pause; the next one needs new writing first.
        if (
            s.stuck_seconds > 0 and phase == "watching" and not self._want_full and not err
            and "hint" in config.actions_of(self.legend_now())  # a mode for solving problems
            and self._last_ink is not None and not self._nudged and now - self._last_ink >= s.stuck_seconds
        ):
            self._nudged = True
            self.session.add_event("nudge", "Still with it?", NUDGES[self._nudges % len(NUDGES)], page=self.store.page_no)
            self._nudges += 1

        self._publish(
            frame, page, fresh_box, now, text, stable, phase=phase,
            ink_share=cv2.countNonZero(ink) / float(ink.size), fresh_px=fresh_px, regions=self.store.on_this_page(),
        )

    def _line_up(self, strength_now: np.ndarray, darkest: np.ndarray, keep: Optional[np.ndarray] = None) -> str:
        """Check that the remembered page still sits exactly on top of the page as it is flattened
        now, and bring it into line if not. (The paper slides and turns a little whenever someone
        writes on it, and the measured corners shift with it.) Otherwise the old ink lands a few
        pixels off and looks new.

        Returns "same" (already in place), "moved" (put right just now) or "lost" (the two could
        not be matched up, so nothing can be said about new ink).

        The remembered page is not just shifted: once it is known where everything went, it is
        taken afresh from the page as it is now, except where there is new ink (and under `keep`,
        whatever is lying on the sheet). Shifting a picture blurs it a little, and a page shifted
        many times in an hour would fade until all of its ink looked new.
        """
        # Compared with `darkest`, which is how the remembered page itself was taken.
        m, sure = register(self.base_strength, darkest)
        if not sure:
            return "lost"
        if m is None:
            return "same"
        moved = move(self.base_strength, m)
        new = cv2.dilate(remove_small(new_ink(strength_now, moved), 8), _K15)
        if keep is not None:
            new = cv2.bitwise_or(new, keep)
        self.base_strength = np.where(new > 0, moved, darkest)
        self.baseline = strength_to_mask(self.base_strength)
        self.base_gray = move(self.base_gray, m)
        if self.base_sat is not None:
            self.base_sat = move(self.base_sat, m)
        if self._sat0 is not None:
            self._sat0 = move(self._sat0, m)
        self.pending = [(cv2.threshold(move(mask, m), 127, 255, cv2.THRESH_BINARY)[1], t, move(st, m)) for mask, t, st in self.pending]
        return "moved"

    def _drawn_since(self, regions: List[dict], hl_mask: np.ndarray, page: np.ndarray) -> List[dict]:
        """The highlights that were not on the sheet when it was taken in.

        Nov 22: a highlight from an earlier session was saved again although old highlights are
        noted when a sheet is taken in (that look can miss one, in glare or under a hand). So each
        highlight is also checked against the page's colorfulness at that moment: where the paper
        under it was already as colorful as now, the highlight was there before."""
        if self._sat0 is None or self._sat0.shape != hl_mask.shape:
            return regions
        now_sat = page_saturation(page)
        keep, old = [], []
        for r in regions:
            x, y, w, h = r["bbox"]
            inside = hl_mask[y:y + h, x:x + w] > 0
            if not inside.any():
                keep.append(r)
                continue
            gain = now_sat[y:y + h, x:x + w][inside].astype(np.int16) - self._sat0[y:y + h, x:x + w][inside].astype(np.int16)
            (keep if float(np.median(gain)) >= config.HIGHLIGHT_NEW_GAIN else old).append(r)
        if old:
            self.store.already_there(old)
        return keep

    def _accept_page(self, strength: np.ndarray, page: np.ndarray, now: float) -> None:
        """Remember the page as it is now; only later changes count as new."""
        self.base_strength = strength.copy()
        self.baseline = strength_to_mask(strength)
        self.base_gray, self._base_gray_time = page_gray(page), now
        self.base_sat = page_saturation(page)
        self._sat0 = self.base_sat.copy()
        self._wrote(now)  # a page just taken in (new sheet, turned view): the "stuck" clock starts here
        self._ink_seen = 0
        # Colored paper, or a warm lamp: how colorful "paper" is for this sheet.
        self._paper_sat = max(float(PAPER_SAT), float(np.median(self.base_sat[::8, ::8])) + 40.0)
        if self._page_unnamed:
            self._page_unnamed = False
            used = {e["meta"].get("page") for e in self.session.events_of(*ANSWERS)}
            self._page_known = self.store.identify(page_signature(page), used)

    def _merge_into(self, page_no: int) -> None:
        """The user says the sheet on view is an earlier page. File what was saved for it there."""
        was = self.store.merge(page_no)
        if not was:
            return
        self.session.relabel_page(was, page_no)
        self._handled = [(a, t, page_no if n == was else n) for a, t, n in self._handled]
        self._page_known = True
        if self._want_full != "you asked":
            self._want_full = None

    def _age_pending(self, now: float) -> None:
        """Ink that got no response a while ago becomes part of the old page."""
        keep = []
        for mask, t, strength in self.pending:
            if now - t > self.settings.recent:
                self.baseline = cv2.bitwise_or(self.baseline, mask)
                self.base_strength = cv2.max(self.base_strength, strength)
            else:
                keep.append((mask, t, strength))
        self.pending = keep

    # ---- asking the tutor ------------------------------------------------------

    def _try_look(
        self, now: float, page: np.ndarray, ink: np.ndarray, fresh: Optional[np.ndarray], full: bool, strength: Optional[np.ndarray] = None
    ) -> Optional[str]:
        s = self.settings
        if self._busy:
            return "Thinking"
        if now < self._backoff_until:
            return "Waiting to retry the vision model"
        if self._want_full != "you asked" or not full:
            if now - self._last_call < s.cooldown:
                return None
        while self._call_times and now - self._call_times[0] > 60:
            self._call_times.popleft()
        if len(self._call_times) >= s.max_calls_per_min:
            return "Paused: reached the calls-per-minute limit"

        mode = self.mode
        crop, box, shape_hint, symbol_sized = None, None, None, False
        if not full:
            tight = mask_bbox(fresh)
            if tight is None:
                return None
            shape_hint = (tight[2] - tight[0], tight[3] - tight[1])
            # A long upright stroke where margin lines mean something: show the whole width of
            # the page beside it, since the passage it marks runs right across.
            wide = "margin line" in self.legend_now(mode).get("marks", {}) and shape_hint[1] >= 90 and shape_hint[1] >= 3 * shape_hint[0]
            crop, box = make_focus_crop(page, fresh, ink=ink, old=self.baseline, wide=wide)
            if crop is None:
                return None
            # Is any of the new ink the size and shape of a drawn symbol (not a long flat line)?
            symbol_sized = any(14 <= max(w, h) <= 220 and min(w, h) >= 10 and max(w, h) <= 3 * min(w, h) for _, _, w, h in ink_groups(fresh))
        reason = self._want_full if full else "new ink"
        self._want_full = None if full else self._want_full
        self._busy = True
        # A read of the whole sheet is Glyph taking the page in, not a mark being read: the web
        # page says so, and keeps its opening screen (Nov 21: "reading marks when the paper has
        # nothing on it at the very start").
        self._reading = "page" if full else "mark"
        self._last_call = now
        self._call_times.append(now)
        self._looks += 1
        # What the web page marks as "being read": the new ink itself, not the wider close-up.
        self._trigger_box, self._trigger_time = (None if full else mask_bbox(fresh)), now
        job = {
            "n": self._looks,
            "full": full,
            "mode": mode,
            "reason": reason,
            "epoch": self.epoch,
            "page": page.copy(),
            "crop": crop,
            "box": box,
            "shape_hint": shape_hint,
            "symbol_sized": symbol_sized,
            "fresh": None if fresh is None else fresh.copy(),
            "ink": ink.copy(),
            "strength": None if strength is None else strength.copy(),
            # Whatever was lying on the sheet when the picture was taken (with a finger's width around it).
            "cover": None if self._cover is None else cv2.dilate(self._cover, _K61),
            "context": self._context(page, box, asked=reason == "you asked"),
            "t_seen": self._fresh_since if (not full and self._fresh_since) else now,
            "t_sent": now,
            "page_no": self.store.page_no,
        }
        self._fresh_since = None
        self._pool.submit(self._run_job, job)
        self._save_burst("ink" if not full else "page")
        return "Thinking"

    def _save_burst(self, name: str) -> None:
        """Keep the last second of camera pictures from the first two looks of a session.

        Still pictures cannot show how the camera behaves from one frame to the next (noise, the
        sheet shaking, the lens refocusing). These can, and they are what detection gets tuned on.
        """
        if self._bursts_saved >= 2 or getattr(self.source, "label", "").startswith(("demo", "images")):
            return
        self._bursts_saved += 1
        frames, folder, n = list(self._recent_frames), self.session.dir / "camera", self._bursts_saved

        def write() -> None:
            try:
                folder.mkdir(exist_ok=True)
                for i, f in enumerate(frames):
                    cv2.imwrite(str(folder / "burst{}_{}_{:02d}.jpg".format(n, name, i)), f, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            except Exception:  # never let a debugging aid disturb the session
                pass

        threading.Thread(target=write, daemon=True).start()

    def _context(self, page: np.ndarray, box, asked: bool = False) -> str:
        lines = []
        if asked:
            lines.append("The student asked for the whole page to be read: report every mark on it, check marks included.")
        if box is not None:
            h, w = page.shape[:2]
            x0, y0, x1, y1 = box
            lines.append(
                "Image 2 shows the part of image 1 from {:.0f}% to {:.0f}% across and {:.0f}% to {:.0f}% down.".format(
                    100.0 * x0 / w, 100.0 * x1 / w, 100.0 * y0 / h, 100.0 * y1 / h
                )
            )
        earlier = self.session.events_of(*ANSWERS)[-5:]
        if earlier:
            lines.append("Earlier responses this session:")
            for e in earlier:
                kind = e["kind"] + (", verdict " + e["meta"]["verdict"] if e["meta"].get("verdict") else "")
                lines.append('- [{}] about "{}": {}'.format(kind, e["meta"].get("target", ""), e["body"]))
        return "\n".join(lines)

    def _run_job(self, job: dict) -> None:
        try:
            page_jpg = _jpg(job["page"], 85)
            crop_jpg = _jpg(job["crop"], 90) if job["crop"] is not None else None
            self.session.save_look(job["n"], page_jpg, crop_jpg)
            t0 = time.time()
            try:
                result = self.brain.analyze(page_jpg, crop_jpg, context=job["context"], shape_hint=job["shape_hint"], mode=job.get("mode", ""))
            finally:
                job["model_s"] = time.time() - t0
                job["model"] = getattr(self.brain, "last_model", "") or getattr(self.brain, "name", "")
                job["tried"] = list(getattr(self.brain, "last_errors", []))
            self._results.put((job, result, None))
        except Exception as e:
            self._results.put((job, None, e))

    def _log_timing(self, job: dict, now: float, triggers: int, error: str = "") -> dict:
        row = {
            "look": job["n"],
            "reason": job["reason"],
            "full_page": job["full"],
            "wait_s": round(max(0.0, job["t_sent"] - job["t_seen"]), 2),  # ink appeared -> picture sent
            "model_s": round(job.get("model_s", 0.0), 2),  # time inside the vision model call
            "total_s": round(max(0.0, now - job["t_seen"]), 2),  # ink appeared -> answer ready
            "model": job.get("model", ""),
            "triggers": triggers,
            "error": error,
            # Models that failed before the answer came, and why. Each one cost time and a request.
            "tried": ["{}: {}".format(m, k) for m, k, _ in job.get("tried", [])],
        }
        self.session.add_timing(row)
        return row

    def _apply_results(self, now: float) -> None:
        while True:
            try:
                job, result, error = self._results.get_nowait()
            except queue.Empty:
                return
            self._busy = False
            if error is not None:
                self._errors_in_a_row += 1
                wait = getattr(error, "retry_after", None)  # set when the key is over its usage limit
                if wait is None:
                    wait = min(60.0, 8.0 * 2 ** (self._errors_in_a_row - 1))
                self._backoff_until = now + min(300.0, float(wait))
                msg = str(error)[:260]
                if msg != self._last_error:
                    self._last_error = msg
                    self.session.add_event("error", "The vision model had a problem", msg)
                if job["full"]:
                    self._want_full = job["reason"]
                self._log_timing(job, now, 0, msg)
                continue
            self._errors_in_a_row, self._last_error = 0, ""
            same_page = job["epoch"] == self.epoch and self.baseline is not None

            if result.get("occluded"):
                self._wait_for_motion = True
                self._log_timing(job, now, 0, "view blocked")
                continue

            timing = self._log_timing(job, now, len(result.get("triggers", [])))
            if result.get("triggers"):
                self._answer_times.append(timing["total_s"])
            shown = 0
            # More than three check marks on a sheet seen for the first time: it was marked before
            # (by a teacher, or last week). Up to three were drawn just now, perhaps in the seconds
            # before the sheet was taken in, and are answered (Nov 21: the first check of a
            # session got no answer).
            many = {a for a in COUNTED if job["full"] and sum(1 for t in result.get("triggers", []) if t["action"] == a) > FIRST_LOOK_CHECKS}
            for t in result.get("triggers", []):
                key = (t["action"], _norm(t["target"]))
                page_no = job.get("page_no") or 0
                if job["full"]:
                    # A sheet that comes into view with underlines on it was underlined some other
                    # day: those are left alone (Yoon Woo, Nov 20). Symbols on it are answered, and
                    # so is everything when the student asks for the sheet to be read.
                    # The same goes for every mark on words (a box, a circle, a margin line), and
                    # for the check marks of a sheet that is covered in them.
                    # A circled question mark is never taken from a first look: a page of print
                    # holds printed question marks, and one passed for a drawn one (Nov 22).
                    old = t["action"] in many if t["action"] in COUNTED else (t.get("kind", "symbol") != "symbol" or t["action"] == "explain")
                    if old and job["reason"] != "you asked":
                        continue
                    # Reading a whole sheet finds every mark on it, old ones too. One that was
                    # answered before, on any sheet, is the same mark seen again.
                    if self._already_answered(key):
                        continue
                elif self._already_answered(key, page_no):
                    # The same thing about the same words on the same sheet. The only good reason
                    # is a second spark next to the same problem, to ask for a stronger hint, and
                    # then the new ink has the size of a symbol. Anything else is the model
                    # answering an old mark because something else on the page changed.
                    # A second check by the same problem is the student trying again after "not
                    # yet": that one is answered even when the answer is word for word the same.
                    if t["action"] not in REPEATABLE or not job.get("symbol_sized"):
                        continue
                    if t["action"] != "check" and self._said_before(t["response"]):
                        continue
                self._handled.append(key + (page_no,))
                title = TITLES.get(t["action"], t["action"].title())
                if t["action"] in NAMED and t["target"]:
                    title = "{}: {}".format(NAMED[t["action"]], t["target"][:60])
                extra, body = {}, t["response"]
                if job.get("mode"):
                    extra["mode"] = job["mode"]
                if t["action"] == "find":
                    # Said in Glyph's own words, so the count always matches what is outlined.
                    places = t.get("places") or []
                    n = max(int(t.get("count") or 0), len(places))
                    extra["count"] = n
                    if not n:
                        body = "It does not appear anywhere else on this page."
                    else:
                        body = "It appears {} more time{} on this page".format(n, "" if n == 1 else "s")
                        body += ", outlined." if len(places) == n == 1 else ", each one outlined." if len(places) == n else ". {} of them {} outlined.".format(len(places), "is" if len(places) == 1 else "are") if places else "."
                    self._found = {"term": t["target"], "boxes": places, "epoch": job["epoch"]} if same_page else None
                elif same_page and self._found is not None:
                    self._found = None  # the outlines belong to the find card; a newer answer takes its place
                if t["action"] == "check":
                    extra["verdict"] = t.get("verdict") or "unsure"
                    title = VERDICT_TITLES[extra["verdict"]]
                    if t.get("work"):
                        # The model's own solution: kept with the session for looking into a wrong
                        # verdict, never sent to the web page.
                        try:
                            self.session.save_text("looks/{:03d}_check.txt".format(job["n"]), "{}\n\n{}\n".format(extra["verdict"], t["work"]))
                        except OSError:
                            pass
                self.session.add_event(
                    t["action"], title, body, target=t["target"], symbol=t.get("symbol"),
                    seconds=timing["total_s"], model_seconds=timing["model_s"], snip=self._snip(job, t["action"]),
                    page=job.get("page_no"), **extra
                )
                shown += 1

            if not same_page:
                continue
            if job["full"]:
                if shown:
                    # The marks in that picture have been answered, so the picture is the old page
                    # now. The remembered page can be behind it: a spark drawn while the read was
                    # waiting its turn was answered here and then again as "new ink" (Nov 20).
                    # Not under a hand, though: what it hid has not been seen.
                    seen, seen_strength = job["ink"], job.get("strength")
                    if job.get("cover") is not None:
                        clear = cv2.bitwise_not(job["cover"])
                        seen = cv2.bitwise_and(seen, clear)
                        seen_strength = None if seen_strength is None else cv2.bitwise_and(seen_strength, clear)
                    if seen.shape == self.baseline.shape:
                        self.baseline = cv2.bitwise_or(self.baseline, seen)
                        if seen_strength is not None:
                            self.base_strength = cv2.max(self.base_strength, seen_strength)
                        self.pending = []
                continue
            if shown:
                # Answered: everything on the page at that moment is now old.
                self.baseline = cv2.bitwise_or(self.baseline, job["ink"])
                if job.get("strength") is not None:
                    self.base_strength = cv2.max(self.base_strength, job["strength"])
                self.pending = []
            else:
                # Nothing recognised yet: keep this ink marked as new for a while,
                # in case it was a symbol caught half-drawn.
                self.pending.append((job["fresh"], now, job["strength"]))

    def _snip(self, job: dict, action: str = "") -> Optional[int]:
        """A close picture of the one mark that was just answered, for its card.

        A 3:2 window drawn close round that mark (Yoon Woo, Nov 21: the picture took in his
        circled letter, the check after it and two older checks; he asked for it to show just
        the one). An underline is shown with the word above it. A line down the margin is the
        exception: it means the passage beside it, so that picture stays wide.
        """
        box = job.get("box")
        if box is None:
            return None
        page, fresh = job["page"], job.get("fresh")
        ph, pw = page.shape[:2]
        mark = pick_mark(fresh, action) if fresh is not None else None
        if mark is None or action == "summarize":
            x0, y0, x1, y1 = box if mark is None or action != "summarize" else (0, mark[1] - 20, pw, mark[3] + 20)
            w = float(min(max(x1 - x0, 1.5 * (y1 - y0), 0.5 * pw), pw, ph * 1.5))
        else:
            x0, y0, x1, y1 = mark
            if action == "define":
                y0 -= 38  # the underlined word stands above its line
            pad = min(60.0, max(22.0, 0.45 * max(x1 - x0, y1 - y0)))
            w = float(min(max(x1 - x0 + 2 * pad, 1.5 * (y1 - y0 + 2 * pad), 170.0), pw, ph * 1.5))
        h = w / 1.5
        left = int(round(min(max(0.0, 0.5 * (x0 + x1) - 0.5 * w), pw - w)))
        top = int(round(min(max(0.0, 0.5 * (y0 + y1) - 0.5 * h), ph - h)))
        cut = page[top : top + int(h), left : left + int(w)]
        if cut.size == 0:
            return None
        if cut.shape[1] != 540:
            cut = cv2.resize(cut, (540, 360), interpolation=cv2.INTER_AREA if cut.shape[1] > 540 else cv2.INTER_CUBIC)
        return self.session.save_snip(_jpg(cut, 88))

    def _already_answered(self, key: Tuple[str, str], page_no: Optional[int] = None) -> bool:
        """Was this action already taken about these words (on this page, if one is given)?"""
        action, target = key
        for a, t, n in self._handled:
            if page_no is not None and n != page_no:
                continue
            if a == action and (t == target or SequenceMatcher(None, t, target).ratio() >= 0.8):
                return True
        return False

    def _said_before(self, response: str) -> bool:
        said = _norm(response)
        return any(_norm(e["body"]) == said for e in self.session.events_of(*ANSWERS))

    # ---- highlights and study guide --------------------------------------------

    def _wrote(self, now: float) -> None:
        self._last_ink, self._nudged = now, False

    def _add_highlights(self, new_regions: List[dict]) -> None:
        if new_regions:
            self._wrote(self._ticks[-1] if self._ticks else time.time())  # highlighting is working too
        for r in new_regions:
            self.session.add_event(
                "highlight",
                "{} highlight saved".format(r["color"].title()),
                r["label"],
                highlight_id=r["id"],
                color=r["color"],
            )

    def study_guide(self) -> str:
        """Build the end-of-session guide. Called from a web request.

        With one sheet it is a single list. With more than one, each sheet gets its own
        "Page N" section holding its highlights, the words looked up on it, the hints given and the
        answers checked.
        """
        regions = self.store.all()
        order = list(self.legend.get("highlight_colors", {}).keys())
        regions.sort(key=lambda r: (order.index(r["color"]) if r["color"] in order else 99, r["id"]))
        defs = self.session.events_of("define")
        helped = self.session.events_of("hint", "explain")
        checked = self.session.events_of("check")
        more = [  # (heading, events, how one is written)
            ("Synonyms", self.session.events_of("synonym"), lambda e: "**{}**: {}".format(e["meta"].get("target", "?"), e["body"])),
            ("Summaries", self.session.events_of("summarize"), lambda e: e["body"]),
            ("Problems to try", self.session.events_of("practice"), lambda e: e["body"]),
            ("Worked answers", self.session.events_of("answer"), lambda e: "{}: {}".format(e["meta"].get("target", "?"), " ".join(e["body"].split()))),
        ]
        every = defs + helped + checked + [e for _, events, _ in more for e in events]
        pages = sorted({r["page_no"] for r in regions} | {e["meta"].get("page") for e in every if e["meta"].get("page") is not None})
        split = len(pages) > 1
        head = "###" if split else "##"

        def section(page_no) -> List[str]:
            mine = lambda e: not split or e["meta"].get("page") == page_no  # noqa: E731
            out: List[str] = []
            items = []
            for r in regions:
                if split and r["page_no"] != page_no:
                    continue
                try:
                    items.append({"color": r["color"], "label": r["label"], "jpg": r["path"].read_bytes()})
                except OSError:
                    pass
            if items:
                text = self.brain.study_guide(items)
                if split:
                    text = "\n".join("#" + line if line.startswith("## ") else line for line in text.splitlines())
                out += ["", text]
            elif not split:
                out += ["", "No highlights were captured this session."]
            words = [e for e in defs if mine(e)]
            if words:
                out += ["", head + " Words you looked up"]
                out += ["- **{}**: {}".format(e["meta"].get("target", "?"), e["body"]) for e in words]
            hints = [e for e in helped if mine(e)]
            if hints:
                out += ["", head + " Where you asked for help"]
                out += ["- {} ({})".format(e["meta"].get("target", "?"), e["body"]) for e in hints]
            checks = [e for e in checked if mine(e)]
            if checks:
                out += ["", head + " Answers you checked"]
                out += ["- {}: **{}.** {}".format(e["meta"].get("target", "?"), e["title"], e["body"]) for e in checks]
            for name, events, line in more:
                these = [e for e in events if mine(e)]
                if these:
                    out += ["", head + " " + name] + ["- " + line(e) for e in these]
            return out

        parts = ["# Study guide", "", time.strftime("%A, %B %d, %Y")]
        if split:
            for page_no in pages:
                body = section(page_no)
                if body:
                    parts += ["", "## Page {}".format(page_no)] + body
        else:
            parts += section(None)
        text = "\n".join(parts).strip() + "\n"
        self.session.save_text("study_guide.md", text)
        return text

    # ---- pictures for the web page ---------------------------------------------

    def _publish(self, frame, page, fresh_box, now, text, stable, show_quad=True, phase="watching", ink_share=0.0, fresh_px=0, regions=()) -> None:
        """Hand the pictures and the state to the web page.

        The pictures go out clean. Everything drawn over them (the sheet's outline, the box round
        the mark being read, the highlights) is sent as numbers from 0 to 1 and drawn by the web
        page, so it stays sharp at any size.
        """
        ph, pw = page.shape[:2]

        def unit(x0, y0, x1, y1):
            return [round(max(0.0, x0 / pw), 4), round(max(0.0, y0 / ph), 4), round(min(1.0, x1 / pw), 4), round(min(1.0, y1 / ph), 4)]

        reading = self._trigger_box is not None and (self._busy or now - self._trigger_time < 2.5)
        box = None
        if reading:
            box = unit(*self._trigger_box)
        elif fresh_box is not None:
            x0, y0, x1, y1 = fresh_box
            box = unit(x0 - 6, y0 - 6, x1 + 6, y1 + 6)
        covers = []
        if self._cover is not None and phase != "none":
            outlines, _ = cv2.findContours(self._cover, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in outlines[:6]:
                x, y, w, h = cv2.boundingRect(c)
                covers.append(unit(x, y, x + w, y + h))
        # A sheet that cannot be matched to the remembered one is a different sheet waiting to be
        # taken in: what was outlined on the old one does not belong on it.
        other_sheet = phase == "none" or (phase == "moving" and self._in_place == "lost")
        found = []
        if self._found and self._found["epoch"] == self.epoch and not other_sheet:
            found = [list(b) for b in self._found["boxes"]]
        highlights = [] if other_sheet else [{"color": r["color"], "box": unit(r["bbox"][0], r["bbox"][1], r["bbox"][0] + r["bbox"][2], r["bbox"][1] + r["bbox"][3])} for r in regions]
        fh, fw = frame.shape[:2]
        quad = None
        if self.quad is not None and show_quad:
            quad = [[round(float(x) / fw, 4), round(float(y) / fh, 4)] for x, y in self.quad]
        # The same boxes as they lie in the camera picture (four corners each), so the web page
        # can draw them on the camera view too. Only while the outline in use is the one shown.
        cam = None
        if quad is not None and phase not in ("none", "held"):
            try:
                back = np.linalg.inv(page_matrix(self.quad)[0])
            except np.linalg.LinAlgError:
                back = None
            if back is not None:
                def on_camera(b):
                    x0, y0, x1, y1 = b[0] * pw, b[1] * ph, b[2] * pw, b[3] * ph
                    pts, w, h = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], pw, ph
                    for _ in range(self._publish_turns % 4):  # undo each quarter turn of the view
                        pts, w, h = [(h - 1 - y, x) for x, y in pts], h, w
                    out = cv2.perspectiveTransform(np.array([pts], np.float32), back)[0]
                    return [[round(float(x) / fw, 4), round(float(y) / fh, 4)] for x, y in out]

                cam = {
                    "box": on_camera(box) if box else None,
                    "highlights": [{"color": h["color"], "pts": on_camera(h["box"])} for h in highlights],
                    "covers": [on_camera(c) for c in covers],
                    "found": [on_camera(b) for b in found],
                }
        ticks = list(self._ticks)
        rate = (len(ticks) - 1) / (ticks[-1] - ticks[0]) if len(ticks) > 2 and ticks[-1] > ticks[0] else 0.0
        overlay = {
            "phase": phase,
            "box": box,
            "box_state": "reading" if (reading and self._busy) else ("read" if reading else "new"),
            "highlights": highlights,
            "covers": covers,
            "found": found,
            "found_term": self._found["term"] if found else "",
            "quad": quad,
            "cam": cam,
            "page_size": [pw, ph],
            "ink_pct": round(100.0 * ink_share, 1),
            "new_px": int(fresh_px),
            "rate": round(rate, 1),
        }

        self._show_quad = show_quad
        page_jpg, raw_jpg = _jpg(page, 80), _jpg(self._outlined(frame), 70)
        with self._lock:
            self._page_jpg, self._raw_jpg = page_jpg, raw_jpg
            self._last_page = page
            self._status = {
                "text": text,
                "page_found": self.quad is not None,
                "stable": bool(stable),
                "busy": self._busy,
                "reading": self._reading if self._busy else None,
                "view": overlay,
            }
