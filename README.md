# Glyph (practice build)

A study tutor that watches your paper through a camera. You never type: you draw.

| You do this on paper | Glyph does this |
|---|---|
| Draw a **spark** (a starburst, like an asterisk) next to a problem | Gives one hint. Never the answer. |
| **Underline** a word | Defines it, in the context of the page |
| **Highlight** in yellow, green, pink or blue | Saves it. "End session" turns all highlights into a study guide |
| Draw a **circled question mark** next to a passage | Explains it in plain language |
| Draw a **check mark** next to your answer | Checks it: "Looks right" or "Not yet" and which step to look at again. Never the answer. |
| Draw a **target** (a bullseye) next to a problem | Gives one new problem of the same kind |

There are two modes, switched with the **Student | Editor** button at the top left of the page. The
marks above are student mode, for solving problems. Editor mode is for reading and writing: it keeps
the underline, the highlights and the circled question mark, and adds these.

| In editor mode | Glyph does this |
|---|---|
| Draw a **box** around a word | Finds every other place the word appears and outlines them on the page |
| Draw a **circle** around a word | Gives synonyms that fit the sentence |
| Draw a **line down the margin** beside a passage | Summarizes that passage |

Switching mode reads nothing and costs no request. `GLYPH_MODE=editor` in `.env` starts in editor mode.
Which marks each mode uses is set in `symbols.json`.

You write with any pen or pencil. Glyph works out which strokes are new by itself.

If you stop writing for a while (90 seconds), Glyph shows one "keep going" card. It never gives an
answer and uses no model call. `GLYPH_STUCK_SECONDS` in `.env` changes the wait; `0` turns it off.

This is the practice version for learning what is hard. Rebuild from scratch, in a new repo, at the hackathon.

The name shown in the app and used in the answers is one setting: put `GLYPH_NAME=Gliff` (or any
name) in `.env` and start again.

## Start it

```
bash start.sh --demo        # works in Git Bash on Windows too; Command Prompt: start.bat --demo
```

The first run takes about a minute to set up; after that it starts in a second and needs no internet
to start. `--demo` needs no camera: it plays a simulated worksheet that gets a spark, an underline,
two highlights, a checked answer and a target, so you can see the whole thing work. Click **Editor** and
it plays a page of reading instead. With a Gemini key in `.env`, add `--mock` to keep the demo from
spending requests: `bash start.sh --demo --mock`. A browser tab opens at http://127.0.0.1:8765.
Press Ctrl+C in Terminal to stop.

On a Mac you can also double-click **Start Glyph.command** in this folder. It starts Glyph with the
camera and keeps the Mac awake while it runs.

`start.sh` copies your Gemini key from the `talking-menu` project the first time. Without a key, Glyph runs
with fake answers so everything else can still be tested.

## Test with your real camera

1. Mount the iPhone above the desk, camera pointing straight down, lamp on. **Lock the phone** (screen
   off) and keep it still: that is when a Mac offers it as a camera. A cable to the Mac is steadier
   than wireless. Any desk works, as long as the paper is clearly lighter or less colorful than it.
2. Start Glyph: double-click **Start Glyph.command**, or run `bash start.sh`. It picks the camera that
   sees a sheet of paper. If only the computer's own camera is connected, it waits and tells you how
   to get the phone to show up. macOS asks to let Terminal use the camera the first time: allow it
   and start again.
   (To choose yourself: `bash start.sh --list-cameras` saves a photo from each camera to
   `camera_check/`, then `bash start.sh --camera 1`.)
3. Get the whole sheet in the picture. If the mount is not tall enough, use the phone's **0.5x lens**:
   click the Video (camera) icon in the Mac's menu bar while Glyph runs, turn Center Stage off, and
   pick 0.5x. All four corners should show, with some desk around them, and the text should be sharp.
4. In the browser, click **Camera**. The sheet should have a white outline with a pink dot on each
   corner. Click **Page**: you should see the sheet flat, with blue corner brackets once it is locked
   on. If the text is sideways or upside down, click **Rotate** until it is upright
   (Glyph remembers the turn for the next start).
5. A new sheet is read once in full as soon as it is steady, so marks already on it get answered.
   Then try each mark from the table above. **Lift your hand off the sheet** after drawing. A pink
   frame labelled "Reading" closes on the mark and a pink bar sweeps the page; the frame turns blue
   and says "Answered" when the answer arrives. Each mark is answered once.
6. Highlight a few lines, then click **End session**. With more than one sheet, the guide has a
   section per page.

The row under the page shows what Glyph measures: whether the sheet is locked on, which page this is,
how much of the page is ink, how much new ink it sees right now, pictures analysed per second, and
how long the last answer took.

## Pages

Sheets are numbered 1, 2, 3 in the order Glyph first sees them, and the numbers are shown at the top
right. Take a sheet away and bring it back, even upside down, and it keeps its number and is not
read again. A sheet with almost nothing on it cannot be told from another blank one.

If Glyph gives a sheet a new number by mistake, click the number it should have had and choose
**Yes, same sheet**. The answers and highlights move over to that number.

Things worth writing down while you test: how long each answer takes, which symbols get missed, and how the
highlight colors behave under your lamp. `docs/camera-test-checklist.md` has a full list.

## Tune it to your desk

Open http://127.0.0.1:8765/tune while Glyph is running (or click **Tune**).

- **Ink** view: your writing should be painted dark blue and blank paper should stay clean. Move
  "Ink sensitivity" until that is true.
- **Highlighter** view: draw a stroke with each highlighter, press **Pick from page** for that color,
  then click the stroke. Glyph sets the color range from that spot.
- **Hand and objects** view: red shows what Glyph treats as covering the page.
- **Save to .env** keeps the settings for next time. Your key line is left alone.

To tune from a photo instead of the live camera: `bash start.sh --source photo.jpg`, then open `/tune`.

## How fast is it?

- Every look is logged to `sessions/<latest>/timings.jsonl`: `wait_s` (ink appeared → picture sent),
  `model_s` (time inside the model call), `total_s` (ink appeared → answer), `model` (which one
  answered) and `tried` (models that failed first, and why). The app shows "answered in N s" on
  each answer.
- Models are tried fastest first. One that times out is tried last from then on, one that is over its
  usage limit is left alone for a while, and one the key cannot use is dropped. `GLYPH_MODEL` in
  `.env` puts a model of your choice first.
- Compare models without the camera:
  ```
  source venv/bin/activate
  python bench.py
  ```
  It times each Gemini model (with thinking off and on) on the demo page and writes `bench_results.md`.
  It spends real requests: on a free key use `python bench.py --runs 1`.

## If something is off

| What you see | What to try |
|---|---|
| The page is not flattened (no white outline in the Camera view) | All four corners must be in the picture: raise the phone or use its 0.5x lens. Keep things that are white or cream (a pencil case, another sheet) from touching the sheet's edge. Pictures from moments when no sheet was found are saved in `sessions/<latest>/camera/`. |
| "Part of the sheet is outside the camera's view" | Slide the sheet back. Glyph holds the last good view until it is whole again. |
| "Gemini's usage limit for this key is used up for now" | Free keys get a small allowance per minute and per day. Glyph waits and tries again by itself. Turning on billing for the key in Google AI Studio lifts the limit. |
| The launcher finds only one camera | The iPhone is not connected as a camera: lock it, keep it still, Wi-Fi and Bluetooth on, or plug it in. Check that it appears in Photo Booth's Camera menu. |
| A symbol gets no answer | Draw it bigger and with a thicker pen. Look in `sessions/<latest>/looks/` to see exactly what was sent to the model. Click **Read page now** to force a full read. |
| Highlights are not picked up | Open **Tune**, press "Pick from page" for that color and click the stroke. Glare (a lamp reflecting straight off the paper) washes color out: move the lamp. |
| Glyph reacts to nothing, or to everything | Open **Tune** and move "Ink sensitivity": lower catches fainter ink, higher ignores more. |
| "Paused: reached the calls-per-minute limit" | Raise `GLYPH_MAX_CALLS_PER_MIN` in `.env` if your key allows it. |
| A dashed dark box on the page view | Glyph thinks something is lying on the sheet there (a hand, a pen) and ignores ink next to it. A shadow alone does not count. |
| "No sheet in view" | Glyph sees the desk and no paper. It reads nothing and saves no highlights until a sheet is back. |
| The same mark is answered again | It should not be. Note which mark and what was on the page, and keep `sessions/<latest>/looks/`: it shows exactly what was sent. |
| An underline gets the wrong word | Draw the line right under the word, about as wide as the word, in one stroke. On small print, underline one word at a time. |
| A sheet you already showed gets a new number | Click the number it should have had, then **Yes, same sheet**. |

## Change what the symbols do

Edit `symbols.json`. Each symbol has a name, a description of what it looks like, and an action (`hint`,
`explain` or `define`). Highlight colors map to study guide sections there too.

## How it works

1. `glyph/camera.py` reads frames (camera, video file, photos, or the demo).
2. `glyph/page.py` finds the sheet (by color, then by brightness), flattens it, and measures how dark
   the ink is at every spot.
3. `glyph/engine.py` compares the ink with what it remembers of the page. Ink that is clearly darker
   than anything that was there before, in a still picture, means "look". In the close-up sent to
   the model the new strokes are recolored bright pink and the model is told to answer only those,
   so old symbols are not answered twice. (That pink is inside the picture the model gets. It has
   nothing to do with the pen you use.) The sheet may slide while you write: the remembered page is
   lined up with it again, and nothing is sent until the two match.
4. `glyph/highlights.py` finds highlighter by color on the Mac, with no model call.
5. `glyph/brain.py` sends the page to the vision model with the symbol legend and gets back a hint,
   definition or explanation. Swapping to another model means changing one method there.
6. `glyph/app.py` and `glyph/static/index.html` are the web page. The frames, brackets and readouts
   are drawn in the browser from numbers the engine reports; the pictures themselves are left clean.

Every session saves its feed, highlight photos, study guide and model inputs under `sessions/`.

## Checks

```
source venv/bin/activate
python -m tests.test_pipeline
python -m tests.test_rough
python -m tests.test_tools
```

- `test_pipeline` (17): the full flow, a half-drawn symbol, a hand on the page, a nudged sheet, a new
  sheet, model errors, the "keep going" card, the boxes on the camera view.
- `test_rough` (9): the same flow on a worse camera: lamp on one side, glare, soft focus, a dim room,
  a tilted camera, sensor grain and flicker.
- `test_tools` (57): model fallbacks and usage limits, choosing the camera, a wooden desk with a
  shadow, gray clothing beside the sheet, a bare desk, a sliding or turned sheet, shadows, blank or
  dark views, a mark answered once and a second mark answered again, the check mark (verdict, a
  second try, a check drawn before the sheet was taken in, a sheet covered in ticks), a sheet in a
  warm shadow, the close picture of the mark on the card, the two modes (each mode's marks, switching, the editor
  demo, found places, no "keep going" card in editor mode), page numbers, study guide by
  page, timing log, the tuning page, the name setting.

Run them one after another, not at the same time: they are timed like a live camera, and a busy
computer makes them miss their cues.

Known limit: a strong glare patch directly on a highlight splits or hides it.

None of these call Gemini. What only a real run can show: live model speed and answers, and the real
camera in real light.
