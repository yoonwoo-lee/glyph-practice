# Glyph — context for Claude

Read this first. It catches you up on what this project is, where it stands, and what's next.
The README covers how to run it; this file covers the why and the plan.

## Handoff rule (both Claudes, every session)

1. **Before starting:** `git fetch origin && git show origin/main:HANDOFF.md` and read the newest
   entries. Do anything marked `[open]` that is addressed to your side, or say why not.
2. **Before stopping:** add an entry to `HANDOFF.md` on `main` (what you did, what you found, what you
   need from the other side) and push it. How to do that is at the top of that file. Notes-only
   commits to `HANDOFF.md` are the one exception to "don't push straight to `main`".
3. Yoon Woo and Skylar should only have to say "check the handoff". Do not ask them to relay messages.

## The team and the goal

- **Yoon Woo** and **Skylar**, UCLA. Building Glyph for **HackwithBay 4.0** (San Francisco, Tue Nov 24, 2026).
- **Who does what (agreed Nov 18):** Yoon Woo writes all the code, the stuck nudge included. Skylar does
  the business side: logo, colors, what each mark means, the demo story and who it is for. The setup
  steps and the stuck-nudge task below are kept as written; whoever builds the nudge follows the task.
- **The name may change** (Glyf, Glyff and Gliff were floated Nov 19: there are already several
  "glyph" AI products). It is one setting, `GLYPH_NAME` in `.env`. Don't hard-code the name anywhere.
- **Look:** a light sky blue `#45B6EC`, white `#FCFFFF` and hot pink `#D83995` (from Yoon Woo's reference,
  Nov 19; he asked for the blue lighter than the reference's `#0593C6`, which now only adds depth in one corner).
  The colors must **blend**: one field of sky blue with a pink bloom runs behind the whole window, and
  the paper and a white answers sheet float on it. Hot pink marks whatever is being read right now
  (it gathers behind the paper while a mark is read). Skylar likes it minimal, Yoon Woo wants it a
  little richer: keep the layout plain and put the richness in that one background.
  **The answers side is settled** (Yoon Woo, Nov 19 evening: "it was perfect"): a white sheet, the
  newest answer in a white card with a sky-to-pink edge, the underlined word in pink, pink count
  badges and page number, a pink End session button, a blue-to-pink headline on the first screen.
  The one thing he rejected there is a thick, full-width hot pink "Reading your mark" bar: that is a
  small sky-blue pill now. Two other tries were dropped the same evening (pink removed from that
  side; the answer as a filled blue block). Don't restyle this side again unless he asks.
  **Motion he asked for (Nov 19):** text Glyph writes is written out letter by letter with a pink
  caret (answers in about 2.5 s, the study guide in about 3 s), never dropped in whole; the first-screen
  headline folds away smoothly when a read starts and the list of marks when the first answer arrives.
  **Toned down after outside feedback (Nov 19, 19:20):** the pink in the background is one soft glow in
  the bottom left corner (several strong blooms read as "blotches"), and the scan is a thin line
  passing slowly down the page with a faint glow, not a tall fast pink bar. Don't turn either back up.
- **Order of work (Yoon Woo, Nov 19):** UI first for now; features later. He asked to be reminded:
  when the UI work wraps up, remind him of the camera test on live Gemini (the one that decides
  whether the features really work), then the stuck nudge and the camera-view overlay.
  (Nov 19, 21:10: he went out and asked for the nudge and the overlay to be built meanwhile. Both are
  done, see `HANDOFF.md`. What is left to remind him of is the camera test.)
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
4. **Run the demo (no camera needed):** `bash start.sh --demo`. Skylar is on Windows with Git Bash:
   `bash start.sh` works there too, and he activates with `source venv/Scripts/activate` instead of
   `source venv/bin/activate` below. (`start.bat` is for plain Command Prompt.) First run sets up a venv (~1 min), then a
   browser tab opens at http://127.0.0.1:8765. He should see a simulated worksheet get a hint, a
   definition and two highlights, then click "End session" to see the study guide. Ctrl+C stops it.
   Needs Python 3.9+.
5. **Run the checks:** `source venv/bin/activate && python -m tests.test_pipeline` → all 17 should pass.
   (Two more suites: `python -m tests.test_rough` and `python -m tests.test_tools`; 59 checks in total.
   Run them one after another: run together they starve each other and miss their timing.)
6. **Read the code** in the order of the "How it works" table below, so he understands the pipeline.
7. **Optional camera test:** `bash start.sh --list-cameras`, open `camera_check/` to find his camera
   number, then `bash start.sh --camera <n>`. Steps and troubleshooting are in the README.
8. **Start Skylar's task below** on a new branch: `git checkout -b stuck-nudge`. Yoon Woo is on the
   `camera-test` branch (real-camera testing and tuning), so the two don't overlap. Open a pull request
   when done; don't push straight to `main`.

## Skylar's task: stuck nudge (branch `stuck-nudge`)

**Built Nov 19 (evening) by Yoon Woo's Claude, at Yoon Woo's request, and merged to `main`.** The task
is kept below as written, as the record of what was asked. Differences from it: a new highlight also
restarts the clock, and the checks drive `_tick` with a made-up clock (`_stepper` in the tests).

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
- Do **not** edit `glyph/static/index.html`: the redesigned UI (now on `main`) already styles the
  `nudge` event.
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

## Current status (Nov 19)

**Works, checked on the real camera (Nov 17 and Nov 19, iPhone on a gooseneck, 0.5x lens, wooden desk):**
- Sheet found and flattened; Rotate turns it upright; the first full read of a sheet; spark → hint and
  underline → definition on handwriting; yellow highlights saved; marks are picked up quickly.

**What the Nov 19 camera session got wrong (all fixed the same day, see `HANDOFF.md`):**
- The same mark answered several times; underlines on a printed speech got the wrong word or none;
  one sheet taken away and brought back counted as a new page (numbers ran up to 18); a gray hoodie
  merged into the sheet's outline; the bare desk was read as a page and saved as highlights.

**Built and covered by the checks (59 pass: 17 + 9 + 33), but not yet run on the real camera or
against live Gemini:**
- The Nov 19 fixes: new strokes recolored pink in the close-up and the model told to answer only
  those; nothing sent until the remembered page lines up with the page now; specks and edge slivers
  dropped; one answer per mark; page numbers 1, 2, 3 that survive a sheet leaving and returning;
  "No sheet in view" on a bare desk; the redesigned page.
- They were developed by replaying the pictures saved during the Nov 19 session. The replay now gives
  one full read per sheet, no repeats and no false highlights. No Gemini call was made in that replay
  (the sandbox cannot reach Gemini), so how the model takes the pink close-up is untested.
- Study guide sections per page; highlights in green, pink and blue; the circled question mark.

**What is in the app:**
- Spark → hint, underline → definition, circled question mark → explanation, highlights → study guide
  (one section per sheet when more than one was used).
- Web page at http://127.0.0.1:8765: left half is what Glyph sees: the flattened page with
  corner brackets, a pink frame and sweep while a mark is read, the camera as an inset (swappable; the camera view shows the same
  mark frame, highlights and covers, mapped onto the desk from `status.view.cam`),
  and a row of frosted readouts (sheet, page, ink, new ink, frame rate, last answer). Right half (a
  white sheet floating on the color field) is
  the newest answer as a large card with a cut-out of the mark, highlights by color, a timeline, page
  numbers, and a typeset study guide (Copy / Print). `/?guide` opens on the guide.
- Page numbers: 1, 2, 3 in the order sheets are first seen. A returning sheet keeps its number (also
  when turned 180°). Clicking an earlier number and "Yes, same sheet" merges by hand (`POST /api/page`).
- `--demo` plays a simulated worksheet with no camera; without a key it shows practice answers.
- `/tune` page: live views of ink / highlighter / hand detection, sliders, click-to-pick highlighter
  colors, saves to `.env`.
- Logs per session in `sessions/<ts>/`: `timings.jsonl` (seconds per look, which model answered, which
  failed first), `looks/` (what was sent to the model), `camera/` (pictures from moments when no
  sheet was found).
- `bench.py` times each model on the demo page. Still not run: it needs a key with allowance left.

**Known limits:**
- A free Gemini key runs out after a few dozen reads in a day. Yoon Woo's ran out on Nov 17.
- A full page of small print at 0.5x and 1080p is near the limit of what the camera resolves.
- Glare directly on a highlight splits or hides it.
- The page view updates a few times a second (each frame is analysed); the camera view is smooth.
- Text orientation is not detected: the user clicks Rotate.

## Stack

- **Python 3.9** (matches the Mac), venv created by `start.sh`
- **OpenCV** — finds the sheet (by color first: paper is the big area that is neither colorful nor
  dark; by brightness as a fallback), flattens it, finds ink, detects highlighter by HSV color (no model call)
- **Gemini vision** via `google-genai`, v1beta API, thinking off, 10 s per call (the shortest Gemini
  accepts). Models in order: `gemini-3.5-flash-lite`, `gemini-flash-lite-latest`, `gemini-3.8-flash`,
  `gemini-flash-latest`. A model that times out is tried last from then on, one over its usage limit
  (429) is left alone for a minute or more, one the key cannot use (404) is dropped. The 2.5 models
  are closed to new keys.
- **FastAPI + uvicorn** — local server, one-picture-per-request camera and page views, JSON API
- Vanilla HTML/JS front end (`glyph/static/index.html`)
- Key: `GEMINI_API_KEY` in `.env` (never committed). Without a key it runs with fake answers.

## How it works (files)

| File | Job |
|---|---|
| `Start Glyph.command` | Mac: double-click to start with the camera (keeps the Mac awake) |
| `run.py` | CLI: `--demo`, `--camera auto` (default: the camera that sees a sheet) or `--camera N`, `--list-cameras`, `--source <video/photos>`, `--mock`, `--rotate`, `--port` |
| `glyph/camera.py` | Frame sources: camera, video file, photo list, demo. Chooses the camera; says how to connect the phone |
| `glyph/page.py` | Sheet detection + perspective warp, ink strength, what counts as new ink, hand/object "cover" (not shadows), telling sheets apart, focus crop |
| `glyph/engine.py` | Main loop. New ink + still picture → "look". Keeps the outline steady, follows a sliding sheet, cooldown 4s, max 8 calls/min, backoff on errors, dedupes repeated answers |
| `glyph/highlights.py` | Highlighter detection by color, saves crops, tracks per page |
| `glyph/brain.py` | Prompt + Gemini call with model fallbacks and usage-limit handling, returns strict JSON (hint / define / explain); `MockBrain` for testing |
| `glyph/session.py` | Saves each session to `sessions/<timestamp>/` (events, model inputs, study guide) |
| `glyph/app.py` | FastAPI routes: `/`, `/api/frame/page.jpg`, `/api/frame/raw.jpg` (the page asks for these in a loop), `/api/state`, `/api/look`, `/api/rotate`, `/api/page` (same sheet as an earlier number), `/api/study-guide`. Puts the name from `GLYPH_NAME` into the pages |
| `glyph/tune.py` | Tuning page backend: detection overlays, color picking, save to `.env` |
| `bench.py` | Model timing on the demo page (spends real requests) |
| `HANDOFF.md` | Notes between the two Claudes (see the handoff rule at the top) |
| `docs/` | Camera test checklist, event-day plan |
| `glyph/config.py` | Thresholds (settle time, ink sensitivity, highlight colors, rate limits); most can be overridden in `.env` |

Key design choices:
- (Nov 20: the pink goes on the ink itself, by darkness, after the close-up is enlarged. Painting the
  whole new-ink area turned a small spark into a solid pink blob and live Gemini answered nothing.)
- In the close-up sent to the model, the **new** strokes are recolored hot pink and nothing is faded;
  the prompt says to answer only the pink strokes. Fading the old ink left the model little to read
  around an underline on print (the likely cause of the Nov 19 misses; not yet confirmed against live
  Gemini). The student writes with any pen: the pink is ours.
- One answer per mark: a full read never repeats an (action, target) already answered; a new-ink look
  repeats one only for a second symbol-sized spark or question mark with a different answer.
- No look until the remembered page and the page now line up ("same"); "moved" waits, "lost" means a
  different or changed sheet. This stopped shifted print from being sent as new ink.
- The overlays are drawn in the browser from `status.view`; the page and camera pictures are sent clean.
- "New" means clearly darker than anything the remembered page had within a few pixels, in the middle
  of the last three frames. A yes/no ink mask made faint pencil flicker in and out as "new ink".
- The sheet's outline is held fixed once a page is accepted and moves only when four frames agree.
  When it moves, the remembered page is lined up again with the page as flattened now.
- Ink right next to a hand/object is ignored until it moves. User should lift their hand after drawing.
  A shadow is not an object.
- Highlights are detected locally, so they cost no API calls.
- Requests are scarce: nothing is read twice without a reason (see the Gemini bullet above).

## Next up (not built yet, rough priority)

0. **Writer mode / annotation mode** (asked for Nov 17, on hold; raise it when Yoon Woo next asks for
   features): the same marks do different
   jobs per mode. Writer = solving problems, annotation = readings and books.

1. **Run `docs/camera-test-checklist.md` on the real camera** with the Nov 19 changes, on a key with
   billing turned on.
2. **Stuck nudge** — built Nov 19 (no writing for `GLYPH_STUCK_SECONDS`, 90 by default → one "keep going"
   card, no model call). Still open from the idea: noticing the student pick up their phone.
3. **Mistake catcher + mistake log/calendar** — spot errors in written work, keep a running log over time.
4. **Paper Ctrl+F** — ask where something is on the page and have it pointed out.
5. **Custom symbol mapping UI** — let users add their own symbols without editing JSON.
6. Audio replies (voice), finger-frame screenshot (point/frame with fingers to capture a region),
   left-hand gestures.

## Open questions

- Answer latency with live Gemini now that thinking is off and the fast model goes first.
- Does `gemini-3.5-flash-lite` accept the thinking setting, and are its hints good enough? (If it
  refuses the setting, Glyph asks again without it; the terminal says so.)
- Do green, pink and blue highlighters separate cleanly under the desk lamp and at the venue?
- Does Continuity Camera stay connected for a whole session on a cable?
- HackwithBay rules: the event page lists no rule on pre-built code (checked Nov 17). Ask at the opening.
  Build time is 11:00 to 15:30. See `docs/event-day-plan.md`.

## Working conventions

- Keep the MVP small; add features only after the camera works for real.
- Don't commit `.env`, `venv/`, `sessions/`, or `camera_check/` (already in `.gitignore`).
- Run the checks before pushing: `source venv/bin/activate && python -m tests.test_pipeline`.
