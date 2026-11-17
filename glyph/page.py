"""Finding the sheet of paper, flattening it, and spotting new ink."""

from __future__ import annotations

from typing import Optional, Tuple

import cv2
import numpy as np

from . import config


def order_quad(pts: np.ndarray) -> np.ndarray:
    """Return 4 corners as top-left, top-right, bottom-right, bottom-left."""
    pts = np.asarray(pts, dtype=np.float32).reshape(4, 2)
    s = pts.sum(axis=1)
    d = pts[:, 0] - pts[:, 1]
    return np.array(
        [pts[np.argmin(s)], pts[np.argmax(d)], pts[np.argmax(s)], pts[np.argmin(d)]],
        dtype=np.float32,
    )


def find_page_quad(frame: np.ndarray) -> Tuple[Optional[np.ndarray], bool]:
    """Find the paper: the largest bright four-sided shape in the frame.

    Returns (corners, clean). `clean` is False when something (a hand, a pen)
    breaks the outline, so the caller can keep using the last good corners.
    Returns (None, False) when no sheet stands out, for example when the paper
    fills the whole frame or sits on a white desk.
    """
    h, w = frame.shape[:2]
    scale = 640.0 / w
    small = cv2.resize(frame, (640, max(1, int(round(h * scale)))), interpolation=cv2.INTER_AREA)
    gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, False
    c = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(c)
    sh, sw = small.shape[:2]
    if area < 0.12 * sh * sw:
        return None, False
    x, y, bw, bh = cv2.boundingRect(c)
    touches = int(x <= 2) + int(y <= 2) + int(x + bw >= sw - 2) + int(y + bh >= sh - 2)
    if touches >= 3:
        return None, False

    peri = cv2.arcLength(c, True)
    quad = None
    direct = False
    for eps in (0.02, 0.03, 0.05):
        approx = cv2.approxPolyDP(c, eps * peri, True)
        if len(approx) == 4 and cv2.isContourConvex(approx):
            quad = approx.reshape(4, 2).astype(np.float32)
            direct = True
            break
    if quad is None:
        hull = cv2.convexHull(c)
        hperi = cv2.arcLength(hull, True)
        for eps in (0.02, 0.03, 0.05):
            approx = cv2.approxPolyDP(hull, eps * hperi, True)
            if len(approx) == 4:
                quad = approx.reshape(4, 2).astype(np.float32)
                break
    if quad is None:
        return None, False
    quad_area = cv2.contourArea(quad)
    fill = area / quad_area if quad_area > 0 else 0.0
    clean = direct and 0.93 <= fill <= 1.05
    return order_quad(quad / scale), clean


def _rotate(img: np.ndarray, quarter_turns: int) -> np.ndarray:
    k = quarter_turns % 4
    return np.ascontiguousarray(np.rot90(img, k)) if k else img


def warp_page(frame: np.ndarray, quad: np.ndarray, quarter_turns: int = 0) -> np.ndarray:
    """Flatten the paper to a top-down image of a fixed size."""
    tl, tr, br, bl = quad
    width = (np.linalg.norm(tr - tl) + np.linalg.norm(br - bl)) / 2.0
    height = (np.linalg.norm(bl - tl) + np.linalg.norm(br - tr)) / 2.0
    if width >= height:
        out_w, out_h = config.PAGE_LONG, config.PAGE_SHORT
    else:
        out_w, out_h = config.PAGE_SHORT, config.PAGE_LONG
    dst = np.array([[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]], dtype=np.float32)
    m = cv2.getPerspectiveTransform(quad.astype(np.float32), dst)
    page = cv2.warpPerspective(frame, m, (out_w, out_h), flags=cv2.INTER_LINEAR, borderValue=(255, 255, 255))
    return _rotate(page, quarter_turns)


def full_frame_page(frame: np.ndarray, quarter_turns: int = 0) -> np.ndarray:
    """No sheet found: treat the whole camera frame as the page."""
    h, w = frame.shape[:2]
    scale = config.PAGE_LONG / float(max(h, w))
    page = cv2.resize(frame, (max(1, int(round(w * scale))), max(1, int(round(h * scale)))), interpolation=cv2.INTER_AREA)
    return _rotate(page, quarter_turns)


def ink_mask(page: np.ndarray) -> np.ndarray:
    """White where there is dark ink (pen, pencil, print).

    Works on the brightest color channel, so highlighter (which stays bright
    in at least one channel) does not count as ink.
    """
    v = cv2.GaussianBlur(page.max(axis=2), (3, 3), 0)
    mask = cv2.adaptiveThreshold(
        v, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, config.INK_BLOCK, config.INK_C
    )
    b = 10  # ignore the very edge of the sheet
    mask[:b, :] = 0
    mask[-b:, :] = 0
    mask[:, :b] = 0
    mask[:, -b:] = 0
    return mask


_K15 = np.ones((15, 15), np.uint8)


def normalize_light(page: np.ndarray) -> np.ndarray:
    """Even out the lighting so blank paper comes out neutral white everywhere.

    Two corrections, both measured from the page itself:
    1. white balance: the typical paper color is scaled to gray, so a warm lamp
       does not make the whole sheet look like yellow highlighter;
    2. brightness: a smooth map of how bright the paper is in each area (from
       the brightest color channel, which highlighter barely changes) is
       divided out, so a dim room or a lamp on one side does not hide colors.
    Used for finding highlighter colors only; ink detection has its own
    local threshold and the saved pictures keep the real colors.
    """
    small = cv2.resize(page, None, fx=0.125, fy=0.125, interpolation=cv2.INTER_AREA)
    top = small.max(axis=2)
    bright = small[top >= np.percentile(top, 50)]
    paper = np.median(bright.reshape(-1, 3), axis=0).astype(np.float32) if len(bright) else np.array([240, 240, 240], np.float32)
    wb = np.clip(float(paper.max()) / np.maximum(paper, 1.0), 1.0, 1.8)

    light = cv2.dilate(top, np.ones((5, 5), np.uint8))  # paint over ink
    light = cv2.GaussianBlur(light, (0, 0), 6).astype(np.float32)
    gain = np.clip(238.0 / np.maximum(light, 1.0), 0.8, 3.0)
    gain = cv2.resize(gain, (page.shape[1], page.shape[0]), interpolation=cv2.INTER_LINEAR)
    out = page.astype(np.float32) * (gain[..., None] * wb[None, None, :])
    return np.clip(out, 0, 255).astype(np.uint8)


def page_gray(page: np.ndarray) -> np.ndarray:
    """Smoothed grayscale page, used to notice things lying on the sheet."""
    return cv2.GaussianBlur(cv2.cvtColor(page, cv2.COLOR_BGR2GRAY), (9, 9), 0)


def cover_mask(gray: np.ndarray, base_gray: np.ndarray, highlight_mask: np.ndarray) -> np.ndarray:
    """White where something wide (a hand, an arm, a pen, a shadow) hides the page.

    Compares the page with how it looked when it was clear. Pen strokes are
    too thin to survive the clean-up, drawn symbols are too small, and
    highlighter is excluded by color, so only real objects remain.
    """
    mb = float(np.median(base_gray[::8, ::8]))
    mc = float(np.median(gray[::8, ::8]))
    gain = min(1.4, max(0.7, mb / max(mc, 1.0)))  # even out exposure changes
    cur = cv2.convertScaleAbs(gray, alpha=gain) if abs(gain - 1.0) > 0.02 else gray
    _, m = cv2.threshold(cv2.absdiff(cur, base_gray), config.COVER_DIFF, 255, cv2.THRESH_BINARY)
    m = cv2.bitwise_and(m, cv2.bitwise_not(cv2.dilate(highlight_mask, _K15)))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, _K15)
    if cv2.countNonZero(m) == 0:
        return m
    return remove_small(m, int(config.COVER_MIN_FRAC * m.size))


def remove_small(mask: np.ndarray, min_area: int) -> np.ndarray:
    """Drop specks smaller than min_area pixels without thinning real strokes."""
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if n <= 1:
        return mask
    keep = stats[:, cv2.CC_STAT_AREA] >= min_area
    keep[0] = False
    return (keep[labels].astype(np.uint8)) * 255


def mask_bbox(mask: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
    """Bounding box (x0, y0, x1, y1) of the white pixels, or None."""
    pts = cv2.findNonZero(mask)
    if pts is None:
        return None
    x, y, w, h = cv2.boundingRect(pts)
    return int(x), int(y), int(x + w), int(y + h)


def make_focus_crop(page: np.ndarray, fresh: np.ndarray, pad: int = 70):
    """Close-up of the new ink, with everything older faded out.

    The vision model is told that only the full-contrast marks in this image
    are new, which keeps it from answering an old symbol a second time.
    Returns (image, (x0, y0, x1, y1)) or (None, None) if there is no new ink.
    """
    box = mask_bbox(fresh)
    if box is None:
        return None, None
    h, w = fresh.shape[:2]
    x0, y0, x1, y1 = box
    x0, y0 = max(0, x0 - pad), max(0, y0 - pad)
    x1, y1 = min(w, x1 + pad), min(h, y1 + pad)
    crop = page[y0:y1, x0:x1]
    near = cv2.dilate(fresh[y0:y1, x0:x1], np.ones((13, 13), np.uint8))
    faded = cv2.addWeighted(crop, 0.3, np.full_like(crop, 255), 0.7, 0)
    out = np.where(near[..., None] > 0, crop, faded)
    longest = max(out.shape[:2])
    if longest < 500:
        f = 500.0 / longest
        out = cv2.resize(out, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
    return np.ascontiguousarray(out), (x0, y0, x1, y1)


class Stability:
    """Tracks how long the camera picture has been holding still."""

    def __init__(self) -> None:
        self._prev = None
        self._since = None

    def update(self, frame: np.ndarray, now: float) -> float:
        small = cv2.resize(frame, (160, 90), interpolation=cv2.INTER_AREA)
        g = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (5, 5), 0)
        if self._prev is None or self._since is None:
            self._prev, self._since = g, now
            return 0.0
        moving = float((cv2.absdiff(g, self._prev) > 14).mean()) > 0.004
        self._prev = g
        if moving:
            self._since = now
            return 0.0
        return now - self._since
