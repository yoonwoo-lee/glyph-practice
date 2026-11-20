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
    cover_mask,
    ink_strength,
    new_ink,
    steady_strength,
    strength_to_mask,
    make_focus_crop,
    mask_bbox,
    page_gray,
    page_saturation,
    remove_small,
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

TITLES = {"hint": "Hint", "explain": "Explanation", "define": "Definition"}

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
    read_first_page: bool = True  # read a sheet in full as soon as it is first seen
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
        self._quads: deque = deque(maxlen=7)  # recent sightings of the sheet's corners
        self._fills: deque = deque(maxlen=7)  # ...and how much of each outline was visibly paper
        self._quad_fill = 1.0  # the same, for the outline in use
        self._outline_held_since: Optional[float] = None  # since when a moved outline has been held back
        self._check_alignment = False
        self._hl = None  # (highlights found, their mask) from the last time they were looked for
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
        s["mode"] = getattr(self.brain, "name", "?")
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

        stable_for = self._stability.update(frame, now)
        stable = stable_for >= s.settle
        self._recent_frames.append(frame)

        quad, clean, touches, fill, cut_off = find_sheet(frame)
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

        page = warp_page(frame, self.quad, turns) if self.quad is not None else full_frame_page(frame, turns)

        # Is there a sheet of paper here at all? Without this check the outline of a sheet that
        # has been taken away stays in use, and the bare desk under it is read as a new page
        # (Nov 19: wood grain was sent to the model, and the whole desk saved as a highlight).
        # A flattened sheet is nearly all paper even with a hand on it. The whole camera picture
        # only counts as "the page" when it is nearly all paper: a white desk, or a close-up.
        if quad is not None and clean:
            papery = True
        else:
            papery = paper_share(page, self._paper_sat) >= (0.45 if self.quad is not None else 0.8)
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
                self._add_highlights(self.store.update(regions, page))
                if s.read_first_page and not self._page_known:
                    self._want_full = "new page"  # marks already on the sheet get answered straight away
        else:
            self._age_pending(now)
            # Anything wide lying on the sheet? Ignore the ink around it.
            sat_now = page_saturation(page)
            cover = cover_mask(page_gray(page), self.base_gray, hl_mask, sat_now, self.base_sat)
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
            if (big or sprawl or self._in_place != "same" or fresh_px >= s.min_new_px) and stable and steady_ink and not outline_unsure:
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
                    if not stable:
                        self._cover_since = None
                    elif self._cover_since is None:
                        self._cover_since = now
                    elif now - self._cover_since >= s.cover_hold:
                        # It is not going away (a pen left on the sheet): treat it as the page.
                        self._reset_page()
                        self._accept_page(strength_any, page, now)
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
                    if hl_new:
                        self._add_highlights(self.store.update(regions, page))
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
                        if cv2.countNonZero(unread) >= s.min_new_px and not self._wait_for_motion:
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
        self.pending = [(cv2.threshold(move(mask, m), 127, 255, cv2.THRESH_BINARY)[1], t, move(st, m)) for mask, t, st in self.pending]
        return "moved"

    def _accept_page(self, strength: np.ndarray, page: np.ndarray, now: float) -> None:
        """Remember the page as it is now; only later changes count as new."""
        self.base_strength = strength.copy()
        self.baseline = strength_to_mask(strength)
        self.base_gray, self._base_gray_time = page_gray(page), now
        self.base_sat = page_saturation(page)
        self._wrote(now)  # a page just taken in (new sheet, turned view): the "stuck" clock starts here
        self._ink_seen = 0
        # Colored paper, or a warm lamp: how colorful "paper" is for this sheet.
        self._paper_sat = max(float(PAPER_SAT), float(np.median(self.base_sat[::8, ::8])) + 40.0)
        if self._page_unnamed:
            self._page_unnamed = False
            used = {e["meta"].get("page") for e in self.session.events_of("hint", "explain", "define")}
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

        crop, box, shape_hint, symbol_sized = None, None, None, False
        if not full:
            crop, box = make_focus_crop(page, fresh, ink=ink, old=self.baseline)
            if crop is None:
                return None
            tight = mask_bbox(fresh)
            shape_hint = (tight[2] - tight[0], tight[3] - tight[1])
            # Is any of the new ink the size and shape of a drawn symbol (not a long flat line)?
            symbol_sized = any(14 <= max(w, h) <= 220 and min(w, h) >= 10 and max(w, h) <= 3 * min(w, h) for _, _, w, h in ink_groups(fresh))
        reason = self._want_full if full else "new ink"
        self._want_full = None if full else self._want_full
        self._busy = True
        self._last_call = now
        self._call_times.append(now)
        self._looks += 1
        # What the web page marks as "being read": the new ink itself, not the wider close-up.
        self._trigger_box, self._trigger_time = (None if full else mask_bbox(fresh)), now
        job = {
            "n": self._looks,
            "full": full,
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
            "context": self._context(page, box),
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

    def _context(self, page: np.ndarray, box) -> str:
        lines = []
        if box is not None:
            h, w = page.shape[:2]
            x0, y0, x1, y1 = box
            lines.append(
                "Image 2 shows the part of image 1 from {:.0f}% to {:.0f}% across and {:.0f}% to {:.0f}% down.".format(
                    100.0 * x0 / w, 100.0 * x1 / w, 100.0 * y0 / h, 100.0 * y1 / h
                )
            )
        earlier = self.session.events_of("hint", "explain", "define")[-5:]
        if earlier:
            lines.append("Earlier responses this session:")
            for e in earlier:
                lines.append('- [{}] about "{}": {}'.format(e["kind"], e["meta"].get("target", ""), e["body"]))
        return "\n".join(lines)

    def _run_job(self, job: dict) -> None:
        try:
            page_jpg = _jpg(job["page"], 85)
            crop_jpg = _jpg(job["crop"], 90) if job["crop"] is not None else None
            self.session.save_look(job["n"], page_jpg, crop_jpg)
            t0 = time.time()
            try:
                result = self.brain.analyze(page_jpg, crop_jpg, context=job["context"], shape_hint=job["shape_hint"])
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
            for t in result.get("triggers", []):
                key = (t["action"], _norm(t["target"]))
                page_no = job.get("page_no") or 0
                if job["full"]:
                    # Reading a whole sheet finds every mark on it, old ones too. One that was
                    # answered before, on any sheet, is the same mark seen again.
                    if self._already_answered(key):
                        continue
                elif self._already_answered(key, page_no):
                    # The same thing about the same words on the same sheet. The only good reason
                    # is a second spark next to the same problem, to ask for a stronger hint, and
                    # then the new ink has the size of a symbol. Anything else is the model
                    # answering an old mark because something else on the page changed.
                    if t["action"] == "define" or not job.get("symbol_sized") or self._said_before(t["response"]):
                        continue
                self._handled.append(key + (page_no,))
                title = TITLES.get(t["action"], t["action"].title())
                if t["action"] == "define" and t["target"]:
                    title = "Definition: " + t["target"][:60]
                self.session.add_event(
                    t["action"], title, t["response"], target=t["target"], symbol=t.get("symbol"),
                    seconds=timing["total_s"], model_seconds=timing["model_s"], snip=self._snip(job),
                    page=job.get("page_no"),
                )
                shown += 1

            if job["full"] or not same_page:
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

    def _snip(self, job: dict) -> Optional[int]:
        """The piece of paper around the mark that was just answered.

        A 3:2 window that always contains the mark and is slid, within that
        limit, to take in as much nearby writing as possible, so a spark drawn
        in the margin is shown next to the problem it belongs to.
        """
        box = job.get("box")
        if box is None:
            return None
        page, ink = job["page"], job["ink"]
        ph, pw = page.shape[:2]
        x0, y0, x1, y1 = box
        w = int(min(max(x1 - x0, 1.5 * (y1 - y0), 0.5 * pw), pw, ph * 1.5))
        h = int(w / 1.5)

        def best(lo: int, hi: int, weight: np.ndarray, size: int) -> int:
            lo, hi = max(0, lo), min(hi, len(weight) - size)
            if hi <= lo:
                return max(0, min(lo, len(weight) - size))
            run = np.concatenate([[0.0], np.cumsum(weight)])
            starts = np.arange(lo, hi + 1)
            return int(starts[np.argmax(run[starts + size] - run[starts])])

        top = best(y1 - h, y0, ink.sum(axis=1, dtype=np.float64), h)
        left = best(x1 - w, x0, ink[top : top + h].sum(axis=0, dtype=np.float64), w)
        cut = page[top : top + h, left : left + w]
        if cut.size == 0:
            return None
        if cut.shape[1] > 540:
            cut = cv2.resize(cut, (540, 360), interpolation=cv2.INTER_AREA)
        return self.session.save_snip(_jpg(cut, 86))

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
        return any(_norm(e["body"]) == said for e in self.session.events_of("hint", "explain", "define"))

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
        "Page N" section holding its highlights, the words looked up on it and the hints given.
        """
        regions = self.store.all()
        order = list(self.legend.get("highlight_colors", {}).keys())
        regions.sort(key=lambda r: (order.index(r["color"]) if r["color"] in order else 99, r["id"]))
        defs = self.session.events_of("define")
        helped = self.session.events_of("hint", "explain")
        pages = sorted(
            {r["page_no"] for r in regions} | {e["meta"].get("page") for e in defs + helped if e["meta"].get("page") is not None}
        )
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
        fh, fw = frame.shape[:2]
        quad = None
        if self.quad is not None and show_quad:
            quad = [[round(float(x) / fw, 4), round(float(y) / fh, 4)] for x, y in self.quad]
        ticks = list(self._ticks)
        rate = (len(ticks) - 1) / (ticks[-1] - ticks[0]) if len(ticks) > 2 and ticks[-1] > ticks[0] else 0.0
        overlay = {
            "phase": phase,
            "box": box,
            "box_state": "reading" if (reading and self._busy) else ("read" if reading else "new"),
            "highlights": [] if phase == "none" else [{"color": r["color"], "box": unit(r["bbox"][0], r["bbox"][1], r["bbox"][0] + r["bbox"][2], r["bbox"][1] + r["bbox"][3])} for r in regions],
            "covers": covers,
            "quad": quad,
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
                "view": overlay,
            }
