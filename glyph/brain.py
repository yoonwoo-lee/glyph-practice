"""The tutor: reads the page with a vision model and decides what to say.

All model calls go through Brain._generate, so switching provider (Claude,
Bedrock, ...) means rewriting that one method.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import List, Optional

from . import config


class BrainError(Exception):
    pass


def build_system_prompt(legend: dict) -> str:
    symbols = "\n".join(
        f'- "{s["name"]}": {s.get("looks_like", s["name"])} -> action "{s["action"]}"'
        for s in legend.get("symbols", [])
    )
    marks = legend.get("marks", {})
    underline = marks.get("underline")
    mark_lines = ""
    if underline in config.ACTIONS:
        mark_lines = (
            f'- "underline": a pen line drawn under a word or short phrase -> action "{underline}". '
            "Fraction bars, equals signs, answer boxes and printed rules are not underlines."
        )
    return f"""You are Glyph, a study tutor that watches a student's sheet of paper through a camera above the desk.
The student never types. They ask for help by drawing small marks on the paper.

SYMBOLS (hand-drawn, so they may be rough):
{symbols or "(none)"}

MARKS:
{mark_lines or "(none)"}

WHAT YOU SEE
Image 1 is the whole page, for context.
If there is an image 2, it is a close-up of the part of the page that just changed. In it, only the
newly drawn ink is at full contrast; everything older is faded. Report only symbols and marks that are
part of that new, full-contrast ink. Faded content was handled earlier and must not be reported.
If there is no image 2, report every symbol or mark you can see on the page.

WHAT IS NOT A TRIGGER
Ordinary handwriting, math working, doodles, crossed-out text and printed text. Most looks at the page
contain no trigger at all. Only report a symbol that clearly matches the legend and looks finished.
If a hand, arm or pen covers the area so you cannot read it, set "occluded" to true.

HOW TO RESPOND
- hint: find the problem the symbol sits next to and read the student's own working. Give ONE hint that
  helps them take the next step themselves. Never state the final answer and never do the working for
  them. If their working contains a mistake, say which line to re-check, not what the fix is. If you
  already gave a hint for this problem (see "Earlier responses"), make this one a little more specific.
  At most 50 words.
- explain: explain the idea or passage next to the mark in plain language. At most 70 words.
- define: give the meaning of the underlined word or phrase as it is used on this page. At most 35 words.
Write to the student directly. Plain sentences, no markdown, no LaTeX.

Reply with JSON only, in this shape:
{{"occluded": false, "triggers": [{{"kind": "symbol" or "underline", "symbol": "<legend name or null>",
"action": "hint" or "explain" or "define", "target": "<short quote of the problem, passage or word the mark refers to>",
"response": "<what you say to the student>"}}]}}
Use an empty "triggers" list when there is nothing to respond to."""


GUIDE_PROMPT = """These are photos of passages a student highlighted while studying. Each photo is labelled with
the highlighter color and what the student uses that color for.

Write a study guide in Markdown:
- One "## <category>" heading per category, in the order given below.
- Under it, one bullet per highlight with the highlighted text only (ignore words outside the color).
  Keep the source's wording, fix obvious reading errors, and merge duplicates.
- If a highlight cannot be read, write "(unreadable highlight)".
Do not add facts that are not in the highlights. Do not add a title or a closing remark."""


def _parse_json(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text).strip()
    try:
        return json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def clean_result(data, legend: dict) -> dict:
    """Keep only well-formed triggers that use actions from the legend."""
    out = {"occluded": False, "triggers": []}
    if not isinstance(data, dict):
        return out
    out["occluded"] = bool(data.get("occluded"))
    allowed = {s["action"] for s in legend.get("symbols", [])}
    underline_action = legend.get("marks", {}).get("underline")
    for t in data.get("triggers") or []:
        if not isinstance(t, dict):
            continue
        action = str(t.get("action") or "").strip().lower()
        response = str(t.get("response") or "").strip()
        kind = "underline" if str(t.get("kind") or "").lower() == "underline" else "symbol"
        ok = action == underline_action if kind == "underline" else action in allowed
        if not ok or action not in config.ACTIONS or not response:
            continue
        out["triggers"].append(
            {
                "kind": kind,
                "symbol": t.get("symbol") or None,
                "action": action,
                "target": str(t.get("target") or "").strip()[:300],
                "response": response[:900],
            }
        )
    return out


class Brain:
    """Gemini, through the google-genai SDK."""

    name = "gemini"

    def __init__(self, legend: dict, models: Optional[List[str]] = None) -> None:
        key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not key:
            raise BrainError("GEMINI_API_KEY is not set in .env")
        from google import genai
        from google.genai import types

        self._client = genai.Client(api_key=key)
        self._types = types
        self.legend = legend
        self.system = build_system_prompt(legend)
        self.models = models or [config.LLM_MODEL] + [m for m in config.LLM_FALLBACKS if m != config.LLM_MODEL]
        self.last_model = ""  # which model actually answered the last call

    def _generate(self, images: List[bytes], text: str, system: Optional[str], want_json: bool) -> str:
        types = self._types
        parts = [types.Part.from_bytes(data=img, mime_type="image/jpeg") for img in images]
        parts.append(types.Part.from_text(text=text))
        options = dict(
            system_instruction=system,
            response_mime_type="application/json" if want_json else "text/plain",
            max_output_tokens=4096,
            temperature=0.3,
        )
        # Optional: cap the model's thinking for faster answers (GLYPH_THINKING_BUDGET=0 turns it off
        # on models that allow that). Left alone unless you set it.
        budget = os.getenv("GLYPH_THINKING_BUDGET", "").strip()
        if budget.lstrip("-").isdigit():
            options["thinking_config"] = types.ThinkingConfig(thinking_budget=int(budget))
        cfg = types.GenerateContentConfig(**options)
        last = None
        for attempt in range(2):
            for model in self.models:
                try:
                    r = self._client.models.generate_content(model=model, contents=parts, config=cfg)
                    if r.text:
                        self.last_model = model
                        return r.text
                    last = BrainError(f"{model} returned no text")
                except Exception as e:  # overloaded, rate-limited, unknown model, ...
                    last = e
                    print(f"[glyph] {model} failed: {str(e)[:90]}")
            time.sleep(1.5)
        raise BrainError(f"The vision model did not answer: {str(last)[:160]}")

    def analyze(self, page_jpg: bytes, crop_jpg: Optional[bytes] = None, context: str = "", shape_hint=None) -> dict:
        images = [page_jpg] + ([crop_jpg] if crop_jpg else [])
        text = "Image 1: the whole page."
        if crop_jpg:
            text += " Image 2: close-up of the newly drawn ink."
        if context:
            text += "\n\n" + context
        raw = self._generate(images, text, self.system, want_json=True)
        try:
            return clean_result(_parse_json(raw), self.legend)
        except ValueError:
            raise BrainError(f"The vision model sent something that is not JSON: {raw[:120]}")

    def study_guide(self, items: List[dict]) -> str:
        """items: [{"color", "label", "jpg"}] -> Markdown sections."""
        order = []
        for it in items:
            if it["label"] not in order:
                order.append(it["label"])
        lines = ["Categories, in order: " + ", ".join(order), ""]
        for i, it in enumerate(items, 1):
            lines.append(f"Photo {i}: {it['color']} highlighter = {it['label']}")
        text = GUIDE_PROMPT + "\n\n" + "\n".join(lines)
        return self._generate([it["jpg"] for it in items], text, None, want_json=False).strip()


class MockBrain:
    """Canned answers, for running the app with no key and no internet."""

    name = "mock"

    def __init__(self, legend: dict) -> None:
        self.legend = legend
        self.calls = 0

    def analyze(self, page_jpg: bytes, crop_jpg: Optional[bytes] = None, context: str = "", shape_hint=None) -> dict:
        self.calls += 1
        time.sleep(0.4)
        if crop_jpg is None or not shape_hint:
            return {"occluded": False, "triggers": []}
        w, h = shape_hint
        if w >= 5 * h and h <= 30:
            data = {
                "triggers": [
                    {
                        "kind": "underline",
                        "action": "define",
                        "target": f"underlined word #{self.calls}",
                        "response": "(fake answer) This is where the definition of the underlined word appears.",
                    }
                ]
            }
        elif 0.5 <= w / float(max(h, 1)) <= 2.0 and max(w, h) <= 160:
            data = {
                "triggers": [
                    {
                        "kind": "symbol",
                        "symbol": "spark",
                        "action": "hint",
                        "target": f"problem next to symbol #{self.calls}",
                        "response": "(fake answer) This is where a hint for the nearby problem appears.",
                    }
                ]
            }
        else:
            data = {"triggers": []}
        return clean_result(data, self.legend)

    def study_guide(self, items: List[dict]) -> str:
        out, seen = [], []
        for it in items:
            if it["label"] not in seen:
                seen.append(it["label"])
        for label in seen:
            out.append(f"## {label}")
            n = sum(1 for it in items if it["label"] == label)
            out.extend(f"- (fake answer) text of {label.lower()} highlight {i}" for i in range(1, n + 1))
            out.append("")
        return "\n".join(out).strip()
