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


def desk_scene(page: np.ndarray, shift=(0, 0), size=(1920, 1080)) -> np.ndarray:
    """Put the sheet on a dark desk, seen slightly from the side."""
    w, h = size
    desk = np.zeros((h, w, 3), np.uint8)
    desk[:] = (52, 66, 84)
    grain = np.random.RandomState(7).randint(-6, 7, (h, w, 1)).astype(np.int16)
    desk = np.clip(desk.astype(np.int16) + grain, 0, 255).astype(np.uint8)
    sx, sy = shift
    quad = np.array([[590, 50], [1330, 66], [1352, 1030], [566, 1012]], np.float32) + np.array([sx, sy], np.float32)
    src = np.array([[0, 0], [PAGE_W - 1, 0], [PAGE_W - 1, PAGE_H - 1], [0, PAGE_H - 1]], np.float32)
    m = cv2.getPerspectiveTransform(src, quad)
    warped = cv2.warpPerspective(page, m, (w, h), flags=cv2.INTER_AREA)
    mask = cv2.warpPerspective(np.full((PAGE_H, PAGE_W), 255, np.uint8), m, (w, h))
    desk[mask > 127] = warped[mask > 127]
    return desk


def add_hand(scene: np.ndarray) -> np.ndarray:
    """A forearm and hand reaching over the lower half of the sheet."""
    out = scene.copy()
    skin = (128, 160, 208)
    cv2.line(out, (1900, 1070), (1080, 720), skin, 170, cv2.LINE_AA)
    cv2.ellipse(out, (1000, 690), (170, 120), 20, 0, 360, skin, -1, cv2.LINE_AA)
    cv2.line(out, (1500, 950), (1900, 1075), (70, 60, 60), 180, cv2.LINE_AA)  # sleeve
    return out


def build_steps() -> Dict[str, np.ndarray]:
    """Named camera frames used by the demo and the tests."""
    page = base_page()
    steps = {"blank": desk_scene(page)}
    draw_spark(page)
    steps["spark"] = desk_scene(page)
    draw_underline(page)
    steps["underline"] = desk_scene(page)
    draw_highlight(page, 0, "yellow")
    draw_highlight(page, 3, "green")
    steps["highlights"] = desk_scene(page)
    return steps


def demo_frames() -> List[np.ndarray]:
    s = build_steps()
    return [s["blank"], s["spark"], s["underline"], s["highlights"]]
