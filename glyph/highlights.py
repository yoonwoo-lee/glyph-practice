"""Finding highlighter marks by color and keeping a picture of each one."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from . import config
from .page import ink_mask, normalize_light

# Box colors (BGR) for drawing on the page view.
DRAW_COLORS = {
    "yellow": (0, 190, 235),
    "green": (70, 170, 60),
    "blue": (220, 140, 40),
    "pink": (170, 80, 230),
}

_K3 = np.ones((3, 3), np.uint8)
_K7 = np.ones((7, 7), np.uint8)
_KCLOSE = cv2.getStructuringElement(cv2.MORPH_RECT, (31, 9))

Box = Tuple[int, int, int, int]  # x, y, w, h


def detect_highlights(page: np.ndarray):
    """Return ([{color, bbox, area}], mask of all highlighted pixels).

    A highlighter stroke is rarely one even color: it is strong where the pen started and pale
    where it ran dry or was drawn fast (camera run of Nov 20: a green stroke over one line of
    small print, half of it paler than the color range, was not found at all). So each color is
    looked for twice: strictly, in its range from the settings, and loosely, a good deal paler.
    A highlight is a loosely colored patch with enough strictly colored paint in it. Plain paper
    is far below even the loose level once the lighting has been evened out.

    What tells a highlight from colored pen strokes (blue ballpoint, out of focus, is pale blue) is
    that it is a filled band: color and the letters under it together are solid for at least seven
    pixels each way. Pen strokes are not, however many of them sit side by side.
    """
    hsv = cv2.cvtColor(normalize_light(page), cv2.COLOR_BGR2HSV)
    union = np.zeros(page.shape[:2], np.uint8)
    regions: List[dict] = []
    min_area = int(page.shape[0] * page.shape[1] * config.HIGHLIGHT_MIN_FRAC)
    core = max(40, min_area // 4)  # strictly colored pixels a highlight must contain
    letters = ink_mask(page)
    for color, ranges in config.HIGHLIGHT_HSV.items():
        strict = loose = None
        for lo, hi in ranges:
            m = cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8))
            paler = (lo[0], max(25, lo[1] - 30), max(60, lo[2] - 30))
            wide = cv2.inRange(hsv, np.array(paler, np.uint8), np.array(hi, np.uint8))
            strict = m if strict is None else cv2.bitwise_or(strict, m)
            loose = wide if loose is None else cv2.bitwise_or(loose, wide)
        if strict is None or cv2.countNonZero(strict) < core:
            continue
        # A stroke over one line of small print is about a dozen pixels tall and cut up by the
        # letters. Keep the color where it is part of a solid band (see above), clear away
        # specks, then join the pieces back up.
        band = cv2.dilate(cv2.morphologyEx(cv2.bitwise_or(loose, letters), cv2.MORPH_OPEN, _K7), _K3)
        mask = cv2.morphologyEx(cv2.bitwise_and(loose, band), cv2.MORPH_OPEN, _K3)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, _KCLOSE)
        n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        for i in range(1, n):
            x, y, w, h, area = (int(v) for v in stats[i])
            if area < min_area or min(w, h) < 9:
                continue
            if area > 0.3 * page.shape[0] * page.shape[1]:
                continue  # that is not a highlighter stroke: a colored desk, or tinted light
            inside = labels[y : y + h, x : x + w] == i
            if cv2.countNonZero(strict[y : y + h, x : x + w][inside]) < core:
                continue
            regions.append({"color": color, "bbox": (x, y, w, h), "area": area})
            union[y : y + h, x : x + w][inside] = 255
    return regions, union


def _iou(a: Box, b: Box) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    union = aw * ah + bw * bh - inter
    return inter / union if union else 0.0


def _inside(a: Box, b: Box) -> float:
    """Share of the smaller box that lies inside the other one."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    small = min(aw * ah, bw * bh)
    return ix * iy / small if small else 0.0


def _thumb(img: np.ndarray) -> np.ndarray:
    return cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (96, 24), interpolation=cv2.INTER_AREA)


def _similar(a: np.ndarray, b: np.ndarray) -> float:
    return float(cv2.matchTemplate(a, b, cv2.TM_CCOEFF_NORMED)[0, 0])


class HighlightStore:
    """Remembers every highlight seen this session, one cropped photo each."""

    def __init__(self, out_dir: Path, labels: Dict[str, str]) -> None:
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.labels = labels
        self.regions: List[dict] = []
        self.page_no = 0
        self._top_page = 0
        self._signatures: Dict[int, np.ndarray] = {}
        self._next_id = 1
        self._last: List[Tuple[str, Box]] = []
        self._old: List[Tuple[str, Box]] = []  # highlights that were on the sheet when it came into view
        self._lock = threading.Lock()

    def new_page(self) -> None:
        """The sheet on view changed or has to be looked at afresh. It has no number (0) until
        `identify` has compared it with the sheets seen so far."""
        self.page_no = 0
        self._last = []
        self._old = []

    def identify(self, signature, used=()) -> bool:
        """Call once the new page is steady. Gives the sheet on view its page number.

        A sheet seen earlier gets its old number back. A nearly blank sheet cannot be recognised
        when it comes back, so a number that was given to one, and has nothing saved under it
        (`used` lists the numbers that have answers), is handed out again: a blank sheet moved
        about the desk does not use up a new number each time.
        Returns True when this sheet was seen earlier in the session.
        """
        from .page import can_be_told_apart, same_page

        best, best_score = None, 0.6
        for no, sig in self._signatures.items():
            score = same_page(signature, sig)
            if score > best_score:
                best, best_score = no, score
        known = best is not None
        if best is None:
            taken = set(used) | {r["page_no"] for r in self.regions}
            free = sorted(no for no, sig in self._signatures.items() if no not in taken and not can_be_told_apart(sig))
            if free:
                best = free[0]
            else:
                self._top_page += 1
                best = self._top_page
        self.page_no = best
        self._signatures[best] = signature
        return known

    def pages(self) -> List[int]:
        """Every page number given out so far, in order."""
        return sorted(set(self._signatures) | {r["page_no"] for r in self.regions if r["page_no"]})

    def turn(self) -> None:
        """The page view was turned a quarter turn: turn the remembered sheets with it, so a
        sheet is still recognised afterwards."""
        self._signatures = {no: np.ascontiguousarray(np.rot90(sig)) for no, sig in self._signatures.items()}

    def merge(self, into: int) -> int:
        """The sheet on view is really page `into`. Returns the number it had."""
        was = self.page_no
        if not was or was == into or into not in self._signatures:
            return 0
        with self._lock:
            for r in self.regions:
                if r["page_no"] == was:
                    r["page_no"] = into
        self._signatures[into] = self._signatures.pop(was)
        self.page_no = into
        return was

    def forget_this_page(self) -> None:
        """Drop what was captured on the current page (it is about to be re-read)."""
        with self._lock:
            self.regions = [r for r in self.regions if r["page_no"] != self.page_no]
        self._last = []

    def _crop(self, page: np.ndarray, bbox: Box) -> np.ndarray:
        x, y, w, h = bbox
        ph, pw = page.shape[:2]
        return page[max(0, y - 8) : min(ph, y + h + 8), max(0, x - 10) : min(pw, x + w + 10)].copy()

    def already_there(self, detections: List[dict]) -> None:
        """These highlights were on the sheet when it came into view (Nov 22: one from an earlier
        session was saved again). They are not saved unless the student makes them longer."""
        for d in detections:
            if not any(c == d["color"] and _iou(d["bbox"], b) > 0.5 for c, b in self._old):
                self._old.append((d["color"], d["bbox"]))

    def update(self, detections: List[dict], page: np.ndarray) -> List[dict]:
        """Take this frame's highlights; return the ones that are new.

        A highlight is accepted once it shows up in two looks in a row.
        """
        prev = self._last
        self._last = [(d["color"], d["bbox"]) for d in detections]
        fresh: List[dict] = []
        with self._lock:
            for d in detections:
                color, bbox = d["color"], d["bbox"]
                if not any(c == color and _iou(bbox, b) > 0.6 for c, b in prev):
                    continue
                if any(c == color and (_iou(bbox, b) > 0.3 or _inside(bbox, b) > 0.6) and bbox[2] * bbox[3] <= 1.15 * b[2] * b[3] for c, b in self._old):
                    continue  # it was there before the sheet was taken in
                crop = self._crop(page, bbox)
                thumb = _thumb(crop)
                match: Optional[dict] = None
                for r in self.regions:
                    if r["color"] != color:
                        continue
                    # A hand or object over part of a saved highlight leaves a smaller piece (or two)
                    # inside the saved box. Those are the same highlight, not new ones.
                    piece = r["page_no"] == self.page_no and _inside(bbox, r["bbox"]) > 0.6
                    if piece or _iou(bbox, r["bbox"]) > 0.3:
                        match = r
                        break
                if match is not None:
                    grew = bbox[2] * bbox[3] > 1.15 * match["bbox"][2] * match["bbox"][3]
                    if grew and match["page_no"] == self.page_no:
                        # The student kept highlighting: keep the longer version.
                        match["bbox"], match["thumb"] = bbox, thumb
                        cv2.imwrite(str(match["path"]), crop)
                        continue
                    if not grew and match["page_no"] == self.page_no:
                        continue  # same spot, same color, same page: already saved
                    if not grew and _similar(thumb, match["thumb"]) > 0.35:
                        continue
                region = {
                    "id": self._next_id,
                    "color": color,
                    "label": self.labels.get(color, color.title()),
                    "bbox": bbox,
                    "page_no": self.page_no,
                    "thumb": thumb,
                }
                self._next_id += 1
                region["path"] = self.out_dir / f"{region['id']:02d}_{color}.jpg"
                cv2.imwrite(str(region["path"]), crop)
                self.regions.append(region)
                fresh.append(region)
        return fresh

    def on_this_page(self) -> List[dict]:
        with self._lock:
            return [r for r in self.regions if r["page_no"] == self.page_no]

    def all(self) -> List[dict]:
        with self._lock:
            return list(self.regions)
