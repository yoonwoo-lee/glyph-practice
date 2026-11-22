"""Settings for Glyph. Every number here can be overridden in .env."""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _num(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return float(default)


# What the app calls itself: on the web page, in the browser tab and to the vision model. The name
# is still being decided, so it lives here and nowhere else. GLYPH_NAME in .env changes it.
APP_NAME = (os.getenv("GLYPH_NAME") or "Glyph").strip() or "Glyph"

# The flattened page is always this size (portrait or landscape).
PAGE_LONG = 1100
PAGE_SHORT = 850

# --- When Glyph looks at the page -------------------------------------------
# How long the picture must hold still before Glyph reads it.
SETTLE_SECONDS = _num("GLYPH_SETTLE_SECONDS", 1.0)
# Minimum gap between two calls to the vision model.
COOLDOWN_SECONDS = _num("GLYPH_COOLDOWN_SECONDS", 4.0)
# Hard cap on vision-model calls per minute (protects a free-tier key).
MAX_CALLS_PER_MIN = int(_num("GLYPH_MAX_CALLS_PER_MIN", 8))
# New ink smaller than this many pixels is treated as noise.
MIN_NEW_INK_PX = int(_num("GLYPH_MIN_NEW_INK_PX", 120))
# If more than this share of the page changes at once, it is a hand, a
# shadow or a new page, not writing.
BIG_CHANGE_FRAC = _num("GLYPH_BIG_CHANGE_FRAC", 0.04)
# Same idea, for old ink that disappeared (something is covering it).
MISSING_FRAC = _num("GLYPH_MISSING_FRAC", 0.35)
# A big change that stays put this long is accepted as the new page.
BIG_CHANGE_HOLD = _num("GLYPH_BIG_CHANGE_HOLD", 3.0)
# Something lying on the sheet (a hand, a pen) counts as a cover once it hides
# this share of the page. Ink next to a cover is ignored until it moves away.
COVER_MIN_FRAC = _num("GLYPH_COVER_MIN_FRAC", 0.004)
# How different (0-255) a patch must look from the clean page to be a cover.
COVER_DIFF = int(_num("GLYPH_COVER_DIFF", 32))
# A cover that stays put this long is accepted as part of the page.
COVER_HOLD = _num("GLYPH_COVER_HOLD", 20.0)
READ_FIRST_PAGE = _num("GLYPH_READ_FIRST_PAGE", 0) > 0  # 1: answer marks already on a new sheet (one request per sheet)
# Ink that got no response stays "new" this long, so a symbol that was read
# while half-drawn is still shown whole on the next look.
RECENT_SECONDS = _num("GLYPH_RECENT_SECONDS", 15.0)
# No new writing for this long with a sheet in view: one "keep going" card (no model call). 0 = off.
STUCK_SECONDS = _num("GLYPH_STUCK_SECONDS", 90.0)

# --- Ink detection -----------------------------------------------------------
INK_BLOCK = 31  # neighbourhood size for the adaptive threshold (odd number)
INK_C = int(_num("GLYPH_INK_C", 14))  # higher = only darker ink counts

# --- Highlighter colors (OpenCV HSV: H 0-179, S 0-255, V 0-255) --------------
# Tune these under your real lighting; the page view draws a box around
# every highlight it accepts.
HIGHLIGHT_HSV = {
    "yellow": [((20, 70, 140), (35, 255, 255))],
    "green": [((36, 60, 120), (85, 255, 255))],
    "blue": [((88, 60, 150), (112, 255, 255))],
    "pink": [((140, 50, 150), (175, 255, 255))],
}


def _hsv_override(color: str, default):
    """GLYPH_HSV_YELLOW=hmin,smin,vmin,hmax,smax,vmax replaces a color's range (the tuner writes these)."""
    raw = os.getenv("GLYPH_HSV_" + color.upper(), "")
    try:
        v = [int(float(x)) for x in raw.split(",")]
        if len(v) == 6:
            return [((v[0], v[1], v[2]), (v[3], v[4], v[5]))]
    except ValueError:
        pass
    return default


HIGHLIGHT_HSV = {c: _hsv_override(c, r) for c, r in HIGHLIGHT_HSV.items()}
# A highlight must cover at least this share of the page.
HIGHLIGHT_MIN_FRAC = 0.0009

# --- Vision model ------------------------------------------------------------
# Fastest first. On the real camera (Nov 17) gemini-3.5-flash-lite answered full pages in 1 to 6 s
# when the two "-latest" names ran past the timeout.
LLM_MODEL = os.getenv("GLYPH_MODEL", "gemini-3.5-flash-lite")
# Tried in order when the main model fails. The 2.5 models are closed to new keys (Nov 2026), so
# they are not listed. A model the key cannot use (404) is dropped for the rest of the session; one
# that is over its usage limit (429) is left alone for a while; one that times out is tried last.
LLM_FALLBACKS = ["gemini-flash-lite-latest", "gemini-3.8-flash", "gemini-flash-latest"]
# Give up on one model call after this long and move to the next model.
# Gemini rejects any deadline under 10 s ("Minimum allowed deadline is 10s"), so never go lower.
LLM_TIMEOUT_SECONDS = max(10.0, _num("GLYPH_TIMEOUT_SECONDS", 10))

DEFAULT_LEGEND = {
    "symbols": [
        {
            "name": "spark",
            "looks_like": "a starburst or asterisk: several straight rays crossing at one point",
            "action": "hint",
        },
        {
            "name": "circled question mark",
            "looks_like": "a question mark with a circle drawn around it",
            "action": "explain",
        },
        {
            "name": "check mark",
            "looks_like": "a tick: a short stroke down, then a longer stroke up to the right",
            "action": "answer",
        },
        {
            "name": "target",
            "looks_like": "a bullseye: a small circle inside a bigger circle, nothing written in it",
            "action": "practice",
        },
    ],
    # Marks made on the words themselves: what each one does.
    "marks": {"underline": "define", "box": "find", "circle": "synonym", "margin line": "summarize"},
    # Each mode uses some of the symbols and marks above. Highlights work in every mode.
    "modes": {
        "student": {
            "label": "STEM",
            "about": "Solving problems",
            "use": ["spark", "check mark", "box", "target", "underline", "circled question mark"],
            # In this mode a box is drawn round an answer, and asks for it to be checked.
            "marks": {"box": "check"},
        },
        "editor": {
            "label": "Humanities",
            "about": "Reading and writing",
            "use": ["underline", "box", "circle", "margin line", "circled question mark"],
        },
    },
    "highlight_colors": {
        "yellow": "Key ideas",
        "green": "Important notes",
        "pink": "Formulas",
        "blue": "Examples",
    },
}

ACTIONS = ("hint", "explain", "define", "answer", "check", "practice", "find", "synonym", "summarize")
VERDICTS = ("right", "wrong", "unsure")  # what a check says about the student's answer

# What each mark on words looks like, as the vision model is told.
MARKS = {
    "underline": "a pen line drawn under a word or short phrase. Fraction bars, equals signs, answer boxes and printed rules are not underlines.",
    "box": "a hand-drawn rectangle around a word, a short phrase or an answer the student wrote. Printed boxes, table cells and printed answer boxes are not marks.",
    "circle": "a hand-drawn circle or oval around a printed word or short phrase. A circle drawn around the student's own question mark is the circled question mark, not this.",
    "margin line": "a long hand-drawn line running down the margin beside several lines of text. A printed rule or the edge of the sheet is not one.",
}

# The mode Glyph starts in. GLYPH_MODE in .env changes it; the button on the web page switches it.
START_MODE = (os.getenv("GLYPH_MODE") or "student").strip().lower()


def mode_id(legend: dict, name: str) -> str:
    """The id of a mode given its id or its label ("stem" and "student" are the same mode). "" if none."""
    name = str(name or "").strip().lower()
    for key, m in (legend.get("modes") or {}).items():
        if name in (key.lower(), str(m.get("label", "")).lower()):
            return key
    return ""


# How the page view was last turned with the Rotate button, kept between runs: the camera and the
# desk stay where they are, so a restart should not put the page on its side again.
VIEW_FILE = ROOT / "sessions" / "view.json"


def saved_rotation() -> int:
    """Degrees (0, 90, 180, 270) the page view was turned by when Rotate was last clicked."""
    try:
        turn = int(json.loads(VIEW_FILE.read_text(encoding="utf-8")).get("rotate", 0))
    except (OSError, ValueError, AttributeError, TypeError):
        return 0
    return turn if turn in (0, 90, 180, 270) else 0


def save_rotation(degrees: int) -> None:
    try:
        VIEW_FILE.parent.mkdir(parents=True, exist_ok=True)
        VIEW_FILE.write_text(json.dumps({"rotate": int(degrees) % 360}), encoding="utf-8")
    except OSError:
        pass


def load_legend() -> dict:
    """symbols.json maps each symbol, mark and highlight color to what it does, and says which
    of them each mode uses."""
    path = ROOT / "symbols.json"
    legend = json.loads(json.dumps(DEFAULT_LEGEND))
    if path.exists():
        try:
            user = json.loads(path.read_text(encoding="utf-8"))
            for key in ("symbols", "marks", "modes", "highlight_colors"):
                if key in user:
                    legend[key] = user[key]
        except (OSError, ValueError) as e:
            print(f"[glyph] could not read symbols.json ({e}); using the defaults")
    legend["symbols"] = [s for s in legend["symbols"] if s.get("action") in ACTIONS]
    legend["marks"] = {k: v for k, v in legend.get("marks", {}).items() if k in MARKS and v in ACTIONS}
    return legend


def modes_of(legend: dict) -> list:
    """The modes a legend has, in order: [{"id", "label", "about"}]. None: one mode with everything."""
    return [
        {"id": key, "label": str(m.get("label") or key.title()), "about": str(m.get("about") or "")}
        for key, m in (legend.get("modes") or {}).items()
        if isinstance(m, dict)
    ]


def legend_for(legend: dict, mode: str = "") -> dict:
    """The legend as one mode uses it: only that mode's symbols and marks.

    A legend without modes, or a mode it does not have, gives everything (which is how Glyph
    worked before there were modes).
    """
    spec = (legend.get("modes") or {}).get(mode)
    out = dict(legend, mode=mode if spec else "")
    if isinstance(spec, dict):
        use = list(spec.get("use") or [])
        out["symbols"] = [s for s in legend.get("symbols", []) if s.get("name") in use]
        out["marks"] = {k: v for k, v in legend.get("marks", {}).items() if k in use}
        # A mode may give a mark a job of its own (a box checks an answer where problems are solved).
        out["marks"].update({k: v for k, v in (spec.get("marks") or {}).items() if k in use and k in MARKS and v in ACTIONS})
    else:
        use = [s.get("name") for s in legend.get("symbols", [])] + list(legend.get("marks", {}))
    # The actions in the order the mode lists its marks: the order they are shown in on the web page.
    action = {s.get("name"): s.get("action") for s in out.get("symbols", [])}
    action.update(out.get("marks", {}))
    out["order"] = [action[name] for name in use if name in action]
    return out


def actions_of(legend: dict) -> list:
    """Every action a legend can ask for, in the fixed order of ACTIONS."""
    have = {s["action"] for s in legend.get("symbols", [])} | set(legend.get("marks", {}).values())
    return [a for a in ACTIONS if a in have]
