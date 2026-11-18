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
from .highlights import DRAW_COLORS, HighlightStore, detect_highlights
from .page import (
    Stability,
    find_page,
    page_signature,
    full_frame_page,
    cover_mask,
    ink_mask,
    make_focus_crop,
    mask_bbox,
    page_gray,
    remove_small,
    warp_page,
)
from .session import Session

log = logging.getLogger("glyph")

_K3 = np.ones((3, 3), np.uint8)
_K9 = np.ones((9, 9), np.uint8)
_K31 = np.ones((31, 31), np.uint8)
CUT_OFF_TEXT = "Part of the sheet is outside the camera's view. Slide it back, or raise the phone."

TITLES = {"hint": "Hint", "explain": "Explanation", "define": "Definition"}


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
        self.base_gray: Optional[np.ndarray] = None
        self._base_gray_time = 0.0
        self._cover_since: Optional[float] = None
        self._cover: Optional[np.ndarray] = None
        self.pending: List[Tuple[np.ndarray, float]] = []
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
        self._handled: List[Tuple[str, str]] = []
        self._prev_fresh_px = 0
        self._fresh_since: Optional[float] = None  # when the ink now waiting to be read first showed up
        self._last_page: Optional[np.ndarray] = None  # clean flattened page, for the tuner
        self._answer_times: List[float] = []
        self._ink_hist: deque = deque(maxlen=2)  # the last two ink masks, to ignore ink that flickers
        self._page_unnamed = True  # the page on view has not been matched to an earlier sheet yet
        self._seen_whole = False  # the full sheet has been in view at least once
        self._page_known = False  # the sheet on view was already read earlier this session
        self._debug_last, self._debug_saved = 0.0, 0
        self._show_quad = True
        self._live_raw: Tuple[Optional[int], bytes] = (None, b"")

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
            return self._rotate * 90

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
        s["camera"] = getattr(self.source, "label", "")
        s["highlights"] = len(self.store.all())
        s["looks"] = self._looks
        times = list(self._answer_times)
        s["last_seconds"] = round(times[-1], 1) if times else None
        s["avg_seconds"] = round(sum(times) / len(times), 1) if times else None
        s["session_seconds"] = int(time.time() - self.session.started)
        return s

    def _outlined(self, frame: np.ndarray) -> np.ndarray:
        """The camera picture, smaller, with the sheet outlined."""
        h, w = frame.shape[:2]
        scale = 960.0 / w
        raw = cv2.resize(frame, (960, max(1, int(round(h * scale)))), interpolation=cv2.INTER_AREA)
        quad = self.quad
        if quad is not None and self._show_quad:
            pts = (quad * scale).astype(np.int32).reshape(-1, 1, 2)
            cv2.polylines(raw, [pts], True, (52, 226, 255), 3, cv2.LINE_AA)  # highlighter yellow
        return raw

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
        self.base_gray = None
        self.pending = []
        self.epoch += 1
        self._big_since = None
        self._cover_since = None
        self._cover = None
        self._wait_for_motion = False
        self._ink_hist.clear()
        self._page_unnamed = True
        self.store.new_page()

    def _tick(self, frame: np.ndarray, now: float) -> None:
        s = self.settings
        self._apply_results(now)

        stable_for = self._stability.update(frame, now)
        stable = stable_for >= s.settle

        quad, clean, touches = find_page(frame)
        if quad is not None and clean and stable_for >= min(0.25, s.settle):
            self._seen_whole = True
            tolerance = max(3.0, 0.002 * frame.shape[1])
            if self.quad is None or float(np.abs(quad - self.quad).max()) > tolerance:
                self.quad = quad
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
        if self._seen_whole and touches in (1, 2) and not clean:
            # The sheet slid partly out of the picture. Flattening it now would give a skewed,
            # zoomed-in view and junk "new ink", so hold the last good view until it is back.
            with self._lock:
                held = self._last_page
            self._big_since = None
            self._ink_hist.clear()
            if held is not None:
                text = "Thinking" if self._busy else CUT_OFF_TEXT
                self._publish(frame, held, None, now, text, stable, show_quad=False)
                return

        with self._lock:
            turns = self._rotate
            reset, self._reset_requested = self._reset_requested, False
            look, self._look_requested = self._look_requested, False
        if look:
            self._want_full = "you asked"

        page = warp_page(frame, self.quad, turns) if self.quad is not None else full_frame_page(frame, turns)
        if reset:
            # The view was turned: highlights from this page will be captured again the right way up.
            self.store.forget_this_page()
        if reset or self._shape != page.shape[:2]:
            self._reset_page()
            self._shape = page.shape[:2]

        regions, hl_mask = detect_highlights(page)
        ink_now = ink_mask(page)
        # Faint pencil and camera noise make bits of ink blink on and off. Count ink as there only
        # when it has shown up in the last three looks in a row; remember everything seen as old.
        ink, ink_any = ink_now, ink_now
        if stable:
            for old_ink in self._ink_hist:
                ink = cv2.bitwise_and(ink, cv2.dilate(old_ink, _K3))
                ink_any = cv2.bitwise_or(ink_any, old_ink)
            steady_ink = len(self._ink_hist) == self._ink_hist.maxlen
            self._ink_hist.append(ink_now)
        else:
            self._ink_hist.clear()
            steady_ink = False
        text = "Watching"
        fresh_box = None

        if self.baseline is None:
            text = "Getting a steady view of the page"
            if stable and steady_ink:
                self._accept_page(ink_any, page, now)
                self._add_highlights(self.store.update(regions, page))
                if s.read_first_page and not self._page_known:
                    self._want_full = "new page"  # marks already on the sheet get answered straight away
        else:
            self._age_pending(now)
            # Anything wide lying on the sheet? Ignore the ink around it.
            cover = cover_mask(page_gray(page), self.base_gray, hl_mask)
            covered = cv2.countNonZero(cover) > 0
            clear = cv2.bitwise_not(cv2.dilate(cover, _K31)) if covered else None
            self._cover = cover if covered else None

            fresh = cv2.bitwise_and(ink, cv2.bitwise_not(cv2.dilate(self.baseline, _K9)))
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

            if big:
                # The visible part of the page no longer matches: moved or swapped.
                text = "Page is moving or was changed"
                self._cover_since = None
                if not stable:
                    self._big_since = None
                elif self._big_since is None:
                    self._big_since = now
                elif now - self._big_since >= s.big_hold:
                    self._reset_page()
                    self._accept_page(ink_any, page, now)
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
                    if not stable:
                        self._cover_since = None
                    elif self._cover_since is None:
                        self._cover_since = now
                    elif now - self._cover_since >= s.cover_hold:
                        # It is not going away (a pen left on the sheet): treat it as the page.
                        self._reset_page()
                        self._accept_page(ink_any, page, now)
                        self._want_full = "page changed"
                        fresh_px = 0
                else:
                    self._cover_since = None
                    if stable and now - self._base_gray_time > 2.0:
                        self.base_gray, self._base_gray_time = page_gray(page), now
                if stable and self.baseline is not None and not steady_ink:
                    fresh_px = 0  # not sure yet which ink is really there
                if stable and self.baseline is not None:
                    self._add_highlights(self.store.update(regions, page))
                    if self._want_full:
                        text = self._try_look(now, page, ink, None, full=True) or text
                    elif fresh_px:
                        unread = fresh
                        if self.pending:
                            seen = self.pending[0][0].copy()
                            for m, _ in self.pending[1:]:
                                seen = cv2.bitwise_or(seen, m)
                            unread = cv2.bitwise_and(fresh, cv2.bitwise_not(cv2.dilate(seen, _K9)))
                            unread = remove_small(unread, 8)
                        if cv2.countNonZero(unread) >= s.min_new_px and not self._wait_for_motion:
                            text = self._try_look(now, page, ink, fresh, full=False) or text
        if not stable:
            self._wait_for_motion = False
        if self._busy:
            text = "Thinking"
        err = getattr(self.source, "error", None)
        if err:
            text = err

        self._publish(frame, page, fresh_box, now, text, stable)

    def _accept_page(self, ink: np.ndarray, page: np.ndarray, now: float) -> None:
        """Remember the page as it is now; only later changes count as new."""
        self.baseline = ink.copy()
        self.base_gray, self._base_gray_time = page_gray(page), now
        if self._page_unnamed:
            self._page_unnamed = False
            self._page_known = self.store.identify(page_signature(page))

    def _age_pending(self, now: float) -> None:
        """Ink that got no response a while ago becomes part of the old page."""
        keep = []
        for mask, t in self.pending:
            if now - t > self.settings.recent:
                self.baseline = cv2.bitwise_or(self.baseline, mask)
            else:
                keep.append((mask, t))
        self.pending = keep

    # ---- asking the tutor ------------------------------------------------------

    def _try_look(self, now: float, page: np.ndarray, ink: np.ndarray, fresh: Optional[np.ndarray], full: bool) -> Optional[str]:
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

        crop, box, shape_hint = None, None, None
        if not full:
            crop, box = make_focus_crop(page, fresh)
            if crop is None:
                return None
            tight = mask_bbox(fresh)
            shape_hint = (tight[2] - tight[0], tight[3] - tight[1])
        reason = self._want_full if full else "new ink"
        self._want_full = None if full else self._want_full
        self._busy = True
        self._last_call = now
        self._call_times.append(now)
        self._looks += 1
        self._trigger_box, self._trigger_time = box, now
        job = {
            "n": self._looks,
            "full": full,
            "reason": reason,
            "epoch": self.epoch,
            "page": page.copy(),
            "crop": crop,
            "box": box,
            "shape_hint": shape_hint,
            "fresh": None if fresh is None else fresh.copy(),
            "ink": ink.copy(),
            "context": self._context(page, box),
            "t_seen": self._fresh_since if (not full and self._fresh_since) else now,
            "t_sent": now,
        }
        self._fresh_since = None
        self._pool.submit(self._run_job, job)
        return "Thinking"

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
                self._backoff_until = now + min(60.0, 8.0 * 2 ** (self._errors_in_a_row - 1))
                msg = str(error)[:220]
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
                if job["full"] and self._already_answered(key):
                    continue
                self._handled.append(key)
                title = TITLES.get(t["action"], t["action"].title())
                if t["action"] == "define" and t["target"]:
                    title = "Definition: " + t["target"][:60]
                self.session.add_event(
                    t["action"], title, t["response"], target=t["target"], symbol=t.get("symbol"),
                    seconds=timing["total_s"], model_seconds=timing["model_s"], snip=self._snip(job),
                )
                shown += 1

            if job["full"] or not same_page:
                continue
            if shown:
                # Answered: everything on the page at that moment is now old.
                self.baseline = cv2.bitwise_or(self.baseline, job["ink"])
                self.pending = []
            else:
                # Nothing recognised yet: keep this ink marked as new for a while,
                # in case it was a symbol caught half-drawn.
                self.pending.append((job["fresh"], now))

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

    def _already_answered(self, key: Tuple[str, str]) -> bool:
        action, target = key
        for a, t in self._handled:
            if a == action and (t == target or SequenceMatcher(None, t, target).ratio() >= 0.8):
                return True
        return False

    # ---- highlights and study guide --------------------------------------------

    def _add_highlights(self, new_regions: List[dict]) -> None:
        for r in new_regions:
            self.session.add_event(
                "highlight",
                "{} highlight saved".format(r["color"].title()),
                r["label"],
                highlight_id=r["id"],
                color=r["color"],
            )

    def study_guide(self) -> str:
        """Build the end-of-session guide. Called from a web request."""
        regions = self.store.all()
        parts = ["# Study guide", "", time.strftime("%A, %B %d, %Y")]
        if regions:
            order = list(self.legend.get("highlight_colors", {}).keys())
            regions.sort(key=lambda r: (order.index(r["color"]) if r["color"] in order else 99, r["id"]))
            pages = sorted({r["page_no"] for r in regions})
            for n, page_no in enumerate(pages, 1):
                items = []
                for r in regions:
                    if r["page_no"] != page_no:
                        continue
                    try:
                        items.append({"color": r["color"], "label": r["label"], "jpg": r["path"].read_bytes()})
                    except OSError:
                        pass
                if not items:
                    continue
                section = self.brain.study_guide(items)
                if len(pages) > 1:
                    # One section per sheet, with the colors as sub-headings under it.
                    section = "\n".join("#" + line if line.startswith("## ") else line for line in section.splitlines())
                    parts += ["", "## Page {}".format(n)]
                parts += ["", section]
        else:
            parts += ["", "No highlights were captured this session."]
        defs = self.session.events_of("define")
        if defs:
            parts += ["", "## Words you looked up"]
            parts += ["- **{}**: {}".format(e["meta"].get("target", "?"), e["body"]) for e in defs]
        helped = self.session.events_of("hint", "explain")
        if helped:
            parts += ["", "## Where you asked for help"]
            parts += ["- {} ({})".format(e["meta"].get("target", "?"), e["body"]) for e in helped]
        text = "\n".join(parts).strip() + "\n"
        self.session.save_text("study_guide.md", text)
        return text

    # ---- pictures for the web page ---------------------------------------------

    def _publish(self, frame, page, fresh_box, now, text, stable, show_quad=True) -> None:
        view = page.copy()
        clean_page = page
        for r in self.store.on_this_page():
            x, y, w, h = r["bbox"]
            color = DRAW_COLORS.get(r["color"], (120, 120, 120))
            cv2.rectangle(view, (x - 4, y - 4), (x + w + 4, y + h + 4), color, 2)
        if self._cover is not None:
            outlines, _ = cv2.findContours(self._cover, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(view, outlines, -1, (60, 60, 200), 2)
        if self._trigger_box is not None and (self._busy or now - self._trigger_time < 2.5):
            x0, y0, x1, y1 = self._trigger_box
            cv2.rectangle(view, (x0, y0), (x1, y1), (150, 60, 35), 3)  # ink blue: "reading this"
        elif fresh_box is not None:
            x0, y0, x1, y1 = fresh_box
            cv2.rectangle(view, (x0 - 6, y0 - 6), (x1 + 6, y1 + 6), (170, 170, 170), 1)

        self._show_quad = show_quad
        page_jpg, raw_jpg = _jpg(view, 75), _jpg(self._outlined(frame), 70)
        with self._lock:
            self._page_jpg, self._raw_jpg = page_jpg, raw_jpg
            self._last_page = clean_page
            self._status = {
                "text": text,
                "page_found": self.quad is not None,
                "stable": bool(stable),
                "busy": self._busy,
            }
