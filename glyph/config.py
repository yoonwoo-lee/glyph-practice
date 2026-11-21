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
            "action": "check",
        },
    ],
    "marks": {"underline": "define"},
    "highlight_colors": {
        "yellow": "Key ideas",
        "green": "Definitions",
        "pink": "Formulas",
        "blue": "Examples",
    },
}

ACTIONS = ("hint", "explain", "define", "check")
VERDICTS = ("right", "wrong", "unsure")  # what a check says about the student's answer


def load_legend() -> dict:
    """symbols.json maps each symbol and highlight color to what it does."""
    path = ROOT / "symbols.json"
    legend = json.loads(json.dumps(DEFAULT_LEGEND))
    if path.exists():
        try:
            user = json.loads(path.read_text(encoding="utf-8"))
            for key in ("symbols", "marks", "highlight_colors"):
                if key in user:
                    legend[key] = user[key]
        except (OSError, ValueError) as e:
            print(f"[glyph] could not read symbols.json ({e}); using the defaults")
    legend["symbols"] = [s for s in legend["symbols"] if s.get("action") in ACTIONS]
    return legend
