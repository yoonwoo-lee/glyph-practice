"""Live tuning: see what Glyph sees, move the thresholds, save them to .env.

Used by the /tune page. Changes apply to the running app at once; "Save"
writes them to .env so they are still there next time.
"""

from __future__ import annotations

import re
from typing import Dict, Optional

import cv2
import numpy as np

from . import config
from .highlights import DRAW_COLORS, detect_highlights
from .page import cover_mask, ink_mask, normalize_light, page_gray, page_saturation

# name -> (lowest, highest, step, what it does)
SLIDERS = {
    "ink_c": (4, 40, 1, "Lower picks up fainter pen and pencil; higher ignores shadows and paper grain."),
    "min_new_px": (30, 600, 10, "Raise it if specks trigger looks."),
    "settle": (0.3, 3.0, 0.1, "Lower feels faster; higher avoids reading a half-drawn mark."),
    "cover_diff": (10, 80, 1, "Lower spots hands and shadows sooner; raise it if the page is flagged as covered when it is clear."),
}


def values(engine) -> dict:
    out = {
        "ink_c": config.INK_C,
        "min_new_px": engine.settings.min_new_px,
        "settle": engine.settings.settle,
        "cover_diff": config.COVER_DIFF,
        "colors": {},
    }
    for color, ranges in config.HIGHLIGHT_HSV.items():
        (h0, s0, v0), (h1, _, _) = ranges[0]
        out["colors"][color] = {"hmin": h0, "hmax": h1, "smin": s0, "vmin": v0}
    return out


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def apply(engine, new: dict) -> dict:
    """Use these values in the running app. Unknown keys are ignored."""
    changed_ink = False
    if "ink_c" in new:
        c = int(_clamp(float(new["ink_c"]), 4, 40))
        changed_ink = c != config.INK_C
        config.INK_C = c
    if "min_new_px" in new:
        engine.settings.min_new_px = int(_clamp(float(new["min_new_px"]), 30, 600))
    if "settle" in new:
        engine.settings.settle = float(_clamp(float(new["settle"]), 0.3, 3.0))
    if "cover_diff" in new:
        config.COVER_DIFF = int(_clamp(float(new["cover_diff"]), 10, 80))
    for color, r in (new.get("colors") or {}).items():
        if color not in config.HIGHLIGHT_HSV:
            continue
        h0 = int(_clamp(float(r.get("hmin", 0)), 0, 179))
        h1 = int(_clamp(float(r.get("hmax", 179)), h0, 179))
        s0 = int(_clamp(float(r.get("smin", 60)), 0, 255))
        v0 = int(_clamp(float(r.get("vmin", 120)), 0, 255))
        config.HIGHLIGHT_HSV[color] = [((h0, s0, v0), (h1, 255, 255))]
    if changed_ink:
        engine.request_reset()  # the remembered ink no longer matches what is seen
    return values(engine)


def probe(page: np.ndarray, fx: float, fy: float) -> dict:
    """Color of the page at a clicked spot (fx, fy are 0-1 across and down)."""
    h, w = page.shape[:2]
    x, y = int(_clamp(fx, 0, 1) * (w - 1)), int(_clamp(fy, 0, 1) * (h - 1))
    raw = page[max(0, y - 6) : y + 7, max(0, x - 6) : x + 7]
    patch = normalize_light(page)[max(0, y - 6) : y + 7, max(0, x - 6) : x + 7]  # same view the detector uses
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV).reshape(-1, 3)
    hh, ss, vv = (int(np.median(hsv[:, i])) for i in range(3))
    b, g, r = (int(np.median(raw.reshape(-1, 3)[:, i])) for i in range(3))
    return {"h": hh, "s": ss, "v": vv, "rgb": "#{:02x}{:02x}{:02x}".format(r, g, b)}


def fit(color: str, hsv: dict) -> Optional[dict]:
    """A range for `color` centred on a clicked highlighter stroke."""
    if color not in config.HIGHLIGHT_HSV:
        return None
    h, s, v = int(hsv["h"]), int(hsv["s"]), int(hsv["v"])
    return {
        "hmin": _clamp(h - 9, 0, 179),
        "hmax": _clamp(h + 9, 0, 179),
        "smin": int(_clamp(s * 0.5, 30, 200)),
        "vmin": int(_clamp(v - 80, 60, 230)),
    }


def render(engine, which: str) -> bytes:
    """A picture of the page with one kind of detection painted on it."""
    page = engine.last_page()
    if page is None:
        blank = np.full((300, 400, 3), 40, np.uint8)
        return cv2.imencode(".jpg", blank)[1].tobytes()
    dim = cv2.addWeighted(page, 0.45, np.full_like(page, 255), 0.55, 0)
    out = dim
    if which == "ink":
        m = ink_mask(page)
        out = dim.copy()
        out[m > 0] = (150, 40, 30)
    elif which == "highlights":
        regions, _ = detect_highlights(page)
        hsv = cv2.cvtColor(normalize_light(page), cv2.COLOR_BGR2HSV)
        out = dim.copy()
        for color, ranges in config.HIGHLIGHT_HSV.items():
            lo, hi = ranges[0]
            m = cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8))
            out[m > 0] = DRAW_COLORS.get(color, (120, 120, 120))
        for r in regions:
            x, y, w, h = r["bbox"]
            cv2.rectangle(out, (x - 4, y - 4), (x + w + 4, y + h + 4), (40, 40, 40), 2)
    elif which == "cover":
        out = dim.copy()
        base = engine.base_gray
        if base is not None and base.shape[:2] == page.shape[:2]:
            _, hl = detect_highlights(page)
            m = cover_mask(page_gray(page), base, hl, page_saturation(page), engine.base_sat)
            m = cv2.dilate(m, np.ones((31, 31), np.uint8))
            out[m > 0] = (70, 70, 220)
    else:
        out = page
    return cv2.imencode(".jpg", out, [int(cv2.IMWRITE_JPEG_QUALITY), 78])[1].tobytes()


def env_lines(v: dict) -> Dict[str, str]:
    lines = {
        "GLYPH_INK_C": str(int(v["ink_c"])),
        "GLYPH_MIN_NEW_INK_PX": str(int(v["min_new_px"])),
        "GLYPH_SETTLE_SECONDS": "{:.1f}".format(float(v["settle"])),
        "GLYPH_COVER_DIFF": str(int(v["cover_diff"])),
    }
    for color, r in v["colors"].items():
        lines["GLYPH_HSV_" + color.upper()] = "{},{},{},{},255,255".format(int(r["hmin"]), int(r["smin"]), int(r["vmin"]), int(r["hmax"]))
    return lines


def save_env(engine) -> int:
    """Write the current values into .env, leaving every other line (the key!) untouched."""
    path = config.ROOT / ".env"
    new = env_lines(values(engine))
    old = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    out, done = [], set()
    for line in old:
        m = re.match(r"\s*#?\s*([A-Z0-9_]+)\s*=", line)
        key = m.group(1) if m else None
        if key in new and not line.lstrip().startswith("#"):
            out.append("{}={}".format(key, new[key]))
            done.add(key)
        else:
            out.append(line)
    missing = [k for k in new if k not in done]
    if missing:
        if out and out[-1].strip():
            out.append("")
        out.append("# Saved from the tuning page")
        out += ["{}={}".format(k, new[k]) for k in missing]
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return len(new)
