# Glyph — context for Claude

Read this first. It catches you up on what this project is, where it stands, and what's next.
The README covers how to run it; this file covers the why and the plan.

## The team and the goal

- **Yoon Woo** and **Skylar**, UCLA. Building Glyph for **HackwithBay 4.0** (San Francisco, Tue Nov 24, 2026).
- This repo is the **practice build**. We use it to learn what's hard (camera, lighting, symbol
  detection, model latency) before the event.
- **Rule: at the hackathon we rebuild from scratch in a new repo.** Don't copy code over. Use this
  repo to learn, then rewrite. Help with notes, plans and lessons learned, not paste-ready code
  meant to be carried into the event build.

## If you're helping Skylar: get set up

Walk Skylar through these in order, checking each one works before moving on.

1. **Clone the repo** (it's public for now, so no invite needed to clone; he needs to be added as a
   collaborator before he can push): `git clone https://github.com/yoonwoo-lee/glyph-practice.git && cd glyph-practice`
2. **Get his own Gemini API key** at https://aistudio.google.com/apikey (free tier is fine).
3. **Make `.env`:** `cp .env.example .env`, then put the key after `GEMINI_API_KEY=`. Never commit `.env`.
   (`start.sh` tries to copy a key from a `../talking-menu` folder; that only exists on Yoon Woo's Mac,
   so on Skylar's machine it just copies `.env.example`. Fill the key in afterward.)
4. **Run the demo (no camera needed):** `bash start.sh --demo`. First run sets up a venv (~1 min), then a
   browser tab opens at http://127.0.0.1:8765. He should see a simulated worksheet get a hint, a
   definition and two highlights, then click "End session" to see the study guide. Ctrl+C stops it.
   Needs Python 3.9+.
5. **Run the checks:** `source venv/bin/activate && python -m tests.test_pipeline` → all 12 should pass.
6. **Read the code** in the order of the "How it works" table below, so he understands the pipeline.
7. **Optional camera test:** `bash start.sh --list-cameras`, open `camera_check/` to find his camera
   number, then `bash start.sh --camera <n>`. Steps and troubleshooting are in the README.
8. **Start Skylar's task below** on a new branch: `git checkout -b stuck-nudge`. Yoon Woo is on the
   `camera-test` branch (real-camera testing and tuning), so the two don't overlap. Open a pull request
   when done; don't push straight to `main`.

## Skylar's task: stuck nudge (branch `stuck-nudge`)

Small and self-contained: sized to finish in one sitting. Build and test it entirely with
`--demo` and the automated checks; no camera needed. Skylar is on Claude Pro, so keep it lean:
read only the files listed here, don't refactor anything else, and skip big rewrites.

**What it does:** if the student stops writing for a while, Glyph posts one friendly "keep going"
card in the feed. No model call (costs nothing, works offline).

**Rules:**
- "Writing" = new ink accepted on the page. Track the time of the last new ink in `Engine`.
  Start the clock when a page is first accepted, and reset it on new ink, new page, and rotate.
- If no new ink for `stuck_seconds` (default **90**) while a sheet is in view, add **one** event:
  `session.add_event("nudge", "Still with it?", <message>)`. Pick the message from a short list of
  3–5 encouraging lines (e.g. "Try writing down what you know so far." / "Stuck? Draw a spark next to
  the problem for a hint."). Never give an answer.
- Only **one nudge per stall**: no more nudges until new ink appears again.
- Don't nudge while a model call is running, or while the view is blocked (hand/object on page).
- Make it configurable: add `stuck_seconds` to the `Settings` dataclass in `glyph/engine.py` and a
  `GLYPH_STUCK_SECONDS` override the same way the other settings are read in `glyph/config.py`
  (add a commented example line to `.env.example`). `0` turns the feature off.

**Where to change things:**
- `glyph/engine.py`: `Settings`, `_accept_page` / new-ink handling inside `_tick` (track the time),
  and a small check at the end of `_tick`. `_tick(frame, now)` takes `now` as an argument, so tests
  can fake time.
- Do **not** edit `glyph/static/index.html`: the UI is being redesigned on `camera-test`, and the new
  version already styles the `nudge` event. On `main` the card will simply appear unstyled for now.
- `README.md`: one line in the marks/features area mentioning the nudge and `GLYPH_STUCK_SECONDS`.

**Tests (add to `tests/test_pipeline.py`, follow the existing tests' pattern):**
1. No new ink past `stuck_seconds` → exactly one `nudge` event.
2. Waiting longer still → still one (no repeats).
3. New ink after the nudge, then another long gap → a second nudge.
4. `stuck_seconds = 0` → never nudges.
All 12 existing checks must still pass.

**Done when:** tests pass, `bash start.sh --demo` runs without errors, and the PR describes what
changed. Phone-scroll detection (from the original idea) is out of scope for now.

## What Glyph is

A paper-based AI tutor. A camera looks down at your desk. You study on real paper and never type;
you draw marks, and Glyph reacts:

| Mark on paper | What Glyph does |
|---|---|
| Spark (starburst / asterisk) next to a problem | One **hint**, never the answer (≤50 words) |
| Underline a word | **Defines** it in the context of the page (≤35 words) |
| Highlighter (yellow / green / pink / blue) | Saves the highlight; "End session" builds a **study guide** grouped by color |
| Circled question mark (extra, removable) | **Explains** the passage (≤70 words) |

Hint-first is the core idea: it should push the student to solve it themselves, not hand over answers.

Symbol → action mapping lives in `symbols.json`, so new symbols are a config change, not a code change.

## Current status (Nov 17)

**Built (MVP, only the three must-haves + the extra symbol):**
- Spark → hint, underline → definition, highlights → end-of-session study guide.
- Local web UI at http://127.0.0.1:8765 (page view / raw camera view, feed, study guide tab).
- `--demo` mode plays a simulated worksheet so everything runs with no camera.
- 12 automated checks pass on simulated frames (`python -m tests.test_pipeline`): full flow,
  half-drawn symbol, hand on page, object left on page, nudged sheet, new sheet, model errors,
  no-sheet fallback, no repeated answers.

**Not tested yet:**
- Real camera (plan: iPhone via macOS Continuity Camera on a gooseneck clamp, pointing straight down)
- Real lighting and handwriting, highlighter color ranges under a real lamp
- Live Gemini calls end to end and how long each answer takes

## Stack

- **Python 3.9** (matches the Mac), venv created by `start.sh`
- **OpenCV** — finds the sheet, flattens it, finds ink, detects highlighter by HSV color (no model call)
- **Gemini vision** via `google-genai` — `gemini-flash-latest`, falls back to
  `gemini-flash-lite-latest`, `gemini-2.5-flash`, `gemini-2.5-flash-lite` on errors / 503s
- **FastAPI + uvicorn** — local server, MJPEG streams, JSON API
- Vanilla HTML/JS front end (`glyph/static/index.html`)
- Key: `GEMINI_API_KEY` in `.env` (never committed). Without a key it runs with fake answers.

## How it works (files)

| File | Job |
|---|---|
| `run.py` | CLI: `--demo`, `--camera N`, `--list-cameras`, `--source <video/photos>`, `--mock`, `--rotate`, `--port` |
| `glyph/camera.py` | Frame sources: camera, video file, photo list, demo |
| `glyph/page.py` | Sheet detection + perspective warp, ink mask, hand/object "cover" mask, focus crop |
| `glyph/engine.py` | Main loop. New ink + still picture → "look". Cooldown 4s, max 8 calls/min, backoff on errors, dedupes repeated answers |
| `glyph/highlights.py` | Highlighter detection by color, saves crops, tracks per page |
| `glyph/brain.py` | Prompt + Gemini call, returns strict JSON (hint / define / explain); `MockBrain` for testing |
| `glyph/session.py` | Saves each session to `sessions/<timestamp>/` (events, model inputs, study guide) |
| `glyph/app.py` | FastAPI routes: `/`, `/stream/page`, `/stream/raw`, `/api/state`, `/api/look`, `/api/rotate`, `/api/study-guide` |
| `glyph/config.py` | Thresholds (settle time, ink sensitivity, highlight colors, rate limits); most can be overridden in `.env` |

Key design choices:
- Only **new** ink is sent at full contrast (old ink faded), so old symbols aren't answered twice.
- Ink right next to a hand/object is ignored until it moves. User should lift their hand after drawing.
- Highlights are detected locally, so they cost no API calls.

## Next up (not built yet, rough priority)

1. **Test with the real camera** and tune thresholds (biggest unknown).
2. **Stuck nudge** — if the student stalls (or picks up their phone and scrolls), Glyph nudges them to keep going.
3. **Mistake catcher + mistake log/calendar** — spot errors in written work, keep a running log over time.
4. **Paper Ctrl+F** — ask where something is on the page and have it pointed out.
5. **Custom symbol mapping UI** — let users add their own symbols without editing JSON.
6. Audio replies (voice), finger-frame screenshot (point/frame with fingers to capture a region),
   left-hand gestures.

## Open questions

- Answer latency with live Gemini: is it fast enough to feel instant?
- Does Continuity Camera hold a stable picture from above, and does the gooseneck stay steady?
- Do highlighter colors separate cleanly under typical dorm/venue lighting?
- Check HackwithBay rules on pre-built code (we're planning to rebuild either way).

## Working conventions

- Keep the MVP small; add features only after the camera works for real.
- Don't commit `.env`, `venv/`, `sessions/`, or `camera_check/` (already in `.gitignore`).
- Run the checks before pushing: `source venv/bin/activate && python -m tests.test_pipeline`.
