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
  **Nov 20, he asked for it to be "a little more organized"** (same look): the newest answer has a
  heading ("Latest answer") with the reading pill at the end of that line, so the card does not jump;
  the answer text and the picture of the mark stand in two columns (no text wrapping round the
  picture); earlier answers are grouped under page numbers, hints say which problem; headings carry
  counts. Colors, card, type and motion are as he approved them.
  **Motion he asked for (Nov 19):** text Glyph writes is written out letter by letter with a pink
  caret (answers in about 2.5 s, the study guide in about 3 s), never dropped in whole; the first-screen
  headline folds away smoothly when a read starts and the list of marks when the first answer arrives.
  **The mode switch (Nov 20 night; he asked for it "clean", in the color scheme, the animation "pretty
  cool" but "slightly minimalistic but techy"):** a frosted pill beside the name with Student | Editor.
  The thumb slides and takes its color from where it stands (sky end of the blend for Student, pink end
  for Editor). On a switch, once: a thin line of light crosses the window towards the new mode's side
  (0.8 s, faint tail), the new mode's name is worked out letter by letter from mark characters
  (`*_?[]()|`), the sheet's corners lock on again, and the mode's rows and keys come in one after
  another. Nothing else moves and the background is untouched. He has not seen it yet.
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
   definition, two highlights, a checked answer and a practice problem; clicking **Editor** at the top
   swaps in a page of reading that gets a definition, a find, synonyms, a highlight and a summary. Then
   "End session" for the study guide. Ctrl+C stops it. (With a key in `.env`, plain `--demo` sends the
   demo sheets to live Gemini and spends requests: `--demo --mock` is the free one.)
   Needs Python 3.9+.
5. **Run the checks:** `source venv/bin/activate && python -m tests.test_pipeline` → all 17 should pass.
   (Two more suites: `python -m tests.test_rough` and `python -m tests.test_tools`; 77 checks in total.
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
| Check mark next to an answer (student mode) | **Checks** it: "Looks right" / "Not yet" + which step to look at again. Never the answer (≤40 words) |
| Target, a bullseye, next to a problem (student mode) | One **new problem** of the same kind, unsolved (≤60 words) |
| Box around a word (editor mode) | **Finds** every other place the word appears and outlines them on the page view (paper Ctrl+F) |
| Circle around a word (editor mode) | Three to five **synonyms** that fit the sentence (≤35 words) |
| Line down the margin beside a passage (editor mode) | **Summary** of that passage (≤60 words) |

Hint-first is the core idea: it should push the student to solve it themselves, not hand over answers.

**Two modes (built Nov 20 night, Yoon Woo's answers in brackets):** Student, for solving problems
(spark, check mark, target, underline, circled question mark) and Editor, for reading and writing
(underline, box, circle, margin line, circled question mark). Highlights and the study guide work in
both. Switched with a button on the web page [his choice over a mark on paper]; box = find and
circle = synonyms [his choice]; a margin line = summary [his choice]; a mark that draws a
visualization is left for later [his choice]. No "keep going" card in editor mode. Switching reads
nothing and spends no request. `GLYPH_MODE` in `.env` sets the mode Glyph starts in.

Symbol → action mapping lives in `symbols.json`, and so does which marks each mode uses (`modes`). A
new symbol that reuses an action is a config change; a new action also needs its lines in `HOW` in
`glyph/brain.py`.

## Current status (Nov 20)

**Works, checked on the real camera with live Gemini (Nov 20, iPhone on a gooseneck, 0.5x lens,
wooden desk, `gemini-3.5-flash-lite` on a free-tier key, answers in 1.5 to 6 s):**
- Sheet found, flattened and tracked; Rotate; spark → hint with the pink close-up; underline →
  definition on small print ("functions", "acceleration", a three-word phrase); a second and a third
  sheet numbered in order; underlines already on a sheet left alone; the redesigned page and the
  marks drawn on the page view. Yoon Woo: "working really well", "starting to look like its final form".

**What that run got wrong (fixed the same evening, see `HANDOFF.md`; replayed, not yet re-run on the
camera):**
- Two hints for one spark (the first read of the sheet answered it, then it counted as new ink).
- "ball" underlined close under the word in small print: no look until the next mark was drawn.
- A pale green highlight over one line of small print was not saved.
- Rotate gave the same sheet a new page number.

**Earlier camera sessions (Nov 17, Nov 19):** repeated answers, wrong words for underlines on print, a
returning sheet counted as new, a gray hoodie merged into the outline, the bare desk read as a page.
All fixed on Nov 19 and none of them came back on Nov 20.

**Nov 20, about 22:00:** Yoon Woo ran section 3c of the checklist on the camera and reported that all
the fixes work ("the product is working really well"). The session was not read back from the Mac.

**Built and covered by the checks (77 pass: 17 + 9 + 51), but not yet seen on the real camera or
answered by live Gemini:**
- Everything built Nov 20 night: the check mark, the target, the two modes, box / circle / margin
  line, the places a boxed word was found drawn on the page. The prompts for these have never been
  sent to Gemini. The riskiest are find (it relies on the model returning `box_2d` positions for
  words in small print) and check (a wrong "Looks right" is worse than no answer).
- Whether a small check mark alone is enough ink for a look (a look needs 120 px; a spark has about
  twice the strokes of a tick the same size), and whether a box or circle drawn tight round print
  counts as new ink.
- The stuck nudge; the marks drawn on the Camera view.
- Study guide sections per page and the real study guide call; pink and blue highlighters; the
  circled question mark.

**What is in the app:**
- Spark → hint, underline → definition, circled question mark → explanation, highlights → study guide
  (one section per sheet when more than one was used). Check mark → verdict, target → practice
  problem, and in editor mode box → find, circle → synonyms, margin line → summary (see the table).
- Student | Editor switch at the top left of the page (`POST /api/mode`). The list of marks on the
  first screen and the line of marks along the bottom follow the mode.
- Web page at http://127.0.0.1:8765: left half is what Glyph sees: the flattened page with
  corner brackets, a pink frame and sweep while a mark is read, the camera as an inset (swappable; the camera view shows the same
  mark frame, highlights and covers, mapped onto the desk from `status.view.cam`),
  and a row of frosted readouts (sheet, page, ink, new ink, frame rate, last answer). Right half (a
  white sheet floating on the color field) is
  the newest answer as a large card with a cut-out of the mark, highlights by color, a timeline, page
  numbers, and a typeset study guide (Copy / Print). `/?guide` opens on the guide.
- Page numbers: 1, 2, 3 in the order sheets are first seen. A returning sheet keeps its number (also
  when turned 180°). Clicking an earlier number and "Yes, same sheet" merges by hand (`POST /api/page`).
- `--demo` plays a simulated worksheet with no camera, and a page of reading when the mode is switched
  to Editor (each sheet moves on only while its mode is on). Without a key, or with `--mock`, it shows
  practice answers. With a key, `--demo` alone spends real requests.
- `/tune` page: live views of ink / highlighter / hand detection, sliders, click-to-pick highlighter
  colors, saves to `.env`.
- Logs per session in `sessions/<ts>/`: `timings.jsonl` (seconds per look, which model answered, which
  failed first), `looks/` (what was sent to the model), `camera/` (pictures from moments when no
  sheet was found).
- `bench.py` times each model on the demo page. Still not run: it needs a key with allowance left.

**Known limits:**
- Gemini keys (Nov 20): the first key's project is on a paid tier with no credit, so it is refused
  until credit is bought ($5 is the smallest amount). The key in `.env` now is from a second project on
  the free tier, which showed about 10 requests a day for the model Glyph uses first. A session
  costs one request per new sheet and one per mark. Yoon Woo plans to buy the $5 for the event.
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
| `glyph/camera.py` | Frame sources: camera, video file, photo list, demo (`DemoSource`: one sheet per mode). Chooses the camera; says how to connect the phone |
| `glyph/page.py` | Sheet detection + perspective warp, ink strength, what counts as new ink, hand/object "cover" (not shadows), telling sheets apart, focus crop |
| `glyph/engine.py` | Main loop. New ink + still picture → "look". Keeps the outline steady, follows a sliding sheet, cooldown 4s, max 8 calls/min, backoff on errors, dedupes repeated answers |
| `glyph/highlights.py` | Highlighter detection by color, saves crops, tracks per page |
| `glyph/brain.py` | Prompt (built per mode from the legend: `HOW` has the lines for each action) + Gemini call with model fallbacks and usage-limit handling, returns strict JSON; `MockBrain` for testing (it goes by the shape of the new ink, it cannot see) |
| `glyph/session.py` | Saves each session to `sessions/<timestamp>/` (events, model inputs, study guide) |
| `glyph/app.py` | FastAPI routes: `/`, `/api/frame/page.jpg`, `/api/frame/raw.jpg` (the page asks for these in a loop), `/api/state`, `/api/look`, `/api/rotate`, `/api/page` (same sheet as an earlier number), `/api/study-guide`. Puts the name from `GLYPH_NAME` into the pages |
| `glyph/tune.py` | Tuning page backend: detection overlays, color picking, save to `.env` |
| `bench.py` | Model timing on the demo page (spends real requests) |
| `HANDOFF.md` | Notes between the two Claudes (see the handoff rule at the top) |
| `docs/` | Camera test checklist, event-day plan |
| `glyph/config.py` | Thresholds (settle time, ink sensitivity, highlight colors, rate limits); most can be overridden in `.env` |

Key design choices:
- (Nov 20 night) The model is told only about the marks of the mode that is on, and anything else
  it returns is dropped (`config.legend_for`, `clean_result`). A look carries the mode it was sent in.
- A check: the model first writes its own solution in a `work` field (thinking is off, so this is
  where it reasons), then a verdict. `work` is saved in `sessions/<ts>/looks/NNN_check.txt` and never
  sent to the web page. No clear verdict counts as "unsure", never as right.
- Marks on words (underline, box, circle, margin line) and check marks already on a sheet when it
  comes into view are left alone; the prompt says so and the engine drops them. "Read page now"
  answers them (the note sent with the pictures says the student asked).
- A second spark, question mark, check or target by the same problem is answered again; a mark on a
  word is answered once.
- Find: the model returns `places` as `box_2d` [ymin, xmin, ymax, xmax] on a 0 to 1000 scale of the
  page picture. Boxes that cannot be one word are dropped. The sentence on the card is written by the
  engine from the counts, so it always matches what is outlined. The outlines stay until the next
  answer or a new sheet.
- A long upright stroke in a mode with margin lines gets a close-up as wide as the page.
- (Nov 20: the pink goes on the ink itself, by darkness, after the close-up is enlarged. Painting the
  whole new-ink area turned a small spark into a solid pink blob and live Gemini answered nothing.)
- After a full read that gave an answer, the picture it was given is the remembered page (not under a
  hand). The remembered page can be older than that picture: the read waits for the cooldown.
- A sheet that comes into view with underlines on it: those are left alone (Yoon Woo wants this).
  Symbols on it are answered. "Read page now" answers everything.
- Ink within four pixels of print is not "new" by the main rule (a slipped sheet looks like that).
  It does count where it is solid, the paper there was clean, and the print around it is still in
  place spot for spot. A short flat stroke under print is enough for a look even under 120 pixels:
  a word in 10-point type is 25 pixels wide on the flattened page.
- A highlight is a pale-colored patch with enough strongly colored paint in it, in a band that is
  solid together with its letters. Colored pen strokes are not solid.
- Page signatures are kept unfiltered and filtered when compared, so they can be turned with the view.
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

0. **Modes: built Nov 20 night** as Student and Editor (see "What Glyph is"). Left from what he and
   Skylar listed: a mark that makes a **visualization** in editor mode (he chose "leave it for
   later"; a concept map of boxes and arrows drawn by the page from the model's list was the
   suggestion), and whatever the "and more" in his message was (ask).

1. **Camera run on live Gemini of the Nov 20 night features** (`docs/camera-test-checklist.md`,
   section 3d, about 8 requests). The four fixes of section 3c passed on the camera (his report).
   Also still unseen on the camera: the study guide, the nudge.
2. **Stuck nudge** — built Nov 19 (no writing for `GLYPH_STUCK_SECONDS`, 90 by default → one "keep going"
   card, no model call). Still open from the idea: noticing the student pick up their phone.
3. **Mistake catcher + mistake log/calendar** — spot errors in written work, keep a running log over time.
4. **Paper Ctrl+F** — built Nov 20 night as the box in editor mode. Not built: asking for a word that
   is not on the page in front of you (typing or saying it).
5. **Custom symbol mapping UI** — let users add their own symbols without editing JSON.
6. Audio replies (voice), finger-frame screenshot (point/frame with fingers to capture a region),
   left-hand gestures.

## Open questions

- Answer latency with live Gemini now that thinking is off and the fast model goes first.
- Does `gemini-3.5-flash-lite` accept the thinking setting, and are its hints good enough? (If it
  refuses the setting, Glyph asks again without it; the terminal says so.)
- Do green, pink and blue highlighters separate cleanly under the desk lamp and at the venue? (Nov 20:
  his green is pale, saturation 30 to 65 after the lighting is evened out; found after the fix, on the
  saved picture only.)
- Does Continuity Camera stay connected for a whole session on a cable?
- HackwithBay rules: the event page lists no rule on pre-built code (checked Nov 17). Ask at the opening.
  Build time is 11:00 to 15:30. See `docs/event-day-plan.md`.

## Working conventions

- Keep the MVP small; add features only after the camera works for real.
- Don't commit `.env`, `venv/`, `sessions/`, or `camera_check/` (already in `.gitignore`).
- Run the checks before pushing: `source venv/bin/activate && python -m tests.test_pipeline`.
