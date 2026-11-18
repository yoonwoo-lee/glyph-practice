"""Finding the sheet of paper, flattening it, and spotting new ink."""

from __future__ import annotations

from typing import List, Optional, Tuple

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
    quad, clean, _ = find_page(frame)
    return quad, clean


def page_signature(page: np.ndarray) -> np.ndarray:
    """A small picture of the ink on a page, to tell one sheet from another.

    Two pages of the same reading have their lines in the same places and differ only in the
    words, so what a whole line has in common is taken out and the shapes of the words are kept.
    """
    small = cv2.resize(ink_strength(page), None, fx=1 / 3.0, fy=1 / 3.0, interpolation=cv2.INTER_AREA).astype(np.float32)
    small = cv2.GaussianBlur(small, (3, 3), 0)
    return small - cv2.blur(small, (31, 1))


def same_page(a: np.ndarray, b: np.ndarray) -> float:
    """How alike two page signatures are: high for the same sheet, near 0 for different ones.

    The page is compared piece by piece, and each piece may sit a few pixels off. A sheet that
    was put back slightly turned or shifted therefore still counts as the same sheet.
    """
    if a.shape != b.shape:
        return 0.0
    h, w = a.shape[:2]
    m = 6
    scores = []
    for row in range(5):
        for col in range(4):
            y0, y1 = row * h // 5, (row + 1) * h // 5
            x0, x1 = col * w // 4, (col + 1) * w // 4
            piece = np.ascontiguousarray(b[y0 + m : y1 - m, x0 + m : x1 - m])
            area = np.ascontiguousarray(a[y0:y1, x0:x1])
            if float(piece.std()) < 0.6 or float(area.std()) < 0.6:
                continue  # nothing written in this part of the page
            scores.append(float(cv2.matchTemplate(area, piece, cv2.TM_CCOEFF_NORMED).max()))
    if len(scores) < 3:
        return 0.0
    return float(np.median(scores))


def find_page(frame: np.ndarray) -> Tuple[Optional[np.ndarray], bool, int]:
    """Find the paper in the camera picture: (corners, clean, touches). See find_page_fill."""
    return find_page_fill(frame)[:3]


def find_page_fill(frame: np.ndarray) -> Tuple[Optional[np.ndarray], bool, int, float]:
    """Find the paper in the camera picture.

    Returns (corners, clean, touches, fill). `clean` is False when something (a hand, a pen)
    breaks the outline, so the caller can keep using the last good corners. `touches` is how
    many edges of the camera picture the sheet reaches: 1 or 2 means part of it may be out of
    view. `fill` is how much of the four-cornered outline is visibly paper: it drops when a hand
    or an object reaches onto the sheet. Corners are None when no sheet stands out, for example
    when the paper fills the whole frame or sits on a white desk.

    Two ways of looking are tried. By color: paper is the big area that is neither colorful nor
    dark, which holds up on a wooden desk with glare and with shadows lying across the sheet.
    By brightness: the largest bright shape, which works on a dark desk in any light.
    """
    h, w = frame.shape[:2]
    scale = 640.0 / w
    small = cv2.resize(frame, (640, max(1, int(round(h * scale)))), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (5, 5), 0)
    by_color = _outline(_paper_by_color(small), strict=False)
    if by_color[0] is not None and by_color[1]:
        return order_quad(by_color[0] / scale), True, by_color[2], by_color[3]
    by_light = _outline(_paper_by_brightness(small), strict=True)
    if by_light[0] is not None and by_light[1]:
        return order_quad(by_light[0] / scale), True, by_light[2], by_light[3]
    quad, _, touches, fill = by_light if by_light[0] is not None else by_color
    return (None if quad is None else order_quad(quad / scale)), False, touches, fill


def _paper_by_color(small: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    sat, val = hsv[..., 1], hsv[..., 2]
    bright = float(np.percentile(val, 95))
    mask = ((sat < 75) & (val > 0.38 * bright)).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))


def _paper_by_brightness(small: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return cv2.morphologyEx(th, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))


def _outline(mask: np.ndarray, strict: bool) -> Tuple[Optional[np.ndarray], bool, int, float]:
    """The four corners of the largest shape in a mask, and whether it really is a clean sheet."""
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return None, False, 0, 0.0
    c = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(c)
    sh, sw = mask.shape[:2]
    if area < 0.12 * sh * sw:
        return None, False, 0, 0.0
    x, y, bw, bh = cv2.boundingRect(c)
    touches = int(x <= 2) + int(y <= 2) + int(x + bw >= sw - 2) + int(y + bh >= sh - 2)
    if touches >= 3:
        return None, False, touches, 0.0

    quad = None
    direct = False
    peri = cv2.arcLength(c, True)
    for eps in (0.02, 0.03, 0.05):
        approx = cv2.approxPolyDP(c, eps * peri, True)
        if len(approx) == 4 and cv2.isContourConvex(approx):
            quad = approx.reshape(4, 2).astype(np.float32)
            direct = True
            break
    if quad is None:
        hull = cv2.convexHull(c)
        hperi = cv2.arcLength(hull, True)
        for eps in (0.02, 0.03, 0.05, 0.08):
            approx = cv2.approxPolyDP(hull, eps * hperi, True)
            if len(approx) == 4:
                quad = approx.reshape(4, 2).astype(np.float32)
                break
    if quad is None:
        return None, False, touches, 0.0
    quad_area = cv2.contourArea(quad)
    fill = area / quad_area if quad_area > 0 else 0.0
    if strict:
        clean = direct and 0.93 <= fill <= 1.05 and touches == 0
    else:
        # A real sheet has slightly bowed edges and may reach the edge of the picture.
        clean = 0.93 <= fill <= 1.08 and touches <= 2
        if clean and touches:
            # At the edge of the picture: fine if it still has the proportions of a sheet of paper,
            # not if a chunk of it is out of view.
            o = order_quad(quad)
            a = float(np.linalg.norm(o[1] - o[0]) + np.linalg.norm(o[2] - o[3]))
            b = float(np.linalg.norm(o[3] - o[0]) + np.linalg.norm(o[2] - o[1]))
            clean = 1.15 <= max(a, b) / max(min(a, b), 1.0) <= 1.5
    if clean:
        quad = _sharpen_corners(c, quad)
    return quad, clean, touches, fill


def _sharpen_corners(contour: np.ndarray, quad: np.ndarray) -> np.ndarray:
    """Fit a straight line to each side of the outline and take the corners where they cross.

    The corner points of the rough outline wobble by a few pixels from frame to frame, which
    makes the flattened page shake. A line through the hundreds of points along a side is much
    steadier, and it is not thrown off by a rounded or dog-eared corner.
    """
    pts = contour.reshape(-1, 2).astype(np.float32)
    q = order_quad(quad)
    lines = []
    for i in range(4):
        a, b = q[i], q[(i + 1) % 4]
        d = b - a
        length = float(np.linalg.norm(d))
        if length < 20:
            return quad
        d = d / length
        rel = pts - a
        along = rel @ d
        off = np.abs(rel @ np.array([-d[1], d[0]], np.float32))
        side = pts[(along > 0.12 * length) & (along < 0.88 * length) & (off < max(5.0, 0.03 * length))]
        if len(side) < 12:
            return quad
        vx, vy, x0, y0 = cv2.fitLine(side, cv2.DIST_HUBER, 0, 0.01, 0.01).ravel()
        lines.append((float(vx), float(vy), float(x0), float(y0)))
    corners = []
    for i in range(4):
        vx1, vy1, x1, y1 = lines[(i - 1) % 4]
        vx2, vy2, x2, y2 = lines[i]
        det = vx1 * vy2 - vy1 * vx2
        if abs(det) < 1e-6:
            return quad
        t = ((x2 - x1) * vy2 - (y2 - y1) * vx2) / det
        corner = np.array([x1 + t * vx1, y1 + t * vy1], np.float32)
        if float(np.linalg.norm(corner - q[i])) > 0.08 * float(np.linalg.norm(q[2] - q[0])):
            return quad  # the fit ran off somewhere: keep the rough corners
        corners.append(corner)
    return np.array(corners, np.float32)


def _rotate(img: np.ndarray, quarter_turns: int) -> np.ndarray:
    k = quarter_turns % 4
    return np.ascontiguousarray(np.rot90(img, k)) if k else img


def page_matrix(quad: np.ndarray) -> Tuple[np.ndarray, Tuple[int, int]]:
    """The mapping from the camera picture to the flattened page, and the page's (width, height)."""
    tl, tr, br, bl = quad
    width = (np.linalg.norm(tr - tl) + np.linalg.norm(br - bl)) / 2.0
    height = (np.linalg.norm(bl - tl) + np.linalg.norm(br - tr)) / 2.0
    if width >= height:
        out_w, out_h = config.PAGE_LONG, config.PAGE_SHORT
    else:
        out_w, out_h = config.PAGE_SHORT, config.PAGE_LONG
    dst = np.array([[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]], dtype=np.float32)
    return cv2.getPerspectiveTransform(quad.astype(np.float32), dst), (out_w, out_h)


def warp_page(frame: np.ndarray, quad: np.ndarray, quarter_turns: int = 0) -> np.ndarray:
    """Flatten the paper to a top-down image of a fixed size."""
    m, size = page_matrix(quad)
    page = cv2.warpPerspective(frame, m, size, flags=cv2.INTER_LINEAR, borderValue=(255, 255, 255))
    return _rotate(page, quarter_turns)


def slip_between(old_strength: np.ndarray, new_strength: np.ndarray) -> Optional[Tuple[float, float]]:
    """How far (dx, dy, in pixels) the page content has slipped between two ink pictures.

    Used after the sheet's outline has been re-measured: the remembered page and the page as it
    is flattened now can then sit a few pixels apart. Returns None when the pictures have too
    little in common to tell (a blank sheet, or a different page).
    """
    if old_strength.shape != new_strength.shape:
        return None
    a = cv2.resize(old_strength, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA).astype(np.float32)
    b = cv2.resize(new_strength, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA).astype(np.float32)
    if float(a.std()) < 1.0 or float(b.std()) < 1.0:
        return None
    window = cv2.createHanningWindow((a.shape[1], a.shape[0]), cv2.CV_32F)
    (dx, dy), response = cv2.phaseCorrelate(a, b, window)
    if response < 0.08 or abs(dx) > 12 or abs(dy) > 12:
        return None
    return 2.0 * dx, 2.0 * dy


def slide(picture: np.ndarray, dx: float, dy: float) -> np.ndarray:
    """Shift a page picture by (dx, dy) pixels."""
    h, w = picture.shape[:2]
    return cv2.warpAffine(picture, np.float32([[1, 0, dx], [0, 1, dy]]), (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def full_frame_page(frame: np.ndarray, quarter_turns: int = 0) -> np.ndarray:
    """No sheet found: treat the whole camera frame as the page."""
    h, w = frame.shape[:2]
    scale = config.PAGE_LONG / float(max(h, w))
    page = cv2.resize(frame, (max(1, int(round(w * scale))), max(1, int(round(h * scale)))), interpolation=cv2.INTER_AREA)
    return _rotate(page, quarter_turns)


def ink_strength(page: np.ndarray) -> np.ndarray:
    """How much darker each spot is than the paper around it (0 = blank paper).

    Works on the brightest color channel, so highlighter (which stays bright in at least one
    channel) does not count as ink. Comparing with the surroundings, not with a fixed level,
    means a shadow lying across the sheet does not count as ink either.
    """
    b, g, r = cv2.split(page)
    v = cv2.GaussianBlur(cv2.max(cv2.max(b, g), r), (3, 3), 0)
    around = cv2.blur(v, (config.INK_BLOCK, config.INK_BLOCK), borderType=cv2.BORDER_REPLICATE)
    strength = cv2.subtract(around, v)
    b = 10  # ignore the very edge of the sheet
    strength[:b, :] = 0
    strength[-b:, :] = 0
    strength[:, :b] = 0
    strength[:, -b:] = 0
    return strength


def strength_to_mask(strength: np.ndarray) -> np.ndarray:
    """White where the ink is dark enough to count."""
    return cv2.threshold(strength, max(0, config.INK_C - 1), 255, cv2.THRESH_BINARY)[1]


def ink_mask(page: np.ndarray) -> np.ndarray:
    """White where there is dark ink (pen, pencil, print)."""
    return strength_to_mask(ink_strength(page))


def steady_strength(now: np.ndarray, before: List[np.ndarray]) -> np.ndarray:
    """The middle value of the last three ink pictures, spot by spot.

    One noisy camera frame cannot create ink (or erase it) this way, and a faint stroke keeps
    its true darkness. The earlier pictures are widened by a pixel so a tiny shake still lines up.
    """
    if len(before) < 2:
        return now
    k = np.ones((3, 3), np.uint8)
    a, b = cv2.dilate(before[-1], k), cv2.dilate(before[-2], k)
    return cv2.max(cv2.min(now, a), cv2.min(cv2.max(now, a), b))


def new_ink(steady: np.ndarray, old_strength: np.ndarray) -> np.ndarray:
    """White where there is ink now that the remembered page cannot explain.

    New ink has to be clearly darker than anything the old page had within a few pixels. A faint
    old stroke that drifts across the "is it ink" line is therefore not new, while a real pen
    stroke drawn next to faint old marks still is.
    """
    nearby = cv2.dilate(old_strength, np.ones((9, 9), np.uint8))
    bar = cv2.addWeighted(nearby, 1.6, nearby, 0.0, 4.0)
    darker = cv2.compare(steady, bar, cv2.CMP_GT)
    return cv2.bitwise_and(darker, strength_to_mask(steady))


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
    per_channel = cv2.merge([gain * float(wb[0]), gain * float(wb[1]), gain * float(wb[2])])
    return cv2.multiply(page, per_channel, dtype=cv2.CV_8U)  # rounds and clips to 0..255


def page_gray(page: np.ndarray) -> np.ndarray:
    """Smoothed grayscale page, used to notice things lying on the sheet."""
    return cv2.GaussianBlur(cv2.cvtColor(page, cv2.COLOR_BGR2GRAY), (9, 9), 0)


def page_saturation(page: np.ndarray) -> np.ndarray:
    """Smoothed colorfulness of the page: paper is near 0, skin and most objects are well above."""
    return cv2.GaussianBlur(cv2.cvtColor(page, cv2.COLOR_BGR2HSV)[..., 1], (9, 9), 0)


def cover_mask(
    gray: np.ndarray,
    base_gray: np.ndarray,
    highlight_mask: np.ndarray,
    sat: Optional[np.ndarray] = None,
    base_sat: Optional[np.ndarray] = None,
) -> np.ndarray:
    """White where something wide (a hand, an arm, a pen) hides the page.

    Compares the page with how it looked when it was clear. Pen strokes are
    too thin to survive the clean-up, drawn symbols are too small, and
    highlighter is excluded by color, so only real objects remain.

    When the colorfulness pictures are given too, a shadow is told apart from an object: a
    shadow only makes the paper darker, it does not change its color or blot it out. Shadows
    come and go while someone writes and must not stop Glyph reading. A hand, by its color, is
    caught even where it is about as bright as the paper.
    """
    mb = float(np.median(base_gray[::8, ::8]))
    mc = float(np.median(gray[::8, ::8]))
    gain = min(1.4, max(0.7, mb / max(mc, 1.0)))  # even out exposure changes
    cur = cv2.convertScaleAbs(gray, alpha=gain) if abs(gain - 1.0) > 0.02 else gray
    _, m = cv2.threshold(cv2.absdiff(cur, base_gray), config.COVER_DIFF, 255, cv2.THRESH_BINARY)
    if sat is not None and base_sat is not None:
        more_color = cv2.subtract(sat, base_sat)
        colored = cv2.threshold(more_color, 35, 255, cv2.THRESH_BINARY)[1]
        same_color = cv2.threshold(more_color, 22, 255, cv2.THRESH_BINARY_INV)[1]
        # Lighting: a shadow arriving (darker) or leaving (brighter), with the paper still showing.
        not_blotted = cv2.compare(cur, cv2.convertScaleAbs(base_gray, alpha=0.45), cv2.CMP_GT)
        not_glaring = cv2.compare(cv2.convertScaleAbs(cur, alpha=0.45), base_gray, cv2.CMP_LT)
        shadow = cv2.bitwise_and(cv2.bitwise_and(not_blotted, not_glaring), same_color)
        m = cv2.bitwise_or(cv2.bitwise_and(m, cv2.bitwise_not(shadow)), colored)
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
    tx0, ty0, tx1, ty1 = box
    x0, y0 = max(0, tx0 - pad), max(0, ty0 - pad)
    x1, y1 = min(w, tx1 + pad), min(h, ty1 + pad)
    crop = page[y0:y1, x0:x1]
    near = cv2.dilate(fresh[y0:y1, x0:x1], np.ones((13, 13), np.uint8))
    if tx1 - tx0 <= 220 and ty1 - ty0 <= 220:
        # One small mark: show all of it at full contrast, including any thin stroke of it that
        # was too faint to be picked out as new ink.
        cv2.rectangle(near, (tx0 - x0 - 8, ty0 - y0 - 8), (tx1 - x0 + 8, ty1 - y0 + 8), 255, -1)
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
