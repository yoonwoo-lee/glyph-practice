"""Simulated camera frames: a sheet of paper on a desk that gets marked up.

Lets the whole app run with no camera. Also the basis of the tests.
"""

from __future__ import annotations

import math
from typing import Dict, List, Tuple

import cv2
import numpy as np

INK = (35, 30, 30)
PEN = (95, 45, 25)  # blue-black ballpoint
FONT = cv2.FONT_HERSHEY_SIMPLEX
HAND = cv2.FONT_HERSHEY_SCRIPT_SIMPLEX
PAGE_W, PAGE_H = 850, 1100

NOTES = [
    "Newton's first law: an object stays at rest or moves at",
    "constant velocity unless a net force acts on it. This",
    "resistance to changes in motion is called inertia.",
    "Momentum is the product of mass and velocity: p = m v.",
    "Impulse equals the change in momentum of an object.",
]
NOTES_X, NOTES_Y, NOTES_DY, NOTES_SCALE = 70, 560, 44, 0.74

# Highlighter colors as (B, G, R).
MARKER = {
    "yellow": (90, 235, 255),
    "green": (130, 240, 150),
    "pink": (190, 120, 250),
    "blue": (250, 200, 120),
}


def base_page() -> np.ndarray:
    """A worksheet: one physics problem with some working, then a few notes."""
    page = np.full((PAGE_H, PAGE_W, 3), 244, np.uint8)
    cv2.putText(page, "Physics 1A  -  Practice", (70, 90), FONT, 1.0, INK, 2, cv2.LINE_AA)
    cv2.line(page, (70, 110), (780, 110), INK, 1, cv2.LINE_AA)
    for i, line in enumerate(
        [
            "Problem 1.  A 2.0 kg block slides down a frictionless",
            "incline at 30 degrees. Find the acceleration of the block.",
        ]
    ):
        cv2.putText(page, line, (70, 170 + 40 * i), FONT, 0.74, INK, 2, cv2.LINE_AA)
    for i, line in enumerate(["N = m g cos(30)", "F = m g cos(30)", "a = F / m = 8.5 ?"]):
        cv2.putText(page, line, (110, 300 + 52 * i), HAND, 1.0, PEN, 2, cv2.LINE_AA)
    cv2.putText(page, "Notes", (70, 505), FONT, 0.9, INK, 2, cv2.LINE_AA)
    for i, line in enumerate(NOTES):
        cv2.putText(page, line, (NOTES_X, NOTES_Y + NOTES_DY * i), FONT, NOTES_SCALE, INK, 2, cv2.LINE_AA)
    return page


def _word_span(line_no: int, word: str) -> Tuple[int, int, int]:
    """x0, x1 and text baseline y of a word inside the notes."""
    line = NOTES[line_no]
    start = line.index(word)
    (before, _), _ = cv2.getTextSize(line[:start], FONT, NOTES_SCALE, 2)
    (width, _), _ = cv2.getTextSize(word, FONT, NOTES_SCALE, 2)
    return NOTES_X + before, NOTES_X + before + width, NOTES_Y + NOTES_DY * line_no


def draw_spark(page: np.ndarray, center=(640, 330), radius=30) -> None:
    """The hint symbol: a hand-drawn starburst next to the problem."""
    cx, cy = center
    for k in range(4):
        a = math.pi * k / 4 + 0.12
        dx, dy = int(radius * math.cos(a)), int(radius * math.sin(a))
        cv2.line(page, (cx - dx, cy - dy), (cx + dx, cy + dy), PEN, 3, cv2.LINE_AA)


def draw_underline(page: np.ndarray, line_no: int = 2, word: str = "inertia") -> None:
    x0, x1, y = _word_span(line_no, word)
    cv2.line(page, (x0 - 2, y + 11), (x1 + 2, y + 12), PEN, 3, cv2.LINE_AA)


def draw_highlight(page: np.ndarray, line_no: int, color: str, word: str = "") -> None:
    """Run a highlighter over a whole line of the notes, or just one phrase."""
    if word:
        x0, x1, y = _word_span(line_no, word)
    else:
        (width, _), _ = cv2.getTextSize(NOTES[line_no], FONT, NOTES_SCALE, 2)
        x0, x1, y = NOTES_X, NOTES_X + width, NOTES_Y + NOTES_DY * line_no
    x0, x1, y0, y1 = x0 - 6, x1 + 6, y - 27, y + 9
    tint = np.array(MARKER[color], np.float32) / 255.0
    page[y0:y1, x0:x1] = (page[y0:y1, x0:x1].astype(np.float32) * tint).astype(np.uint8)


def draw_handwriting(page: np.ndarray, text: str = "a = g sin(30)", org=(110, 465)) -> None:
    cv2.putText(page, text, org, HAND, 1.0, PEN, 2, cv2.LINE_AA)


def draw_check(page: np.ndarray, at=(470, 462), size: int = 30) -> None:
    """The check symbol: a short stroke down, then a longer one up to the right. `at` is its low point."""
    x, y = at
    pts = np.array([[x - size // 3, y - size // 3], [x, y], [x + int(size * 0.8), y - size]], np.int32)
    cv2.polylines(page, [pts], False, PEN, 3, cv2.LINE_AA)


def draw_boxed_answer(page: np.ndarray, text: str = "a = g sin(30) = 4.9", org=(110, 465)) -> None:
    """The student writes the corrected line under the working and boxes it: check this answer."""
    draw_handwriting(page, text, org)
    (width, _), _ = cv2.getTextSize(text, HAND, 1.0, 2)
    cv2.rectangle(page, (org[0] - 12, org[1] - 34), (org[0] + width + 14, org[1] + 10), PEN, 3, cv2.LINE_AA)


def draw_target(page: np.ndarray, center=(740, 420), radius: int = 24) -> None:
    """The practice symbol: a small circle inside a bigger one, next to the problem."""
    cv2.circle(page, center, radius, PEN, 3, cv2.LINE_AA)
    cv2.circle(page, center, max(4, radius // 3), PEN, 3, cv2.LINE_AA)


# ---- the sheet for editor mode: a page of reading --------------------------------------------

READING_TITLE = "Reading 4  -  Urban heat islands"
READING = [
    "Cities are often several degrees warmer than the",
    "land around them. Dark roofs and asphalt have a low",
    "albedo: they absorb sunlight and release it as heat",
    "after dark. Tall buildings trap that heat, and cars",
    "and air conditioners add waste heat of their own.",
    "",
    "The effect is strongest on calm summer nights, when",
    "stored heat cannot escape. Heat waves exacerbate it,",
    "and the people most exposed often have the least shade.",
    "Trees, cool roofs and lighter pavement all cut the heat.",
]
READING_X, READING_Y, READING_TITLE_Y = 110, 200, 90
BOXED = (2, "heat")  # the word the demo draws a box round: (line, word)


def reading_page() -> np.ndarray:
    """A page of dense reading: a title and two paragraphs."""
    page = np.full((PAGE_H, PAGE_W, 3), 244, np.uint8)
    cv2.putText(page, READING_TITLE, (70, READING_TITLE_Y), FONT, 1.0, INK, 2, cv2.LINE_AA)
    cv2.line(page, (70, 110), (780, 110), INK, 1, cv2.LINE_AA)
    for i, line in enumerate(READING):
        if line:
            cv2.putText(page, line, (READING_X, READING_Y + NOTES_DY * i), FONT, NOTES_SCALE, INK, 2, cv2.LINE_AA)
    return page


def _reading_span(line_no: int, word: str, start: int = 0) -> Tuple[int, int, int]:
    """x0, x1 and text baseline y of a word in the reading (the first one at or after `start`)."""
    line = READING[line_no]
    at = line.index(word, start)
    (before, _), _ = cv2.getTextSize(line[:at], FONT, NOTES_SCALE, 2)
    (width, _), _ = cv2.getTextSize(word, FONT, NOTES_SCALE, 2)
    return READING_X + before, READING_X + before + width, READING_Y + NOTES_DY * line_no


def reading_places(word: str) -> List[List[int]]:
    """Where a word stands in the reading, apart from the boxed one: [ymin, xmin, ymax, xmax] from 0 to 1000."""
    out = []

    def add(x0, x1, y, up):
        out.append([int(1000 * (y - up) / PAGE_H), int(1000 * (x0 - 3) / PAGE_W), int(1000 * (y + 8) / PAGE_H), int(1000 * (x1 + 3) / PAGE_W)])

    at = READING_TITLE.lower().find(word.lower())
    if at >= 0:
        (before, _), _ = cv2.getTextSize(READING_TITLE[:at], FONT, 1.0, 2)
        (width, _), _ = cv2.getTextSize(READING_TITLE[at : at + len(word)], FONT, 1.0, 2)
        add(70 + before, 70 + before + width, READING_TITLE_Y, 30)
    for i, line in enumerate(READING):
        low, start = line.lower(), 0
        while True:
            at = low.find(word.lower(), start)
            if at < 0:
                break
            start = at + len(word)
            if (i, word) == BOXED and at == low.find(word.lower()):
                continue  # the boxed one itself
            x0, x1, y = _reading_span(i, line[at : at + len(word)], at)
            add(x0, x1, y, 24)
    return out


def draw_reading_underline(page: np.ndarray, line_no: int = 2, word: str = "albedo") -> None:
    x0, x1, y = _reading_span(line_no, word)
    cv2.line(page, (x0 - 2, y + 11), (x1 + 2, y + 12), PEN, 3, cv2.LINE_AA)


def draw_box(page: np.ndarray, line_no: int = BOXED[0], word: str = BOXED[1]) -> None:
    """A box round a word: find every other place it appears."""
    x0, x1, y = _reading_span(line_no, word)
    cv2.rectangle(page, (x0 - 5, y - 29), (x1 + 7, y + 11), PEN, 3, cv2.LINE_AA)


def draw_circle(page: np.ndarray, line_no: int = 7, word: str = "exacerbate") -> None:
    """A circle round a word: synonyms."""
    x0, x1, y = _reading_span(line_no, word)
    cv2.ellipse(page, ((x0 + x1) // 2, y - 9), ((x1 - x0) // 2 + 7, 23), 0, 0, 360, PEN, 3, cv2.LINE_AA)


def draw_margin_line(page: np.ndarray, first: int = 6, last: int = 9) -> None:
    """A line down the margin beside a passage: a summary of it."""
    x, y0, y1 = READING_X - 26, READING_Y + NOTES_DY * first - 24, READING_Y + NOTES_DY * last + 8
    cv2.line(page, (x, y0), (x + 2, y1), PEN, 3, cv2.LINE_AA)


def draw_reading_highlight(page: np.ndarray, line_no: int = 9, color: str = "blue") -> None:
    (width, _), _ = cv2.getTextSize(READING[line_no], FONT, NOTES_SCALE, 2)
    x0, x1, y = READING_X, READING_X + width, READING_Y + NOTES_DY * line_no
    x0, x1, y0, y1 = x0 - 6, x1 + 6, y - 27, y + 9
    tint = np.array(MARKER[color], np.float32) / 255.0
    page[y0:y1, x0:x1] = (page[y0:y1, x0:x1].astype(np.float32) * tint).astype(np.uint8)


def build_reading_steps(corners=None) -> Dict[str, np.ndarray]:
    """Named camera frames of the reading being marked up, for the editor demo and the tests."""
    page = reading_page()
    steps = {"blank": desk_scene(page, corners=corners)}
    draw_reading_underline(page)
    steps["underline"] = desk_scene(page, corners=corners)
    draw_box(page)
    steps["box"] = desk_scene(page, corners=corners)
    draw_circle(page)
    steps["circle"] = desk_scene(page, corners=corners)
    draw_reading_highlight(page)
    steps["highlight"] = desk_scene(page, corners=corners)
    draw_margin_line(page)
    steps["margin"] = desk_scene(page, corners=corners)
    return steps


TILTED = [[640, 150], [1290, 95], [1420, 1010], [520, 960]]  # camera off to one side, sheet turned


WOOD = (70, 130, 200)  # a wooden desk under a lamp, as on Yoon Woo's camera: bright and orange


def desk_scene(page: np.ndarray, shift=(0, 0), size=(1920, 1080), corners=None, desk_color=(52, 66, 84)) -> np.ndarray:
    """Put the sheet on a desk (a dark one unless a color is given), seen slightly from the side."""
    w, h = size
    desk = np.zeros((h, w, 3), np.uint8)
    desk[:] = desk_color
    grain = np.random.RandomState(7).randint(-6, 7, (h, w, 1)).astype(np.int16)
    desk = np.clip(desk.astype(np.int16) + grain, 0, 255).astype(np.uint8)
    sx, sy = shift
    quad = np.array(corners or [[590, 50], [1330, 66], [1352, 1030], [566, 1012]], np.float32) + np.array([sx, sy], np.float32)
    src = np.array([[0, 0], [PAGE_W - 1, 0], [PAGE_W - 1, PAGE_H - 1], [0, PAGE_H - 1]], np.float32)
    m = cv2.getPerspectiveTransform(src, quad)
    warped = cv2.warpPerspective(page, m, (w, h), flags=cv2.INTER_AREA)
    mask = cv2.warpPerspective(np.full((PAGE_H, PAGE_W), 255, np.uint8), m, (w, h))
    desk[mask > 127] = warped[mask > 127]
    return desk


def warm_shadow(page: np.ndarray, top: int = 0) -> np.ndarray:
    """The flat sheet with a warm shadow over it from `top` down: darker, and beige where it was
    white. What a sheet looks like when someone leans over it and only light bounced off a
    wooden desk reaches the paper (Nov 21: colorfulness 82 where blank paper has about 30)."""
    out = page.copy()
    out[top:] = np.clip(out[top:].astype(np.float32) * np.array([0.49, 0.61, 0.72], np.float32), 0, 255).astype(np.uint8)
    return out


def add_hand(scene: np.ndarray, skin=(128, 160, 208)) -> np.ndarray:
    """A forearm and hand reaching over the lower half of the sheet."""
    out = scene.copy()
    cv2.line(out, (1900, 1070), (1080, 720), skin, 170, cv2.LINE_AA)
    cv2.ellipse(out, (1000, 690), (170, 120), 20, 0, 360, skin, -1, cv2.LINE_AA)
    cv2.line(out, (1500, 950), (1900, 1075), (70, 60, 60), 180, cv2.LINE_AA)  # sleeve
    return out


def build_steps(corners=None) -> Dict[str, np.ndarray]:
    """Named camera frames used by the demo and the tests."""
    page = base_page()
    steps = {"blank": desk_scene(page, corners=corners)}
    draw_spark(page)
    steps["spark"] = desk_scene(page, corners=corners)
    draw_underline(page)
    steps["underline"] = desk_scene(page, corners=corners)
    draw_highlight(page, 0, "yellow")
    draw_highlight(page, 3, "green")
    steps["highlights"] = desk_scene(page, corners=corners)
    draw_boxed_answer(page)
    steps["check"] = desk_scene(page, corners=corners)
    draw_target(page)
    steps["target"] = desk_scene(page, corners=corners)
    draw_check(page, (700, 215), 34)  # next to the problem: show me the answer
    steps["answer"] = desk_scene(page, corners=corners)
    return steps


# ---- making the simulated camera less perfect (used by tests/test_rough.py) ----


def lamp(scene: np.ndarray, dark: float = 0.55, warm: bool = True) -> np.ndarray:
    """A desk lamp on one side: bright at top-left, falling off to `dark`, with a warm tint."""
    h, w = scene.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    fall = 1.0 - (1.0 - dark) * ((xx / w) * 0.65 + (yy / h) * 0.35)
    out = scene.astype(np.float32) * fall[..., None]
    if warm:
        out *= np.array([0.86, 0.95, 1.0], np.float32)  # less blue
    return np.clip(out, 0, 255).astype(np.uint8)


def glare(scene: np.ndarray, center=(1050, 560), size=(260, 170), strength: float = 70.0) -> np.ndarray:
    """A soft bright patch, like a lamp reflecting off the paper."""
    h, w = scene.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = ((xx - center[0]) / size[0]) ** 2 + ((yy - center[1]) / size[1]) ** 2
    return np.clip(scene.astype(np.float32) + (strength * np.exp(-d))[..., None], 0, 255).astype(np.uint8)


def soft_focus(scene: np.ndarray, k: int = 7) -> np.ndarray:
    return cv2.GaussianBlur(scene, (k, k), 0)


def dim(scene: np.ndarray, level: float = 0.6) -> np.ndarray:
    return np.clip(scene.astype(np.float32) * level, 0, 255).astype(np.uint8)


def sensor(scene: np.ndarray, rng: np.random.RandomState, noise: float = 4.0, flicker: float = 0.03) -> np.ndarray:
    """What changes from one camera frame to the next: grain and small exposure shifts."""
    gain = 1.0 + rng.uniform(-flicker, flicker)
    grain = rng.normal(0.0, noise, scene.shape).astype(np.float32)
    return np.clip(scene.astype(np.float32) * gain + grain, 0, 255).astype(np.uint8)


def demo_frames(mode: str = "student") -> List[np.ndarray]:
    """The demo for one mode: a worksheet for student mode, a page of reading for editor mode."""
    if mode == "editor":
        s = build_reading_steps()
        return [s["blank"], s["underline"], s["box"], s["circle"], s["highlight"], s["margin"]]
    s = build_steps()
    return [s["blank"], s["spark"], s["underline"], s["highlights"], s["check"], s["target"], s["answer"]]
