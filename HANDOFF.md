# Handoff log

Notes between Yoon Woo's Claude and Skylar's Claude, so nobody has to copy messages by hand.
This file lives on `main`. The rule for using it is at the top of `CLAUDE.md`.

**Read it** (from any branch, without merging): `git fetch origin && git show origin/main:HANDOFF.md`

**Add a note:** switch to `main`, pull, add an entry at the top of the log below, commit only this
file, push, switch back. Notes-only commits to this file may go straight to `main`.

Entry format: date, who, then short bullets under **Done**, **Found** (bugs, surprises, numbers) and
**Need from the other side**. Say which branch and commit. Mark a request `[open]`, and change it to
`[done]` when you have handled it. Keep entries short; link to a PR for detail.

---

## 2026-11-17 (late night), Yoon Woo's Claude

**Done** (on `main` and `camera-test`)
- First real-camera test ran: sheet detection and spark-to-hint work. Fixes from what it showed:
  - **Speed:** `gemini-flash-lite-latest` is now the first model (it answered in about 1 s; Flash kept
    hitting the timeout, so answers took 15 to 30 s). Timeout is 8 s. A model that times out is
    tried last for the rest of the session.
  - **Junk looks:** ink only counts when it shows in three looks in a row, so flickering pencil
    strokes stop being sent as "new ink" (`_ink_hist` in `glyph/engine.py`).
  - **Sheet partly out of view:** Glyph holds the last good page and says so instead of reading a
    skewed view (`find_page` in `glyph/page.py` now reports how many frame edges the sheet touches).
  - **Study guide by page:** with more than one sheet, the guide has `## Page N` sections with the
    colors as `###` sub-headings. A sheet that comes back keeps its page number (`page_signature`).
- 32 checks pass (two new ones in `tests/test_tools.py`).

- Second camera test (same night) showed more, also fixed:
  - **View froze when swapping Page and Camera:** the page no longer uses never-ending MJPEG
    streams. It fetches `/api/frame/page.jpg` and `/api/frame/raw.jpg` in a loop.
  - **Camera view was choppy:** the camera picture now comes straight from the camera
    (`Engine.live_raw_jpg`), not from the main loop, which only manages a few frames a second.
  - **New sheet is read straight away:** the first time a sheet is seen it gets one full read, so
    marks already on it are answered (`Settings.read_first_page`, off in the tests' `FAST` settings).
  - The Rotate button stays.
- 34 checks pass.

**Found**
- The flicker fix and the out-of-view hold are tested on simulated frames only, not the real camera yet.
- Page numbers in `HighlightStore` start at 2, not 1 (two resets at startup). Harmless: the guide
  renumbers pages 1, 2, 3 in order.

**Need from the other side (Skylar)**
- `[open]` `glyph/engine.py` changed again inside `_tick` and `_accept_page`. Merge `main` into
  `stuck-nudge` before going further. For the nudge clock, "new ink" should mean the steady ink
  (`ink`, after the three-look filter), and the out-of-view early return counts as "view blocked".
- `[open]` Yoon Woo and Skylar want **writer mode / annotation mode**. Not designed yet; do not start
  it. Yoon Woo put it on hold (Nov 17); it comes back when he next asks for features.

---

## 2026-11-17 (night), Yoon Woo's Claude

**Done**
- `camera-test` is merged into `main` (commit `258a31c` plus docs). `main` now has the new UI, the
  tuning page, the timing log and all three test suites (30 checks).
- Fixed the three things Skylar reported:
  - Live calls 404 on a fresh install: the client now asks for the `v1beta` API, 15 s timeout per
    call, SDK retries off. `GLYPH_TIMEOUT_SECONDS` changes the timeout.
  - Dead fallbacks: the 2.5 models are gone. Fallbacks are now `gemini-flash-lite-latest`,
    `gemini-3.8-flash`, `gemini-3.5-flash-lite`. A model that returns 404 is skipped for the session.
  - Highlight saved 3 times with a hand on the page: a piece of an already-saved highlight on the
    same page is no longer a new highlight (`glyph/highlights.py`).
- Added `start.bat` for Windows Command Prompt, and `start.sh` now works in Git Bash (uses `python`
  when there is no `python3`, and `venv/Scripts`). In Git Bash activate with `source venv/Scripts/activate`.
- New docs: `docs/camera-test-checklist.md`, `docs/event-day-plan.md`.

**Found**
- HackwithBay 4.0 lists no rule about pre-built code. Build time is short: 11:00 to 15:30 with lunch
  in the middle. Theme: "Thoughtful Agents for Productivity". Details in `docs/event-day-plan.md`.

**Need from the other side (Skylar)**
- `[open]` Merge `main` into `stuck-nudge` (`git fetch origin && git merge origin/main`). Expect
  changes in `glyph/engine.py`; keep both sides. Do not edit `glyph/static/index.html`.
- `[open]` On Windows, run all three suites and note the result here:
  `python -m tests.test_pipeline`, `python -m tests.test_rough`, `python -m tests.test_tools`.
  The highlight fix and the Git Bash path in `start.sh` were not tested on Windows. Say if
  `bash start.sh --demo` runs for you as is.
- `[open]` Run one live call and note which model answered and how long it took. The new fallback
  names were not verified with a real call.
