"""Time the vision model on Glyph's own test pages.

    python bench.py              3 runs of each case on every model
    python bench.py --runs 5
    python bench.py --mock       no key needed: checks that the script itself works

For each model it sends the same pictures the app would send (a spark, an
underline, a whole-page look, a study guide) and reports how long each answer
took and whether the answer was the right kind. Results are printed and saved
to bench_results.md.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
import time
import warnings

warnings.filterwarnings("ignore")

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from glyph import config, demo  # noqa: E402
from glyph.brain import Brain, BrainError, MockBrain  # noqa: E402
from glyph.highlights import detect_highlights  # noqa: E402
from glyph.page import find_page_quad, ink_mask, make_focus_crop, mask_bbox, remove_small, warp_page  # noqa: E402

K9 = np.ones((9, 9), np.uint8)


def jpg(img, q=85) -> bytes:
    return cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), q])[1].tobytes()


def build_cases():
    """The same page + close-up pairs the engine would send for each demo step."""
    steps = demo.build_steps()
    quad, _ = find_page_quad(steps["blank"])
    pages = {k: warp_page(v, quad) for k, v in steps.items()}

    def new_ink(before, after):
        fresh = cv2.bitwise_and(ink_mask(after), cv2.bitwise_not(cv2.dilate(ink_mask(before), K9)))
        fresh = remove_small(fresh, 8)
        crop, _ = make_focus_crop(after, fresh)
        box = mask_bbox(fresh)
        return jpg(after), jpg(crop, 90), (box[2] - box[0], box[3] - box[1])

    cases = []
    page, crop, shape = new_ink(pages["blank"], pages["spark"])
    cases.append(("spark -> hint", page, crop, shape, "hint"))
    page, crop, shape = new_ink(pages["spark"], pages["underline"])
    cases.append(("underline -> definition", page, crop, shape, "define"))
    cases.append(("whole page look", jpg(pages["underline"]), None, None, "any"))

    regions, _ = detect_highlights(pages["highlights"])
    labels = config.load_legend()["highlight_colors"]
    items = []
    for r in regions:
        x, y, w, h = r["bbox"]
        items.append({"color": r["color"], "label": labels.get(r["color"], r["color"]), "jpg": jpg(pages["highlights"][y - 8 : y + h + 8, x - 10 : x + w + 10])})
    return cases, items


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--models", help="comma-separated list (default: the main model and its fallbacks)")
    args = ap.parse_args()

    legend = config.load_legend()
    cases, guide_items = build_cases()
    models = args.models.split(",") if args.models else [config.LLM_MODEL] + [m for m in config.LLM_FALLBACKS if m != config.LLM_MODEL]
    # Each model is tried as-is and with thinking turned off (often much faster).
    setups = [(m, b) for m in models for b in ("", "0")]
    if args.mock:
        setups = [("mock", "")]

    rows, failures = [], []
    for model, budget in setups:
        label = model + (" (thinking off)" if budget == "0" else "")
        if budget:
            os.environ["GLYPH_THINKING_BUDGET"] = budget
        else:
            os.environ.pop("GLYPH_THINKING_BUDGET", None)
        try:
            brain = MockBrain(legend) if args.mock else Brain(legend, models=[model])
        except BrainError as e:
            print(f"[bench] {e}")
            return 1
        print(f"\n{label}")
        for name, page, crop, shape, want in cases:
            times, right, err = [], 0, ""
            for _ in range(args.runs):
                t0 = time.time()
                try:
                    out = brain.analyze(page, crop, shape_hint=shape)
                    times.append(time.time() - t0)
                    actions = [t["action"] for t in out["triggers"]]
                    right += int(want == "any" or want in actions)
                except Exception as e:  # noqa: BLE001
                    err = str(e)[:80]
                time.sleep(0.5)
            rows.append((label, name, times, right, args.runs, err))
            _show(rows[-1])
            if err:
                failures.append(f"{label} / {name}: {err}")
        if guide_items:
            times, err = [], ""
            for _ in range(max(1, args.runs // 2)):
                t0 = time.time()
                try:
                    brain.study_guide(guide_items)
                    times.append(time.time() - t0)
                except Exception as e:  # noqa: BLE001
                    err = str(e)[:80]
            rows.append((label, "study guide (2 highlights)", times, len(times), max(1, args.runs // 2), err))
            _show(rows[-1])

    out = ["# Glyph model timing", "", time.strftime("%Y-%m-%d %H:%M"), "",
           "| Model | Case | Median s | Slowest s | Right kind of answer |", "|---|---|---|---|---|"]
    for label, name, times, right, runs, err in rows:
        med = f"{statistics.median(times):.1f}" if times else "failed"
        worst = f"{max(times):.1f}" if times else "-"
        out.append(f"| {label} | {name} | {med} | {worst} | {right}/{runs} |")
    if failures:
        out += ["", "Errors:"] + [f"- {f}" for f in failures]
    out += ["", "The app adds about 1 second before the model call (waiting for the picture to hold still).",
            "To use a faster setup, set GLYPH_MODEL and/or GLYPH_THINKING_BUDGET=0 in .env."]
    path = config.ROOT / "bench_results.md"
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\nSaved {path.name}")
    return 0


def _show(row) -> None:
    label, name, times, right, runs, err = row
    if times:
        print(f"  {name:<28} median {statistics.median(times):5.1f}s   slowest {max(times):5.1f}s   right {right}/{runs}")
    else:
        print(f"  {name:<28} failed: {err}")


if __name__ == "__main__":
    sys.exit(main())
