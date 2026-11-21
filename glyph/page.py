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

    It is kept as a plain picture, so that it can be turned when the page view is turned
    (`HighlightStore.turn`). What is compared is worked out from it in `_words`.
    """
    small = cv2.resize(ink_strength(page), None, fx=1 / 3.0, fy=1 / 3.0, interpolation=cv2.INTER_AREA).astype(np.float32)
    return cv2.GaussianBlur(small, (3, 3), 0)


def _words(signature: np.ndarray) -> np.ndarray:
    """Two pages of the same reading have their lines in the same places and differ only in the
    words, so what a whole line has in common is taken out and the shapes of the words are kept.

    This works along the lines of text as the page is seen now, so it has to be done after any
    turning, not before: a signature filtered first and turned afterwards matched the same sheet
    at 0.43 where 0.6 is needed, and the sheet got a new page number on Rotate (Nov 20).
    """
    return signature - cv2.blur(signature, (31, 1))


def same_page(a: np.ndarray, b: np.ndarray) -> float:
    """How alike two page signatures are: high for the same sheet, near 0 for different ones.

    The page is compared piece by piece, and each piece may sit a few pixels off. A sheet that
    was put back slightly turned or shifted therefore still counts as the same sheet, and so does
    one that was put back the other way up.
    """
    if a.shape != b.shape:
        return 0.0
    a, b = _words(a), _words(b)
    return max(_alike(a, b), _alike(a, np.ascontiguousarray(b[::-1, ::-1])))


def can_be_told_apart(signature: np.ndarray) -> bool:
    """False for a sheet with so little on it (blank, or a word or two) that it could not be
    recognised if it came back."""
    signature = _words(signature)
    h, w = signature.shape[:2]
    written = 0
    for row in range(5):
        for col in range(4):
            if float(signature[row * h // 5 : (row + 1) * h // 5, col * w // 4 : (col + 1) * w // 4].std()) >= 0.6:
                written += 1
    return written >= 3


def _alike(a: np.ndarray, b: np.ndarray) -> float:
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
    """Find the paper in the camera picture: (corners, clean, touches, fill). See find_sheet."""
    return find_sheet(frame)[:4]


# How bright, compared with the brightest things in view, something gray has to be to count as
# paper. Tried from the most forgiving up. The low levels keep a sheet whole when a deep shadow
# lies across it; the high ones separate it from gray things next to it (a sweatshirt, a laptop).
PAPER_LEVELS = (0.38, 0.5, 0.62, 0.74)
PAPER_SAT = 75  # paper is less colorful than this (0-255); wood and skin are well above


def _paper_sat_in_view(sat: np.ndarray, val: np.ndarray, bright: float) -> Optional[float]:
    """How colorful paper may be in this picture, when PAPER_SAT is too strict for it.

    In a warm shadow (someone leaning over the sheet, so that only light bounced off a wooden
    desk reaches it) white paper comes out beige: colorfulness 80 or so where PAPER_SAT allows
    75, against 150 and more for the desk (Nov 21: the sheet was "not in view" while Yoon Woo
    wrote on its last question). When the bright things in view fall into two clear groups by
    colorfulness, the less colorful one being that kind of paper, the level halfway between the
    two is returned. None when PAPER_SAT already fits, or when there is no such split (a bare
    desk is one group, and must not be split into "paper" and "desk").
    """
    px = sat[val > PAPER_LEVELS[0] * bright]
    if px.size < 2000:
        return None
    level, _ = cv2.threshold(px.reshape(-1, 1), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    low, high = px[px <= level], px[px > level]
    if low.size < 0.08 * px.size or high.size < 0.08 * px.size:
        return None
    paper, desk = float(np.median(low)), float(np.median(high))
    if desk - paper < 45 or paper > 110 or paper + 25 < PAPER_SAT:
        return None
    return min(135.0, 0.5 * (paper + desk))


def find_sheet(frame: np.ndarray, info: Optional[dict] = None) -> Tuple[Optional[np.ndarray], bool, int, float, bool]:
    """Find the paper in the camera picture.

    Returns (corners, clean, touches, fill, cut_off). `clean` is False when something (a hand, a pen)
    breaks the outline, so the caller can keep using the last good corners. `touches` is how
    many edges of the camera picture the sheet reaches: 1 or 2 means part of it may be out of
    view. `fill` is how much of the four-cornered outline is visibly paper: it drops when a hand
    or an object reaches onto the sheet. Corners are None when no sheet stands out, for example
    when the paper fills the whole frame or sits on a white desk. `cut_off` is True when the
    paper itself runs off the edge of the picture.

    Two ways of looking are tried. By color: paper is the big area that is neither colorful nor
    dark, which holds up on a wooden desk with glare and with shadows lying across the sheet.
    Several brightness levels are tried, and an outline only counts when every side of it is a
    real edge of the paper: gray clothing or a gray laptop touching the sheet is otherwise taken
    for more paper (Nov 19: the page view included a sweatshirt and the hands in front of it).
    By brightness: the largest bright shape, which works on a dark desk in any light.

    `info`, when given, receives "sat_limit": how colorful paper was allowed to be for the
    answer (PAPER_SAT, or more for a sheet in a warm shadow; see _paper_sat_in_view).
    """
    h, w = frame.shape[:2]
    scale = 640.0 / w
    small = cv2.resize(frame, (640, max(1, int(round(h * scale)))), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (5, 5), 0)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    sat, val = hsv[..., 1], hsv[..., 2]
    bright = float(np.percentile(val, 95))
    best, rough, rough_warm = None, None, None
    cut_off = False
    limits = [float(PAPER_SAT)]
    warm = _paper_sat_in_view(sat, val, bright)
    if warm is not None and warm > PAPER_SAT:
        # Part or all of the sheet is in warm light. Look with both limits and take the bigger
        # clean sheet: with the usual limit alone, the part still in white light can pass for
        # a whole sheet (its fourth "edge" being where the shadow starts).
        limits.append(warm)
    used = limits[0]
    for sat_limit in limits:
        for level in PAPER_LEVELS:
            mask = ((sat < sat_limit) & (val > level * bright)).astype(np.uint8) * 255
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
            if level == PAPER_LEVELS[-1]:
                cut_off = _runs_off_the_picture(mask)  # judged on paper alone, not on gray things beside it
            quad, clean, touches, fill = _outline(mask, strict=False)
            if quad is None:
                continue
            if rough is None:
                rough = (quad, touches, fill)
            if sat_limit != limits[0] and _sheet_like(quad, fill) and (rough_warm is None or cv2.contourArea(order_quad(quad)) > cv2.contourArea(order_quad(rough_warm[0]))):
                rough_warm = (quad, touches, fill)
            if not clean or not _square_corners(quad):
                continue
            sides = _paper_edges(order_quad(quad), sat, val, bright, mask, sat_limit)
            real = sum(1 for side in sides if side is True)
            if real < 2 or any(side is False for side in sides):
                continue
            key = (real, cv2.contourArea(order_quad(quad)))  # most real edges, then the biggest
            if best is None or key > best[0]:
                best, used = (key, quad, touches, fill), sat_limit
    if rough_warm is not None and best is not None and cv2.contourArea(order_quad(rough_warm[0])) > 1.3 * best[0][1]:
        # In warm light, with something on the sheet that spoils its outline (an arm): the part
        # of the sheet still in white light is clean, but it is not the sheet. Say what is
        # there, as unclear, so the outline that was trusted before stays in use.
        if info is not None:
            info["sat_limit"] = limits[-1]
        return order_quad(rough_warm[0] / scale), False, rough_warm[1], rough_warm[2], cut_off
    if info is not None:
        info["sat_limit"] = used if best is not None else limits[-1]
    if best is not None:
        return order_quad(best[1] / scale), True, best[2], best[3], False
    by_light = _outline(_paper_by_brightness(small), strict=True)
    if by_light[0] is not None and by_light[1] and _square_corners(by_light[0]):
        return order_quad(by_light[0] / scale), True, by_light[2], by_light[3], False
    if by_light[0] is not None:
        quad, touches, fill = by_light[0], by_light[2], by_light[3]
    elif rough is not None:
        quad, touches, fill = rough
    else:
        return None, False, 0, 0.0, cut_off
    return order_quad(quad / scale), False, touches, fill, cut_off


def _sheet_like(quad: np.ndarray, fill: float) -> bool:
    """Roughly a sheet of paper, even with a hand or an arm reaching onto it: square corners,
    the proportions of a sheet, most of the outline filled."""
    o = order_quad(quad)
    a = float(np.linalg.norm(o[1] - o[0]) + np.linalg.norm(o[2] - o[3]))
    b = float(np.linalg.norm(o[3] - o[0]) + np.linalg.norm(o[2] - o[1]))
    return fill >= 0.7 and _square_corners(quad) and 1.15 <= max(a, b) / max(min(a, b), 1.0) <= 1.6


def _runs_off_the_picture(mask: np.ndarray) -> bool:
    """True when the biggest piece of paper in a mask lies along one or two edges of the picture
    for a good stretch: part of the sheet is out of the camera's view. (Along three or four
    edges it is not a sheet at all: a white desk, or paper filling the whole picture.)"""
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if n <= 1:
        return False
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    h, w = mask.shape[:2]
    if stats[i, cv2.CC_STAT_AREA] < 0.08 * h * w:
        return False
    runs = [
        int((labels[0, :] == i).sum()) / float(w),
        int((labels[h - 1, :] == i).sum()) / float(w),
        int((labels[:, 0] == i).sum()) / float(h),
        int((labels[:, w - 1] == i).sum()) / float(h),
    ]
    along = sum(1 for r in runs if r >= 0.12)
    return 1 <= along <= 2


def _square_corners(quad: np.ndarray, low: float = 62.0, high: float = 118.0) -> bool:
    """A sheet seen from above has four corners near 90 degrees. A shape with a slanted side is
    paper plus something else, or a piece of paper cut off by a shadow."""
    o = order_quad(quad)
    for i in range(4):
        u, v = o[i - 1] - o[i], o[(i + 1) % 4] - o[i]
        cos = float(u @ v) / max(1e-6, float(np.linalg.norm(u) * np.linalg.norm(v)))
        if not (low <= float(np.degrees(np.arccos(np.clip(cos, -1.0, 1.0)))) <= high):
            return False
    return True


def _paper_edges(o: np.ndarray, sat: np.ndarray, val: np.ndarray, bright: float, mask: np.ndarray, sat_limit: float = PAPER_SAT) -> list:
    """For each side of an outline: True (a real edge of the paper), False, or "frame" when the
    side runs along the edge of the camera picture.

    A real edge has paper just inside it and, just outside, something that is not paper: either
    colorful (a wooden desk, a hand) or much darker. A side that runs through the middle of
    something gray has the same gray on both sides.
    """
    h, w = val.shape[:2]
    center = o.mean(axis=0)
    out = []
    for i in range(4):
        a, b = o[i], o[(i + 1) % 4]
        d = b - a
        length = float(np.linalg.norm(d))
        if length < 8:
            out.append(False)
            continue
        n = np.array([-d[1], d[0]], np.float32) / length
        if float((center - a) @ n) < 0:
            n = -n  # n now points into the sheet
        good = total = off = 0
        for t in np.linspace(0.15, 0.85, 15):
            p = a + t * d
            xi, yi = int(round(p[0] + 4 * n[0])), int(round(p[1] + 4 * n[1]))
            xo, yo = int(round(p[0] - 4 * n[0])), int(round(p[1] - 4 * n[1]))
            if not (0 <= xi < w and 0 <= yi < h):
                continue
            if not (1 <= xo < w - 1 and 1 <= yo < h - 1):
                off += 1
                continue
            total += 1
            gray_outside = sat[yo, xo] < sat_limit and val[yo, xo] > PAPER_LEVELS[0] * bright
            if mask[yi, xi] and (not gray_outside or float(val[yo, xo]) < 0.72 * float(val[yi, xi])):
                good += 1
        if off >= 8:
            out.append("frame")
        else:
            out.append(total > 0 and good >= 0.7 * total)
    return out


def paper_share(page: np.ndarray, sat_limit: float = PAPER_SAT) -> float:
    """How much of a picture looks like paper: bright and not colorful. A flattened sheet scores
    near 1 even with a hand on it; a bare wooden desk scores near 0."""
    small = cv2.resize(page, None, fx=0.125, fy=0.125, interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    sat, val = hsv[..., 1], hsv[..., 2]
    floor = max(90.0, 0.5 * float(np.percentile(val, 95)))
    return float(((sat < sat_limit) & (val > floor)).mean())


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


def register(old_strength: np.ndarray, new_strength: np.ndarray) -> Tuple[Optional[np.ndarray], bool]:
    """How the remembered ink picture has to be moved to sit exactly on the page as it is now.

    Returns (matrix, sure). The 3x3 matrix is for `move`; it is None when nothing needs moving.
    `sure` is False when the two pictures could not be matched up: a different page, a page that
    has moved too far, or one mostly hidden. Whether ink is new cannot be judged then.

    A loose sheet never comes back to quite the same place: it slides, turns a little, and the
    measured corners shift when a hand hides one of them. A plain shift is not enough then, and
    on a page of print every line that lands two pixels off looks like new ink (Nov 19: half the
    words of a printed speech were sent to the model as "newly drawn"). So the page is compared
    in blocks, each block says where it went, and one perspective change is fitted to all of them.
    """
    if old_strength.shape != new_strength.shape:
        return None, False
    total = np.eye(3)
    moved = old_strength
    sure = False
    where = None
    for _ in range(3):  # each pass picks up blocks the one before could not reach
        step, written, agreed, at = _register_once(moved, new_strength)
        if written == 0:
            return None, True  # nothing written on the remembered page: nothing can be out of place
        if step is None:
            return None, False
        where = at if where is None else where
        sure = agreed >= max(1.0, 0.6 * written)
        total = step @ total
        if _shift_at(step, at) < 0.3:
            break
        moved = move(old_strength, total)
    # How far the writing itself moves. (Measured at the corners of the page, a change fitted to
    # writing in the middle of the sheet looks bigger than it is.)
    shift = _shift_at(total, where)
    if shift > 0.1 * max(old_strength.shape[:2]):
        return None, False  # so far off that the match is not to be trusted
    return (total if shift >= 0.75 else None), sure


def _register_once(old_strength: np.ndarray, new_strength: np.ndarray, rows: int = 8, cols: int = 6, reach: int = 14):
    """One pass of `register`: (matrix or None, blocks with writing, blocks that agree on it,
    where the matched blocks are)."""
    a = cv2.resize(old_strength, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA).astype(np.float32)
    b = cv2.resize(new_strength, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA).astype(np.float32)
    h, w = a.shape[:2]
    src, dst = [], []
    written = 0
    for r in range(rows):
        for c in range(cols):
            y0, y1 = r * h // rows, (r + 1) * h // rows
            x0, x1 = c * w // cols, (c + 1) * w // cols
            piece = np.ascontiguousarray(a[y0:y1, x0:x1])
            if float(piece.std()) < 2.0:
                continue  # nothing written in this block
            written += 1
            sy0, sx0 = max(0, y0 - reach), max(0, x0 - reach)
            area = np.ascontiguousarray(b[sy0 : min(h, y1 + reach), sx0 : min(w, x1 + reach)])
            if float(area.std()) < 2.0:
                continue
            res = cv2.matchTemplate(area, piece, cv2.TM_CCOEFF_NORMED)
            _, peak, _, (px, py) = cv2.minMaxLoc(res)
            if peak < 0.5:
                continue  # covered by a hand, or too little here to be sure
            fx, fy = float(px), float(py)
            if 0 < px < res.shape[1] - 1:  # finer than a pixel: the top of a curve through the peak
                left, mid, right = float(res[py, px - 1]), float(res[py, px]), float(res[py, px + 1])
                bend = left - 2 * mid + right
                if bend < 0:
                    fx += 0.5 * (left - right) / bend
            if 0 < py < res.shape[0] - 1:
                up, mid, down = float(res[py - 1, px]), float(res[py, px]), float(res[py + 1, px])
                bend = up - 2 * mid + down
                if bend < 0:
                    fy += 0.5 * (up - down) / bend
            cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            src.append((2 * cx, 2 * cy))
            dst.append((2 * (cx + sx0 + fx - x0), 2 * (cy + sy0 + fy - y0)))
    n = len(src)
    if n == 0:
        return None, written, 0, None
    src, dst = np.array(src, np.float32), np.array(dst, np.float32)
    m = np.eye(3)
    if n >= 10:
        found, inliers = cv2.findHomography(src, dst, cv2.RANSAC, 2.0)
        if found is not None and int(inliers.sum()) >= max(8, int(0.6 * n)) and 0.8 < float(np.linalg.det(found[:2, :2])) < 1.25:
            return found, written, int(inliers.sum()), src
    if n >= 4:
        found, inliers = cv2.estimateAffine2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=2.0)
        if found is not None and int(inliers.sum()) >= max(3, n // 2) and 0.8 < float(np.linalg.det(found[:, :2])) < 1.25:
            m[:2] = found
            return m, written, int(inliers.sum()), src
    shift = np.median(dst - src, axis=0)
    m[0, 2], m[1, 2] = float(shift[0]), float(shift[1])
    agreed = int((np.abs(dst - src - shift).max(axis=1) <= 2.0).sum())
    return m, written, agreed, src


def _shift_at(m: np.ndarray, points: np.ndarray) -> float:
    """The furthest any of the given points moves under a matrix, in pixels."""
    pts = np.asarray(points, np.float32).reshape(-1, 1, 2)
    return float(np.abs(cv2.perspectiveTransform(pts, m) - pts).max())


def move(picture: np.ndarray, m: np.ndarray) -> np.ndarray:
    """Apply a matrix from `register` to a page picture."""
    h, w = picture.shape[:2]
    return cv2.warpPerspective(picture, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


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

    That rule alone refuses everything within four pixels of print, which is where an underline
    under small type lies (see `_added_beside_print`).
    """
    nearby = cv2.dilate(old_strength, np.ones((9, 9), np.uint8))
    bar = cv2.addWeighted(nearby, 1.6, nearby, 0.0, 4.0)
    darker = cv2.compare(steady, bar, cv2.CMP_GT)
    new = cv2.bitwise_and(darker, strength_to_mask(steady))
    return cv2.bitwise_or(new, _added_beside_print(steady, old_strength))


SOLID_INK = 26  # a pen stroke is at least this much darker than the paper; faint pencil is not
_K25 = (25, 25)


def _added_beside_print(steady: np.ndarray, old_strength: np.ndarray) -> np.ndarray:
    """Solid ink where the paper was clean, close beside older ink that has not itself moved.

    Camera run of Nov 20: "ball" in small print, underlined a pixel or two below the letters with
    a line seven pixels thick. Only a 35-pixel sliver of it was far enough from the letters to
    count as new, and no look was sent.

    Being close to old ink is exactly what old ink does when the sheet has slipped a few pixels,
    which is why the main rule keeps its distance. The difference: when the sheet slips, the old
    ink is no longer where it was. So ink this close to print counts only where the print around
    it is still in place, spot for spot.
    """
    clean_before = cv2.compare(cv2.dilate(old_strength, np.ones((5, 5), np.uint8)), 6, cv2.CMP_LE)
    solid = cv2.bitwise_and(cv2.compare(steady, SOLID_INK, cv2.CMP_GE), clean_before)
    if cv2.countNonZero(solid) == 0:
        return solid
    old_mask = strength_to_mask(old_strength)
    # Old ink that is gone, or much fainter, at its own spot (give or take a pixel).
    still = cv2.compare(cv2.dilate(steady, np.ones((3, 3), np.uint8)), cv2.addWeighted(old_strength, 0.5, old_strength, 0.0, 0.0), cv2.CMP_GE)
    gone = cv2.bitwise_and(old_mask, cv2.bitwise_not(still))
    n_old = cv2.boxFilter(old_mask, cv2.CV_32F, _K25, normalize=False) / 255.0
    n_gone = cv2.boxFilter(gone, cv2.CV_32F, _K25, normalize=False) / 255.0
    in_place = (n_gone <= 0.1 * n_old + 2.0).astype(np.uint8) * 255
    return cv2.bitwise_and(solid, in_place)


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


def see_through(cover: np.ndarray, old_ink: np.ndarray, ink_now: np.ndarray, min_old: int = 300, share: float = 0.7, window: int = 81) -> np.ndarray:
    """A cover mask without the parts through which the remembered print still shows.

    A hand, an arm or a book hides what is printed under it. Light does not: a shadow that
    changes the color of the paper as well as its brightness (someone leaning over a sheet on a
    wooden desk leaves it lit by warm light off the wood) looks like an object to cover_mask,
    by color, yet every printed word under it is still where it was.

    Each connected piece of the mask is judged as a whole: with a fair amount of old ink under
    it, most of it still to be seen, the piece is light. A piece of light is dropped, except
    where the print under it has gone: that is a hand inside the shadow. Every other piece is
    kept whole, edges included (over blank paper there is nothing to tell by, and the outline of
    a fingertip must never pass for writing).
    """
    if cv2.countNonZero(cover) == 0:
        return cover
    n, labels, stats, _ = cv2.connectedComponentsWithStats(cover, connectivity=8)
    still = cv2.bitwise_and(old_ink, cv2.dilate(ink_now, np.ones((9, 9), np.uint8)))
    old_in = np.bincount(labels[old_ink > 0], minlength=n)
    still_in = np.bincount(labels[still > 0], minlength=n)
    light = (old_in >= min_old) & (still_in >= share * old_in)
    light[0] = False
    if not light.any():
        return cover
    # Where, inside the light, has the print gone? Counted over a window a couple of lines high.
    k = (window, window)
    old_n = cv2.boxFilter((old_ink > 0).astype(np.float32), -1, k, normalize=False)
    still_n = cv2.boxFilter((still > 0).astype(np.float32), -1, k, normalize=False)
    hidden = (old_n >= 40) & (still_n < 0.5 * old_n)
    out = cover.copy()
    out[light[labels] & ~hidden] = 0
    return remove_small(cv2.morphologyEx(out, cv2.MORPH_OPEN, _K15), int(config.COVER_MIN_FRAC * out.size)) if cv2.countNonZero(out) else out


def remove_small(mask: np.ndarray, min_area: int) -> np.ndarray:
    """Drop specks smaller than min_area pixels without thinning real strokes."""
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if n <= 1:
        return mask
    keep = stats[:, cv2.CC_STAT_AREA] >= min_area
    keep[0] = False
    return (keep[labels].astype(np.uint8)) * 255


def ink_groups(mask: np.ndarray, gap: int = 25) -> list:
    """Boxes (x, y, w, h) around the separate bits of ink in a mask. Strokes closer together
    than `gap` pixels count as one bit: the rays of a spark, the letters of a word."""
    if cv2.countNonZero(mask) == 0:
        return []
    joined = cv2.dilate(mask, np.ones((gap, gap), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(joined, connectivity=8)
    half = gap // 2
    return [(int(x) + half, int(y) + half, max(1, int(w) - 2 * half), max(1, int(h) - 2 * half)) for x, y, w, h, _ in stats[1:n]]


def mark_pieces(fresh: np.ndarray, gap: int = 25) -> list:
    """The separate things drawn in a mask of new ink, each as {"box": (x0, y0, x1, y1), "px",
    "hole"}. `hole` is how much of its box the piece shuts in: a circle drawn round a word or a
    letter shuts in most of it, a check mark or a spark nothing."""
    if cv2.countNonZero(fresh) == 0:
        return []
    joined = cv2.dilate(fresh, np.ones((gap, gap), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(joined, connectivity=8)
    out = []
    for i in range(1, n):
        x, y, w, h = (int(v) for v in stats[i][:4])
        own = ((labels[y : y + h, x : x + w] == i) & (fresh[y : y + h, x : x + w] > 0)).astype(np.uint8) * 255
        pts = cv2.findNonZero(own)
        if pts is None:
            continue
        bx, by, bw, bh = cv2.boundingRect(pts)
        tight = own[by : by + bh, bx : bx + bw]
        # Close the little gap where a loop's stroke starts and ends, then see what cannot be
        # reached from outside the box.
        shut = cv2.copyMakeBorder(cv2.morphologyEx(tight, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8)), 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
        cv2.floodFill(shut, None, (0, 0), 255)
        inside = shut.size - cv2.countNonZero(shut)
        out.append({"box": (x + bx, y + by, x + bx + bw, y + by + bh), "px": int(cv2.countNonZero(tight)), "hole": inside / float(max(1, bw * bh))})
    return out


def pick_mark(fresh: np.ndarray, action: str) -> Optional[Tuple[int, int, int, int]]:
    """Which of the things just drawn is the mark that was answered: its box (x0, y0, x1, y1).

    One look often holds more than one thing: the letter a student circled and the check mark
    drawn after it, a line of working and a spark. The model says what the mark means, not
    where it is, so the mark is picked by its shape: a check mark and a spark are open strokes
    about as tall as wide, a target and a circled question mark are closed rings, an underline
    is long and flat, a box or a circle round a word shuts the word in. None when there is no
    new ink; the box of everything when nothing fits.
    """
    pieces = [p for p in mark_pieces(fresh) if max(p["box"][2] - p["box"][0], p["box"][3] - p["box"][1]) >= 10]
    if not pieces:
        return mask_bbox(fresh)

    def size(p):
        x0, y0, x1, y1 = p["box"]
        return x1 - x0, y1 - y0

    def symbol_sized(p):
        w, h = size(p)
        return 14 <= max(w, h) <= 220 and min(w, h) >= 10 and max(w, h) <= 3 * min(w, h)

    def biggest(ps):
        return max(ps, key=lambda p: float(np.hypot(*size(p))))["box"]

    ring = [p for p in pieces if p["hole"] >= 0.2]
    open_ = [p for p in pieces if p["hole"] < 0.2]
    if action == "check":
        fit = ring or [p for p in open_ if symbol_sized(p)]  # a box round an answer (a tick, in an older legend)
    elif action in ("answer", "hint"):
        fit = [p for p in open_ if symbol_sized(p)]
    elif action in ("practice", "explain"):
        fit = [p for p in ring if symbol_sized(p)]
    elif action == "define":
        fit = [p for p in open_ if size(p)[0] >= 3 * size(p)[1]]
    elif action in ("find", "synonym"):
        fit = ring
    elif action == "summarize":
        fit = [p for p in open_ if size(p)[1] >= 3 * size(p)[0]]
    else:
        fit = []
    if fit:
        return biggest(fit)
    if len(pieces) == 1:
        return pieces[0]["box"]
    return mask_bbox(fresh)


def marks_only(mask: np.ndarray, gap: int = 25, min_side: int = 14, min_px: int = 30, edge: int = 16) -> np.ndarray:
    """Keep the new ink that could be a mark drawn on the sheet.

    Dropped: bits too small to be a mark (a speck of camera noise, a dot, the tip of a stroke
    caught mid-flicker; the smallest real marks are over 14 pixels long on the flattened page),
    and anything that reaches the very edge of the sheet. Fingers holding the paper and pens
    lying half on it come in from the edge, and their outlines look like dark strokes (Nov 19:
    fingertips were sent to the model as new ink). Nobody draws a mark on the last couple of
    millimetres of the paper.
    """
    if cv2.countNonZero(mask) == 0:
        return mask
    joined = cv2.dilate(mask, np.ones((gap, gap), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(joined, connectivity=8)
    half = gap // 2
    ph, pw = mask.shape[:2]
    keep = np.zeros(n, bool)
    for i in range(1, n):
        x, y, w, h = (int(v) for v in stats[i][:4])
        x0, y0, x1, y1 = x + half, y + half, x + w - half, y + h - half  # the ink itself
        if min(x0, y0) <= edge or x1 >= pw - edge or y1 >= ph - edge:
            continue
        px = cv2.countNonZero(mask[y : y + h, x : x + w][labels[y : y + h, x : x + w] == i])
        keep[i] = max(x1 - x0, y1 - y0) >= min_side and px >= min_px
    return cv2.bitwise_and(mask, keep[labels].astype(np.uint8) * 255)


def short_underline(fresh: np.ndarray, old: np.ndarray, min_len: int = 14) -> bool:
    """Is some of the new ink a short flat stroke lying right under (or beside) older ink?

    That is what an underline under a short word in small print comes to: "ball" in 10-point type
    is 25 pixels wide on the flattened page, and the part of the line that stays clear of the
    letters is a sliver of 30 to 80 pixels. It is too little to pass for writing by size alone, but
    a flat stroke right against print is rarely anything other than an underline.
    The stroke may run either way, for a sheet that is lying sideways.
    """
    if cv2.countNonZero(fresh) == 0:
        return False
    ph, pw = fresh.shape[:2]
    for x, y, w, h in ink_groups(fresh, gap=9):
        if w >= min_len and h <= max(6, w // 4):
            if cv2.countNonZero(old[max(0, y - 14) : y, x : x + w]) >= 1.5 * w:
                return True
        elif h >= min_len and w <= max(6, h // 4):
            left = cv2.countNonZero(old[y : y + h, max(0, x - 14) : x])
            right = cv2.countNonZero(old[y : y + h, x + w : min(pw, x + w + 14)])
            if max(left, right) >= 1.5 * h:
                return True
    return False


def whole_strokes(fresh: np.ndarray, ink: Optional[np.ndarray] = None, old: Optional[np.ndarray] = None) -> np.ndarray:
    """The new ink, filled out to the whole of each stroke.

    "New" is judged strictly: a line drawn right under a row of print only counts where it stays
    clear of the letters. This follows each new stroke along the ink that is on the page now, so
    an underline comes out in one piece.
    """
    if ink is None:
        return fresh
    grown = ink if old is None else cv2.bitwise_and(ink, cv2.bitwise_not(cv2.dilate(old, np.ones((5, 5), np.uint8))))
    grown = cv2.bitwise_or(grown, fresh)
    grown = cv2.bitwise_and(grown, cv2.dilate(fresh, np.ones((31, 31), np.uint8)))  # ...but not far
    n, labels = cv2.connectedComponents(grown, connectivity=8)
    keep = np.zeros(n, bool)
    keep[np.unique(labels[fresh > 0])] = True
    keep[0] = False
    return keep[labels].astype(np.uint8) * 255


def mask_bbox(mask: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
    """Bounding box (x0, y0, x1, y1) of the white pixels, or None."""
    pts = cv2.findNonZero(mask)
    if pts is None:
        return None
    x, y, w, h = cv2.boundingRect(pts)
    return int(x), int(y), int(x + w), int(y + h)


NEW_INK_COLOR = (147, 20, 255)  # hot pink (B, G, R): how new strokes are shown to the model


def make_focus_crop(page: np.ndarray, fresh: np.ndarray, pad: int = 70, ink: Optional[np.ndarray] = None, old: Optional[np.ndarray] = None, wide: bool = False):
    """Close-up of the new ink, with the new strokes colored pink and everything else as it is.

    The vision model is told that only the pink strokes are new. Fading the older writing, as
    this used to do, did not stop the model answering an old symbol again, and it made the words
    above a new underline hard to read. A stroke in a color no pen has is hard to mistake.

    The pink goes on the ink itself, by how dark each spot is, after the close-up is enlarged.
    Painting the whole "new ink" area instead turned a small spark into a solid pink blob (its
    arms are a pixel or two apart, so the area has no gaps), and the model saw no symbol in it
    (camera run of Nov 20).
    `wide` takes the close-up right across the page (for a line drawn down the margin).
    Returns (image, (x0, y0, x1, y1)) or (None, None) if there is no new ink.
    """
    box = mask_bbox(fresh)
    if box is None:
        return None, None
    h, w = fresh.shape[:2]
    tx0, ty0, tx1, ty1 = box
    x0, y0 = max(0, tx0 - pad), max(0, ty0 - pad)
    x1, y1 = min(w, tx1 + pad), min(h, ty1 + pad)
    if wide:  # a line down the margin: the passage beside it runs the width of the page
        x0, x1 = 0, w
    out = page[y0:y1, x0:x1].copy()
    strokes = whole_strokes(fresh, ink, old)[y0:y1, x0:x1]
    longest = max(out.shape[:2])
    f = min(4.0, 900.0 / longest) if longest < 900 else 1.0
    if f > 1.0:
        out = cv2.resize(out, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
        strokes = cv2.threshold(cv2.resize(strokes, (out.shape[1], out.shape[0]), interpolation=cv2.INTER_LINEAR), 60, 255, cv2.THRESH_BINARY)[1]
    r = max(1, int(round(1.5 * f)))
    near = cv2.dilate(strokes, np.ones((2 * r + 1, 2 * r + 1), np.uint8)) > 0
    # How dark each spot is against the paper right around it: the ink, without the gaps between strokes.
    v = cv2.max(cv2.max(out[:, :, 0], out[:, :, 1]), out[:, :, 2])
    k = int(15 * f) | 1
    paper = cv2.morphologyEx(v, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    dark = cv2.subtract(paper, v).astype(np.float32)
    amount = np.zeros(dark.shape, np.float32)
    if near.any():
        top = max(24.0, float(np.percentile(dark[near], 92)))
        amount = np.clip((dark - 0.22 * top) / (0.45 * top), 0.0, 1.0) * near
    if float((amount > 0.5).sum()) < 0.08 * max(1, int((strokes > 0).sum())):
        amount = (strokes > 0).astype(np.float32)  # a filled shape or very broad stroke: color all of it
    amount = amount[:, :, None]
    out = (out.astype(np.float32) * (1.0 - amount) + np.array(NEW_INK_COLOR, np.float32) * amount).astype(np.uint8)
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
