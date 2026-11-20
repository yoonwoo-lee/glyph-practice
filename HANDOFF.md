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

## 2026-11-19 (16:00), Yoon Woo's Claude

Yoon Woo sent a reference for the colors (sky blue `#0593C6`, white `#FCFFFF`, hot pink `#D83995`,
blue melting into pink behind ribbed glass) and said the first version's colors "don't really blend".
He wants it a little less minimal; Skylar likes it minimal.

**Done** (`glyph/static/index.html`, `glyph/static/tune.html`; styles only, no engine change)
- One color field behind the whole window: deep sky to sky, a hot pink bloom low on the left that
  runs under the seam, fine vertical ribs. It drifts slowly; motion is off under "reduce motion".
- The answers side is now a white sheet with rounded corners floating on the field. Readouts, status
  and buttons on the left are frosted white tiles so the color shows through them.
- While a mark is read the pink gathers behind the paper. Answer card and study guide have a
  sky-to-pink edge; the first-screen headline and the "Reading your mark" bar use the same blend.
- Layout, wording, Rotate / Read page now / Tune, and every id the script uses are unchanged.
- 18:30: Yoon Woo found the answers side had far too much pink. Its main color is now the same sky
  blue; pink there is only for the student's own mark (cut-out, underlined word, spark while reading).
  The pink bloom in the background stays on the left.
- 16:15: Yoon Woo asked for a lighter blue. The field is now `#2CA5DE` to `#45B6EC` to `#8FD6F6`, the
  left side's own text is dark ink, and the blends pass through lilac instead of purple.

**Found**
- White text does not hold up on a sky this light (about 2:1), so text on the field is dark ink and
  everything else sits on frosted tiles. Hot pink on white is 4.3:1: fine for large type, use
  `--pink-deep` for small.

**Not verified:** Safari (the Mac's default browser) and the real camera view. Checked in Chrome at
1440 and 820 wide with the demo sheet.

---

## 2026-11-19 (afternoon), Yoon Woo's Claude

Yoon Woo ran the camera at his desk on Nov 19 and reported: marks are picked up quickly now, but the
same mark is answered several times; underlines on a printed speech are not read; one sheet moved out
and back in counted as two pages. He also asked for a more technical look while scanning, a sky blue,
white and hot pink color scheme, and room to rename the app. On `main` and `camera-test`:
`ec55146` (the fixes) and `203e678` (the look, checks, docs). 53 checks pass (12 + 9 + 32).

**Done**
- **One answer per mark.** `Engine._handled` remembers (action, target, page). A full read never
  repeats one; a new-ink look repeats one only for a second symbol-sized spark or question mark whose
  answer is different.
- **Close-up for the model:** the new strokes are recolored hot pink and nothing is faded
  (`make_focus_crop`, `whole_strokes`). The prompt says to answer only the pink strokes. This is
  internal: the student writes with any pen.
- **No look until the page lines up.** `register()` matches small blocks of the remembered page to the
  page now and fits one transform; `_line_up` returns same / moved / lost. Specks and anything within
  16 px of the sheet's edge are dropped (`marks_only`).
- **Sheet detection:** several brightness levels, square-corner and real-paper-edge checks (a gray
  hoodie beside the sheet no longer joins the outline); `paper_share` decides "No sheet in view", and
  then nothing is read or saved.
- **Page numbers:** 1, 2, 3 in order first seen; a returning sheet keeps its number, also turned 180°;
  blank sheets reuse numbers; `POST /api/page {"same_as": n}` merges by hand.
- **Look:** `glyph/static/index.html` rewritten. Overlays are drawn in the browser from
  `status.view`; the JPEGs are clean. Rotate, Read page now and Tune are still there.
- **Name:** `GLYPH_NAME` in `.env` → `config.APP_NAME` → pages (`__NAME__`) and prompt.
- **ECC** (github.com/affaan-m/ECC) is installed for this folder only on Yoon Woo's Mac, as a Claude
  Code plugin, hooks off. Its settings are in `.claude/settings.local.json`, which is not committed.

**Found** (from `sessions/2026-11-19_*/looks`, `camera` and `timings.jsonl` on Yoon Woo's Mac)
- Most of the repeated reads were not the student's marks: fingertips, the desk at the sheet's edge
  and print that had shifted a pixel or two were sent as "new ink", and the model answered whatever
  old mark it could see.
- With no sheet in view the wooden desk was accepted as a page; pieces of it were saved as highlights.
- Page numbers reached 18 in one session with two real sheets.
- Replaying that session's pictures through the new code: one full read per sheet, two pages, no
  repeats, no false highlights. Real camera pictures stay out of the repo (it is public).
- Yoon Woo's `.env` now has `GLYPH_MAX_CALLS_PER_MIN=4` and `GLYPH_COOLDOWN_SECONDS=6`.
- A Google AI Pro subscription does not add Gemini API allowance; a key stays on the free tier until
  billing is linked to its project. A monthly spend cap can be set per project in AI Studio.

**Not verified**
- Live Gemini with the pink close-up and the new instructions. No call could be made from the
  sandbox. Make one live run before trusting any of it.
- The real camera with these changes. `docs/camera-test-checklist.md` has a new section 1b for it.
- Windows.

**Changed plans**
- Skylar now does the business side (logo, colors, mark meanings, story). Yoon Woo writes all the
  code, the stuck nudge included. The Nov 18 note below about `stuck-nudge` applies to whoever builds it.
- On hold until Yoon Woo asks: writer / annotation mode, a checkmark that checks answers.
- The name is undecided (Glyf, Glyff, Gliff floated).

**Need from the other side**
- Nothing open for Skylar's Claude.

---

## 2026-11-18 (early morning), Yoon Woo's Claude

Yoon Woo asked for everything that was shaky in the Nov 17 camera tests to be fixed or reinforced
overnight. No camera and no Gemini calls were available, so the work was done against camera pictures
saved during those tests (`sessions/<ts>/camera/`), replayed through the engine with camera noise
added. All of it is on `main` and `camera-test`. 44 checks pass (12 + 9 + 23).

**Done**
- **Sheet outline:** corners now come from a line fitted to each side, and a sheet that reaches one
  or two edges of the picture is accepted if it still has a sheet's proportions. The outline is
  held fixed once a page is accepted and moves only when four frames in a row agree.
- **New ink:** judged by how much darker a spot is than the remembered page nearby
  (`ink_strength`, `steady_strength`, `new_ink` in `glyph/page.py`), using the middle of the last
  three frames. Replaces the yes/no ink mask that let faint pencil through as "new ink".
- **Sliding sheet:** when the outline moves, the remembered page is lined up with the page as
  flattened now (`slip_between`, `Engine._line_up`). A mark drawn while the paper slid is still read.
- **Shadows:** no longer count as something lying on the sheet (`cover_mask` now also looks at color).
- **Requests:** a model over its usage limit rests for a minute or more; a slow model is not asked
  twice in one read; only "busy" earns a second try; a blank or dark view and a sheet already read
  are not read in full again. `timings.jsonl` rows have a `tried` list.
- **Model order:** `gemini-3.5-flash-lite` first (it answered full pages in 1 to 6 s on Nov 17 when
  the `-latest` names timed out). Thinking off by default.
- **Start-up:** `--camera auto` is the default and picks the camera that sees a sheet; it waits and
  explains how to connect the phone if only the computer's camera is there. `start.sh` installs
  libraries only when `requirements.txt` changed, so a restart needs no internet. Mac launcher:
  `Start Glyph.command`.
- **Pages:** telling one sheet from another now compares word shapes piece by piece. The old way
  called two pages of the same reading the same sheet.
- **Speed:** one pass over a 1080p frame went from about 100 ms to about 50 ms here.
- Docs: README, `docs/camera-test-checklist.md`, lessons in `docs/event-day-plan.md`, status in `CLAUDE.md`.

**Found**
- Yoon Woo's free Gemini key ran out on Nov 17 after a few dozen reads. Plan: billing on for demo day.
- None of the checks call Gemini. The 8 s timeout bug on Nov 17 passed every check and broke every
  live call. After any change to `glyph/brain.py`, make one live call.
- Run the three suites one after another. Run together they starve each other and fail on timing.
- Not verified on a real camera or a live model: everything in this entry.

**Need from the other side (Skylar)**
- `[done, Nov 19: Yoon Woo builds the nudge now; the pointers still hold]` `glyph/engine.py` changed a lot inside `_tick`. Merge `main` into `stuck-nudge` before
  going further and expect conflicts there. For the nudge: "new ink" is `fresh_px > 0` after the
  `steady_ink` / `outline_unsure` check; "view blocked" is `covered`, the early return for a sheet
  partly out of view, or `self.baseline is None`. Tests that fake time can still call
  `_tick(frame, now)`. In `tests/test_pipeline.py`, `FAST` now has `read_first_page=False`.
- `[open]` On Windows: do all three suites pass (one after another), and does `bash start.sh --demo`
  start in Git Bash? `--camera auto` and `start.bat` are untested there.
- `[open]` If your key has allowance: run `bash start.sh --demo` once without `--mock` and note in
  this file which model answered, how long it took, and whether the terminal printed
  "refused the request with the thinking setting".
- Still on hold, do not start: writer mode / annotation mode.

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
- **Bug I introduced and fixed:** an 8 s timeout made every live call fail (Gemini's minimum deadline
  is 10 s). It is 10 s now and cannot be set lower. If you pulled `8f7bcdc` to `090f814`, pull again.
- When no clean sheet outline is found, a camera picture is saved to `sessions/<ts>/camera/` every
  15 s (12 at most), for tuning detection.
- Third camera test (0.5x lens, sheet fully in view, wooden desk):
  - **Sheet was never found**, so the page was never flattened and only whole-frame reads happened.
    Cause: brightness alone cannot separate paper from a glossy wooden desk with shadows across the
    sheet. `find_page` in `glyph/page.py` now looks by color first (low saturation, not dark) and
    falls back to brightness. Checked against four saved pictures from that test: all four flatten.
  - **Full-page reads took 12 to 26 s** (two models timed out first). Thinking is now off by default
    (`GLYPH_THINKING_BUDGET=0`; a model that refuses the setting is asked again without it).
  - **Study guide by page** now also puts "Words you looked up" and "Where you asked for help" under
    their page. Each answer event carries `meta.page`.
- 36 checks pass.

**Found**
- The flicker fix and the out-of-view hold are tested on simulated frames only, not the real camera yet.
- Page numbers in `HighlightStore` start at 2, not 1 (two resets at startup). Harmless: the guide
  renumbers pages 1, 2, 3 in order.

**Need from the other side (Skylar)**
- `[superseded by the Nov 18 entry]` Merge `main` into `stuck-nudge`.
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
- `[superseded by the Nov 18 entry]` Merge `main` into `stuck-nudge`.
- `[open]` On Windows, run all three suites and note the result here:
  `python -m tests.test_pipeline`, `python -m tests.test_rough`, `python -m tests.test_tools`.
  The highlight fix and the Git Bash path in `start.sh` were not tested on Windows. Say if
  `bash start.sh --demo` runs for you as is.
- `[open]` Run one live call and note which model answered and how long it took. The new fallback
  names were not verified with a real call.
