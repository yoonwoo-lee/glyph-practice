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


# How to answer each action, as the vision model is told. Only the actions a mode uses are sent.
HOW = {
    "hint": """- hint: find the problem the symbol sits next to and read the student's own working. Give ONE hint that
  helps them take the next step themselves. Never state the final answer and never do the working for
  them. If their working contains a mistake, say which line to re-check, not what the fix is. If you
  already gave a hint for this problem (see "Earlier responses"), make this one a little more specific.
  At most 50 words.""",
    "explain": "- explain: explain the idea or passage next to the mark in plain language. At most 70 words.",
    "define": "- define: give the meaning of the underlined word or phrase as it is used on this page. At most 35 words.",
    "answer": """- answer: the student is asking for the answer to the problem the check mark sits next to. Give the worked
  solution in three to five short steps, each on its own line, ending with the final answer. At most
  90 words.""",
    "check": """- check: the student wants the answer they marked (inside the box) checked. Find that answer, the working above
  it and the problem it belongs to. First solve the problem yourself in "work" (a few short steps, at
  most 60 words; the student never sees it). Then set "verdict":
  "right" when their final answer agrees with yours (rounding and equivalent forms count). Say so, and
  name the step they got right.
  "wrong" when it does not agree, or a line of their working does not follow. Say it is not right yet
  and which line or step to look at again. Never state the correct answer or the corrected line.
  "unsure" when there is no answer next to the mark, you cannot read it, or you cannot solve the
  problem with confidence. Say what you need, for example the final answer written clearly inside the box.
  Never say "right" without having worked it out. At most 40 words.""",
    "practice": """- practice: write ONE new problem of the same kind as the problem the target sits next to: the same idea
  and difficulty, with different numbers or a different setting. Do not solve it and give no hint.
  At most 60 words.""",
    "find": """- find: the target is the word or phrase inside the box. Look through image 1 for every OTHER place the
  same word appears (other endings and capital letters count). List them in "places", in reading order,
  at most 20: each is {"box_2d": [ymin, xmin, ymax, xmax], "text": "<the three or four words around it>"},
  with the box drawn tightly round that one word in numbers from 0 to 1000 measured on image 1 (0, 0 is
  the top left corner). Use an empty list when it appears nowhere else. "response" is one short
  sentence saying how many more times the word appears.""",
    "synonym": """- synonym: give three to five words that could replace the circled word in its sentence, best fit first,
  separated by commas. The response is that list of words and nothing else: no sentence, no explanation.""",
    "summarize": """- summarize: the passage is every line of text the margin line runs beside; read all of it from image 1.
  Say what it says in two or three plain sentences, using only what is in the passage. At most 60
  words. The target is the first four or five words of the passage.""",
}

# How to read the target of each mark on words off the pink strokes.
PINK_TARGET = {
    "underline": "- For a pink underline, the target is exactly the word or words sitting directly above the pink line, read\n"
    "  from the close-up, and nothing else. A pink line under two rows of text means both rows' underlined words.",
    "box": "- For a pink box, the target is exactly the word or words inside the box, read from the close-up.",
    "circle": "- For a pink circle around a word, the target is exactly the word or words inside it, read from the close-up.",
    "margin line": "- For a pink line down the margin, the passage is the lines of text level with the pink line, from its top\n"
    "  end to its bottom end.",
}


def build_system_prompt(legend: dict) -> str:
    """The standing instructions for one legend. Pass config.legend_for(legend, mode) for one mode."""
    symbols = "\n".join(
        f'- "{s["name"]}": {s.get("looks_like", s["name"])} -> action "{s["action"]}"'
        for s in legend.get("symbols", [])
    )
    marks = {k: v for k, v in legend.get("marks", {}).items() if k in config.MARKS and v in config.ACTIONS}
    mark_lines = "\n".join(f'- "{k}": {config.MARKS[k]} -> action "{v}"' for k, v in marks.items())
    actions = config.actions_of(dict(legend, marks=marks))
    checks = "check" in actions
    # A sheet seen for the first time: symbols are answered. Marks on words were drawn some other
    # day (Yoon Woo, Nov 20), unless the student asks.
    asking = {"check": "checked", "answer": "answered"}  # marks a marked sheet may be covered in
    counted = [k for k, v in list(marks.items()) + [(s["name"], s["action"]) for s in legend.get("symbols", [])] if v in asking]
    first = [s["name"] for s in legend.get("symbols", []) if s["action"] not in asking]
    left = [k for k, v in marks.items() if v not in asking]
    first_look = "Report only these hand-drawn symbols, where you can see them clearly: {}.".format(
        ", ".join(first) if first else "(none)"
    )
    if counted:
        # Nov 21: a check drawn in the first seconds, before the sheet had been taken in, got no
        # answer. A sheet covered in ticks is another matter: those are a teacher's.
        first_look += (
            "\nOn a first look, also report these when there are three or fewer of a kind on the sheet (the student has\n"
            "just drawn them): {}. More than three of a kind means the sheet was marked before: report none of that kind."
        ).format(", ".join(counted))
    if left:
        first_look += (
            "\nLeave these alone on a first look, because they were drawn before: {}. The one exception is when the note\n"
            "with the images says the student asked for the whole page to be read: then report every mark."
        ).format(", ".join(left))
    pink = "".join("\n" + PINK_TARGET[k] for k in marks)
    if checks:
        pink += (
            "\n- A pink box often comes with pink writing inside it: the answer the student wrote just before drawing\n"
            "  it. The box is the trigger and that writing is what to check."
        )
    how = "\n".join(HOW[a] for a in actions)
    extra_keys = ""
    if checks:
        extra_keys += '\n"work": "<check only: your own solution, in brief>", "verdict": "<check only: right, wrong or unsure>",'
    if "find" in actions:
        extra_keys += '\n"places": [<find only: one entry for each other place the word appears>],'
    kinds = " or ".join('"{}"'.format(k) for k in ["symbol"] + list(marks))
    action_list = " or ".join('"{}"'.format(a) for a in actions) or '"hint"'
    return f"""You are {config.APP_NAME}, a study tutor that watches a student's sheet of paper through a camera above the desk.
The student never types. They ask for help by drawing small marks on the paper.

SYMBOLS (hand-drawn, so they may be rough):
{symbols or "(none)"}

MARKS (drawn on the words themselves):
{mark_lines or "(none)"}

WHAT YOU SEE
Image 1 is the whole page, for context only.
If there is an image 2, it is a close-up of the place where the student has just drawn something. The
strokes they just drew are colored BRIGHT PINK. Everything black, gray or blue was on the page before and
has already been dealt with.
- Respond only when the pink strokes themselves form one of the symbols or marks above.
- Never respond to a symbol or mark that is not pink, even if it is clear and sits right next to the pink.
- Pink strokes that are ordinary writing, working, a stray line, a dot, a smudge, a shadow, or part of a
  hand or pen are not a trigger. Most close-ups contain no trigger: return an empty list for those.{pink}
If there is no image 2, the sheet is being seen for the first time. {first_look}
Printed text, printed rules and ordinary handwriting are not marks. A page of print with nothing drawn
on it has no triggers. When unsure, report nothing.

WHAT IS NOT A TRIGGER
Ordinary handwriting, math working, doodles, crossed-out text and printed text. Only report a symbol that
clearly matches the legend and looks finished.
If a hand, arm or pen covers the area so you cannot read it, set "occluded" to true.

HOW TO RESPOND
{how}
Write to the student directly. Plain sentences, no markdown, no LaTeX.

Reply with JSON only, in this shape:
{{"occluded": false, "triggers": [{{"kind": {kinds}, "symbol": "<legend name or null>",
"action": {action_list}, "target": "<short quote of the problem, passage or word the mark refers to>",{extra_keys}
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


# What a model may write for a verdict. Anything else counts as "unsure".
_VERDICT_WORDS = {"right": "right", "correct": "right", "wrong": "wrong", "incorrect": "wrong", "not right": "wrong", "not yet": "wrong", "unsure": "unsure"}
assert set(_VERDICT_WORDS.values()) == set(config.VERDICTS)


def _unit_box(raw) -> Optional[list]:
    """A model's [ymin, xmin, ymax, xmax] (0 to 1000 on the page picture) as [x0, y0, x1, y1] from 0 to 1.

    None for anything that cannot be one word on a page: not four numbers, empty, or far too big.
    """
    try:
        y0, x0, y1, x1 = [float(v) for v in raw]
    except (TypeError, ValueError):
        return None
    scale = 1.0 if max(y0, x0, y1, x1) <= 1.0 else 1000.0  # some models answer from 0 to 1
    x0, y0, x1, y1 = [min(1.0, max(0.0, v / scale)) for v in (x0, y0, x1, y1)]
    if x1 - x0 < 0.004 or y1 - y0 < 0.003 or x1 - x0 > 0.6 or y1 - y0 > 0.15:
        return None
    return [round(x0, 4), round(y0, 4), round(x1, 4), round(y1, 4)]


def clean_result(data, legend: dict) -> dict:
    """Keep only well-formed triggers that use actions from the legend."""
    out = {"occluded": False, "triggers": []}
    if not isinstance(data, dict):
        return out
    out["occluded"] = bool(data.get("occluded"))
    allowed = {s["action"] for s in legend.get("symbols", [])}
    marks = legend.get("marks", {})
    for t in data.get("triggers") or []:
        if not isinstance(t, dict):
            continue
        action = str(t.get("action") or "").strip().lower()
        response = str(t.get("response") or "").strip()
        kind = str(t.get("kind") or "").strip().lower().replace("_", " ")
        kind = kind if kind in marks else "symbol"
        ok = action == marks[kind] if kind in marks else action in allowed
        if not ok or action not in config.ACTIONS or not (response or action == "find"):
            continue
        kept = {
            "kind": kind,
            "symbol": t.get("symbol") or None,
            "action": action,
            "target": str(t.get("target") or "").strip()[:300],
            "response": response[:900],
        }
        if action == "check":
            # No clear verdict is "unsure": a check must never read as "right" by accident.
            verdict = _VERDICT_WORDS.get(str(t.get("verdict") or "").strip().lower().rstrip("."), "unsure")
            kept["verdict"] = verdict
            kept["work"] = str(t.get("work") or "").strip()[:600]
        if action == "find":
            places = [p for p in (t.get("places") or []) if isinstance(p, dict)][:30]
            kept["count"] = len(places)
            kept["places"] = [b for b in (_unit_box(p.get("box_2d")) for p in places) if b]
        out["triggers"].append(kept)
    return out


class QuotaError(BrainError):
    """Every model is over its usage limit for now. `retry_after` is seconds until the next try."""

    def __init__(self, message: str, retry_after: float) -> None:
        super().__init__(message)
        self.retry_after = retry_after


def _kind(err: Exception) -> str:
    """Sort a failed model call into what to do about it."""
    text = (type(err).__name__ + " " + str(err)).lower()
    code = getattr(err, "code", None) or getattr(err, "status_code", None)
    if code == 429 or "resource_exhausted" in text or "quota" in text:
        return "quota"  # over the usage limit: leave this model alone for a while
    if code == 404 or "not_found" in text or "no longer available" in text or "is not found" in text:
        return "gone"  # this key can never use this model
    if code in (401, 403) or "api key not valid" in text or "api_key_invalid" in text or "permission_denied" in text:
        return "key"  # the key itself was refused
    if code == 504 or "timeout" in text or "timed out" in text or "deadline" in text:
        return "slow"
    if code == 400 or "invalid_argument" in text:
        return "refused"  # the request was not accepted as sent
    if any(w in text for w in ("connecterror", "connection", "getaddrinfo", "name or service", "nodename nor servname", "unreachable")):
        return "offline"
    return "busy"  # overloaded (500 / 503) or unknown: worth one more try


def _retry_hint(err: Exception) -> Optional[float]:
    """Gemini often says how long to wait ("Please retry in 23.5s")."""
    m = re.search(r"retry in ([0-9.]+) ?s", str(err), re.I) or re.search(r"retrydelay\W+([0-9.]+)s", str(err), re.I)
    return float(m.group(1)) if m else None


WHY = {
    "quota": "over its usage limit",
    "gone": "not available for this key",
    "slow": "too slow",
    "refused": "refused the request",
    "busy": "busy",
    "offline": "could not be reached",
    "key": "refused the key",
}


class Brain:
    """Gemini, through the google-genai SDK."""

    name = "gemini"

    def __init__(self, legend: dict, models: Optional[List[str]] = None) -> None:
        key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not key:
            raise BrainError("GEMINI_API_KEY is not set in .env")
        from google import genai
        from google.genai import types

        # v1beta is where the "-latest" model names live; newer SDK versions default to v1, which 404s
        # on them. One attempt and a timeout per call: the SDK's own retries made a slow model look
        # frozen. Falling back to the next model is handled in _generate.
        http = {"api_version": "v1beta", "timeout": int(config.LLM_TIMEOUT_SECONDS * 1000)}
        if hasattr(types, "HttpRetryOptions"):
            http["retry_options"] = types.HttpRetryOptions(attempts=1)
        try:
            self._client = genai.Client(api_key=key, http_options=http)
        except Exception:  # an SDK version that rejects one of the options above
            self._client = genai.Client(api_key=key, http_options={"api_version": "v1beta"})
        self._types = types
        self.legend = legend
        self._systems = {}  # mode -> (that mode's legend, its instructions)
        self.system = self._for("")[1]
        self.models = list(models or [config.LLM_MODEL] + [m for m in config.LLM_FALLBACKS if m != config.LLM_MODEL])
        self.last_model = ""  # which model actually answered the last call
        self._no_budget = set()  # models that refused the thinking setting
        self._resting = {}  # model -> time until which it is over its usage limit
        self._quota_hits = {}  # model -> how many times in a row it has been over the limit
        self.last_errors = []  # (model, what went wrong, detail) for the last call

    def _for(self, mode: str):
        """The legend and the instructions for one mode ("" means every mark there is)."""
        if mode not in self._systems:
            legend = config.legend_for(self.legend, mode)
            self._systems[mode] = (legend, build_system_prompt(legend))
        return self._systems[mode]

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
        cfg_plain = types.GenerateContentConfig(**options)
        # Thinking is off by default: on the real camera it pushed full-page reads past the timeout.
        # GLYPH_THINKING_BUDGET changes it (-1 lets the model decide). A model that refuses the
        # setting is asked again without it, and remembered.
        budget = os.getenv("GLYPH_THINKING_BUDGET", "0").strip()
        cfg_quick = cfg_plain
        if budget.lstrip("-").isdigit() and int(budget) >= 0:
            cfg_quick = types.GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_budget=int(budget)), **options)

        def ask(model: str) -> str:
            cfg = cfg_plain if model in self._no_budget else cfg_quick
            try:
                r = self._client.models.generate_content(model=model, contents=parts, config=cfg)
            except Exception as e:
                if cfg is cfg_plain or _kind(e) != "refused":
                    raise
                # Most likely the thinking setting: ask once more without it.
                self._no_budget.add(model)
                print(f"[glyph] {model} refused the request with the thinking setting; asking without it")
                r = self._client.models.generate_content(model=model, contents=parts, config=cfg_plain)
            return r.text or ""

        # Every request counts against the key's allowance, so nothing is asked twice without a
        # reason: a model over its limit is left alone for a while, a model that timed out is not
        # asked again in the same round, and only a "busy" answer earns one more try.
        self.last_errors = []
        now = time.time()
        ready = [m for m in self.models if self._resting.get(m, 0.0) <= now]
        if self.models and not ready:
            raise self._quota_error(now)
        slow = 0
        for attempt in range(2):
            again = []
            for model in ready:
                if slow >= 2:
                    # Two models in a row gave no answer in time: that is the connection, or
                    # Gemini as a whole, not the models. Asking the others would cost two more
                    # requests and twenty more seconds (Nov 21: four timeouts, 39 s). They go
                    # first on the next try, since the slow ones have been moved to the back.
                    break
                hint = None
                try:
                    answer = ask(model)
                    if answer:
                        self.last_model = model
                        self._quota_hits.pop(model, None)
                        return answer
                    kind, note = "busy", "returned no text"
                except Exception as e:
                    kind, note = _kind(e), str(e)
                    hint = _retry_hint(e)
                self.last_errors.append((model, kind, note[:200]))
                print(f"[glyph] {model} failed ({WHY[kind]}): {note[:90]}")
                if kind == "key":
                    raise BrainError("Gemini refused the key in .env. Check that GEMINI_API_KEY is right.")
                if kind == "offline":
                    raise BrainError("Could not reach Gemini. Check the internet connection.")
                if kind == "gone" and model in self.models:
                    self.models.remove(model)
                    print(f"[glyph] {model} is not available for this key; skipping it from now on")
                elif kind == "quota":
                    hits = self._quota_hits.get(model, 0) + 1
                    self._quota_hits[model] = hits
                    rest = hint if hint else 60.0 * 2 ** (hits - 1)
                    self._resting[model] = time.time() + max(5.0, min(900.0, rest))
                elif kind == "slow":
                    slow += 1
                    if model in self.models and len(self.models) > 1:
                        # Too slow right now: try it last from here on, so it stops holding up answers.
                        self.models.remove(model)
                        self.models.append(model)
                elif kind == "busy":
                    again.append(model)
            if not again:
                break
            ready = again
            time.sleep(1.0)
        if not self.models:
            raise BrainError("None of the Gemini models are available for this key. Set GLYPH_MODEL in .env to one that is.")
        now = time.time()
        if all(self._resting.get(m, 0.0) > now for m in self.models):
            raise self._quota_error(now)
        tried = "; ".join(f"{m} {WHY[k]}" for m, k, _ in self.last_errors) or "no model was ready"
        raise BrainError(f"The vision model did not answer ({tried}).")

    def _quota_error(self, now: float) -> QuotaError:
        wait = max(5.0, min(self._resting.get(m, now) for m in self.models) - now)
        return QuotaError(
            "Gemini's usage limit for this key is used up for now. Free keys get a small allowance per minute "
            f"and per day. Glyph will try again in about {int(round(wait))} s.",
            retry_after=wait,
        )

    def analyze(self, page_jpg: bytes, crop_jpg: Optional[bytes] = None, context: str = "", shape_hint=None, mode: str = "") -> dict:
        legend, system = self._for(mode)
        images = [page_jpg] + ([crop_jpg] if crop_jpg else [])
        text = "Image 1: the whole page."
        if crop_jpg:
            text += " Image 2: close-up. The bright pink strokes are what the student just drew; nothing else is new."
        if context:
            text += "\n\n" + context
        raw = self._generate(images, text, system, want_json=True)
        try:
            return clean_result(_parse_json(raw), legend)
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


DEMO_GUIDE = {
    "Key ideas": "Newton's first law: an object stays at rest or moves at constant velocity unless a net force acts on it.",
    "Important notes": "Momentum is the product of mass and velocity: p = m v.",
    "Examples": "Trees, cool roofs and lighter pavement all cut the heat.",
}
# What the practice brain says. "demo" is for the built-in demo sheets, where it answers as the real
# model would for those pages; "practice" is for a real camera with no key in .env.
MOCK = {
    "hint": {
        "symbol": "spark",
        "demo": ("Problem 1, block on a frictionless incline", "Check which part of gravity actually pulls the block along the slope. Draw the weight, then split it into one piece along the incline and one into it. Which trig function goes with each?"),
        "practice": ("the problem next to your spark", "a hint for the problem next to your spark"),
    },
    "practice": {
        "symbol": "target",
        "demo": ("Problem 1, block on a frictionless incline", "A 3.0 kg crate slides down a frictionless ramp tilted at 20 degrees. Find its acceleration. Then find how long it takes to slide 2.0 m starting from rest."),
        "practice": ("the problem next to your target", "a new problem like the one next to your target"),
    },
    "answer": {
        "symbol": "check mark",
        "demo": ("Problem 1, block on a frictionless incline", "Only gravity along the slope moves the block.\nThat part is m g sin(30).\na = g sin(30) = 9.8 x 0.5\na = 4.9 m/s^2"),
        "practice": ("the problem next to your check mark", "the worked answer to the problem next to your check mark"),
    },
    "check": {
        "demo": ("Problem 1, block on a frictionless incline", "That is right. Using the part of gravity along the slope, g sin(30), was the step that fixed it."),
        "practice": ("the answer in your box", "whether the answer in your box is right"),
    },
    "define": {
        "demo": ("inertia", "How strongly an object resists any change in its motion. The more mass it has, the more inertia, and the harder it is to speed up, slow down or turn."),
        "demo_editor": ("albedo", "How much of the sunlight that hits a surface is reflected instead of absorbed. Dark roofs and asphalt have a low albedo, so they soak most of it up."),
        "practice": ("underlined word", "the meaning of the word you underlined"),
    },
    "find": {
        "demo_editor": ("heat", ""),
        "practice": ("the word in your box", ""),
    },
    "synonym": {
        "demo_editor": ("exacerbate", "worsen, intensify, aggravate, compound"),
        "practice": ("the word in your circle", "words that could replace the word you circled"),
    },
    "summarize": {
        "demo_editor": ("The effect is strongest on", "City heat is worst on still summer nights, when stored heat cannot escape, and heat waves make it worse. People with the least shade are hit hardest. Trees, cool roofs and lighter pavement all cut how much sunlight a city absorbs."),
        "practice": ("the passage beside your line", "a summary of the passage beside your line"),
    },
}


class MockBrain:
    """Canned answers, for running the app with no key and no internet.

    It cannot see: it goes by the size and shape of the new ink (and, on the demo sheets, by what
    it has already answered there, since those sheets are marked in a fixed order).
    """

    name = "mock"

    def __init__(self, legend: dict, demo: bool = False) -> None:
        self.legend = legend
        self.calls = 0
        self.demo = demo  # the built-in demo sheets: answer as the real model would for those pages
        self._given = set()  # (mode, action) pairs already answered

    def _answer(self, action: str, kind: str, mode: str) -> dict:
        entry = MOCK[action]
        key = ("demo_editor" if mode == "editor" and "demo_editor" in entry else "demo") if self.demo else "practice"
        target, text = entry.get(key) or entry["practice"]
        if key == "practice" and text:
            text = "Practice answer. With a Gemini key in .env, {} appears here.".format(text)
        t = {"kind": kind, "symbol": entry.get("symbol"), "action": action, "target": target, "response": text}
        if action == "check":
            t["verdict"] = "right" if self.demo else "unsure"
            t["work"] = "Along the incline only m g sin(30) acts. a = g sin(30) = 9.8 x 0.5 = 4.9 m/s^2." if self.demo else ""
        if action == "find":
            t["places"] = []
            if self.demo:
                from . import demo  # where the word really is on the demo reading

                t["places"] = [{"box_2d": box, "text": target} for box in demo.reading_places(target)]
        return t

    def analyze(self, page_jpg: bytes, crop_jpg: Optional[bytes] = None, context: str = "", shape_hint=None, mode: str = "") -> dict:
        self.calls += 1
        time.sleep(0.4)
        if crop_jpg is None or not shape_hint:
            return {"occluded": False, "triggers": []}
        legend = config.legend_for(self.legend, mode)
        can = set(config.actions_of(legend))
        marks = {v: k for k, v in legend.get("marks", {}).items()}  # action -> the mark that asks for it
        w, h = shape_hint
        pick = None
        if w >= 5 * h and h <= 30:
            pick = "define"  # a long flat stroke: an underline
        elif h >= 3 * w and h >= 90:
            pick = "summarize"  # a long upright stroke: a line down the margin
        elif self.demo and "check" in can and w >= 4 * h and h > 30:
            pick = "check"  # the demo worksheet's corrected line with a box drawn round it
        elif "hint" in can and 0.5 <= w / float(max(h, 1)) <= 2.0 and max(w, h) <= 160:
            # About as tall as wide: a spark, and after it (on the demo sheet) the target.
            # On the demo worksheet they come in a fixed order: spark, target, check mark.
            pick = "hint"
            if self.demo and (mode, "hint") in self._given:
                pick = "answer" if (mode, "practice") in self._given else "practice"
        elif "hint" not in can and h <= 90 and w <= 420:
            # Something drawn round a word. On the demo reading the box comes first, then the circle.
            pick = "find" if self.demo and (mode, "find") not in self._given else "synonym"
        if pick not in can:
            return {"occluded": False, "triggers": []}
        self._given.add((mode, pick))
        return clean_result({"triggers": [self._answer(pick, marks.get(pick, "symbol"), mode)]}, legend)

    def study_guide(self, items: List[dict]) -> str:
        out, seen = [], []
        for it in items:
            if it["label"] not in seen:
                seen.append(it["label"])
        for label in seen:
            out.append(f"## {label}")
            n = sum(1 for it in items if it["label"] == label)
            if self.demo and label in DEMO_GUIDE:
                out.append("- " + DEMO_GUIDE[label])
            else:
                out.extend(f"- Practice answer: the text of {label.lower()} highlight {i} goes here." for i in range(1, n + 1))
            out.append("")
        return "\n".join(out).strip()
