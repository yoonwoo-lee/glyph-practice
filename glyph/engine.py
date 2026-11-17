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
    find_page_quad,
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

_K9 = np.ones((9, 9), np.uint8)
_K31 = np.ones((31, 31), np.uint8)

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
        return s

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
        self.store.new_page()

    def _tick(self, frame: np.ndarray, now: float) -> None:
        s = self.settings
        self._apply_results(now)

        stable_for = self._stability.update(frame, now)
        stable = stable_for >= s.settle

        quad, clean = find_page_quad(frame)
        if quad is not None and clean and stable_for >= min(0.25, s.settle):
            tolerance = max(3.0, 0.002 * frame.shape[1])
            if self.quad is None or float(np.abs(quad - self.quad).max()) > tolerance:
                self.quad = quad

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
        ink = ink_mask(page)
        text = "Watching"
        fresh_box = None

        if self.baseline is None:
            text = "Getting a steady view of the page"
            if stable:
                self._accept_page(ink, page, now)
                self._add_highlights(self.store.update(regions, page))
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
                    self._accept_page(ink, page, now)
                    self._want_full = "new page"
            else:
                self._big_since = None
                fresh_box = mask_bbox(fresh) if fresh_px else None
                if covered:
                    text = "Watching (part of the page is covered)"
                    if not stable:
                        self._cover_since = None
                    elif self._cover_since is None:
                        self._cover_since = now
                    elif now - self._cover_since >= s.cover_hold:
                        # It is not going away (a pen left on the sheet): treat it as the page.
                        self._reset_page()
                        self._accept_page(ink, page, now)
                        self._want_full = "page changed"
                        fresh_px = 0
                else:
                    self._cover_since = None
                    if stable and now - self._base_gray_time > 2.0:
                        self.base_gray, self._base_gray_time = page_gray(page), now
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
        }
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
            result = self.brain.analyze(page_jpg, crop_jpg, context=job["context"], shape_hint=job["shape_hint"])
            self._results.put((job, result, None))
        except Exception as e:
            self._results.put((job, None, e))

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
                continue
            self._errors_in_a_row, self._last_error = 0, ""
            same_page = job["epoch"] == self.epoch and self.baseline is not None

            if result.get("occluded"):
                self._wait_for_motion = True
                continue

            shown = 0
            for t in result.get("triggers", []):
                key = (t["action"], _norm(t["target"]))
                if job["full"] and self._already_answered(key):
                    continue
                self._handled.append(key)
                title = TITLES.get(t["action"], t["action"].title())
                if t["action"] == "define" and t["target"]:
                    title = "Definition: " + t["target"][:60]
                self.session.add_event(t["action"], title, t["response"], target=t["target"], symbol=t.get("symbol"))
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
            items = []
            for r in regions:
                try:
                    items.append({"color": r["color"], "label": r["label"], "jpg": r["path"].read_bytes()})
                except OSError:
                    pass
            parts += ["", self.brain.study_guide(items)]
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

    def _publish(self, frame, page, fresh_box, now, text, stable) -> None:
        view = page.copy()
        for r in self.store.on_this_page():
            x, y, w, h = r["bbox"]
            color = DRAW_COLORS.get(r["color"], (120, 120, 120))
            cv2.rectangle(view, (x - 4, y - 4), (x + w + 4, y + h + 4), color, 2)
        if self._cover is not None:
            outlines, _ = cv2.findContours(self._cover, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(view, outlines, -1, (60, 60, 200), 2)
        if self._trigger_box is not None and (self._busy or now - self._trigger_time < 2.5):
            x0, y0, x1, y1 = self._trigger_box
            cv2.rectangle(view, (x0, y0), (x1, y1), (200, 90, 30), 2)
        elif fresh_box is not None:
            x0, y0, x1, y1 = fresh_box
            cv2.rectangle(view, (x0 - 6, y0 - 6), (x1 + 6, y1 + 6), (170, 170, 170), 1)

        h, w = frame.shape[:2]
        scale = 960.0 / w
        raw = cv2.resize(frame, (960, max(1, int(round(h * scale)))), interpolation=cv2.INTER_AREA)
        if self.quad is not None:
            pts = (self.quad * scale).astype(np.int32).reshape(-1, 1, 2)
            cv2.polylines(raw, [pts], True, (60, 200, 90), 2, cv2.LINE_AA)

        page_jpg, raw_jpg = _jpg(view, 75), _jpg(raw, 70)
        with self._lock:
            self._page_jpg, self._raw_jpg = page_jpg, raw_jpg
            self._status = {
                "text": text,
                "page_found": self.quad is not None,
                "stable": bool(stable),
                "busy": self._busy,
            }
