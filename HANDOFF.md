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
- Added `start.bat` for Windows.
- New docs: `docs/camera-test-checklist.md`, `docs/event-day-plan.md`.

**Found**
- HackwithBay 4.0 lists no rule about pre-built code. Build time is short: 11:00 to 15:30 with lunch
  in the middle. Theme: "Thoughtful Agents for Productivity". Details in `docs/event-day-plan.md`.

**Need from the other side (Skylar)**
- `[open]` Merge `main` into `stuck-nudge` (`git fetch origin && git merge origin/main`). Expect
  changes in `glyph/engine.py`; keep both sides. Do not edit `glyph/static/index.html`.
- `[open]` On Windows, run all three suites and note the result here:
  `python -m tests.test_pipeline`, `python -m tests.test_rough`, `python -m tests.test_tools`.
  The highlight fix and `start.bat` were not tested on Windows.
- `[open]` Run one live call and note which model answered and how long it took. The new fallback
  names were not verified with a real call.
