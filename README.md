# Glyph (practice build)

A study tutor that watches your paper through a camera. You never type: you draw.

| You do this on paper | Glyph does this |
|---|---|
| Draw a **spark** (a starburst, like an asterisk) next to a problem | Gives one hint. Never the answer. |
| **Underline** a word | Defines it, in the context of the page |
| **Highlight** in yellow, green, pink or blue | Saves it. "End session" turns all highlights into a study guide |
| Draw a **circled question mark** next to a passage | Explains it in plain language |

This is the practice version for learning what is hard. Rebuild from scratch, in a new repo, at the hackathon.

## Start it

```
bash start.sh --demo        # works in Git Bash on Windows too; Command Prompt: start.bat --demo
```

The first run takes about a minute to set up; after that it starts in a second and needs no internet
to start. `--demo` needs no camera: it plays a simulated worksheet that gets a spark, an underline and
two highlights, so you can see the whole thing work. A browser tab opens at http://127.0.0.1:8765.
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
4. In the browser, click **Camera**. The sheet should have a yellow outline. Click **Page**: you should
   see the sheet flat. If the text is sideways or upside down, click **Rotate** until it is upright.
5. A new sheet is read once in full as soon as it is steady, so marks already on it get answered.
   Then try each mark from the table above. **Lift your hand off the sheet** after drawing. A blue
   box shows what Glyph is reading; the answer appears a few seconds later.
6. Highlight a few lines, then click **End session: build study guide**. With more than one sheet, the
   guide has a section per page.

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
| The page is not flattened (no yellow outline in the Camera view) | All four corners must be in the picture: raise the phone or use its 0.5x lens. Keep things that are white or cream (a pencil case, another sheet) from touching the sheet's edge. Pictures from moments when no sheet was found are saved in `sessions/<latest>/camera/`. |
| "Part of the sheet is outside the camera's view" | Slide the sheet back. Glyph holds the last good view until it is whole again. |
| "Gemini's usage limit for this key is used up for now" | Free keys get a small allowance per minute and per day. Glyph waits and tries again by itself. Turning on billing for the key in Google AI Studio lifts the limit. |
| The launcher finds only one camera | The iPhone is not connected as a camera: lock it, keep it still, Wi-Fi and Bluetooth on, or plug it in. Check that it appears in Photo Booth's Camera menu. |
| A symbol gets no answer | Draw it bigger and with a thicker pen. Look in `sessions/<latest>/looks/` to see exactly what was sent to the model. Click **Look now** to force a full read. |
| Highlights are not picked up | Open **Tune**, press "Pick from page" for that color and click the stroke. Glare (a lamp reflecting straight off the paper) washes color out: move the lamp. |
| Glyph reacts to nothing, or to everything | Open **Tune** and move "Ink sensitivity": lower catches fainter ink, higher ignores more. |
| "Paused: reached the calls-per-minute limit" | Raise `GLYPH_MAX_CALLS_PER_MIN` in `.env` if your key allows it. |
| A red outline on the page view | Glyph thinks something is lying on the sheet there (a hand, a pen) and ignores ink next to it. A shadow alone does not count. |

## Change what the symbols do

Edit `symbols.json`. Each symbol has a name, a description of what it looks like, and an action (`hint`,
`explain` or `define`). Highlight colors map to study guide sections there too.

## How it works

1. `glyph/camera.py` reads frames (camera, video file, photos, or the demo).
2. `glyph/page.py` finds the sheet (by color, then by brightness), flattens it, and measures how dark
   the ink is at every spot.
3. `glyph/engine.py` compares the ink with what it remembers of the page. Ink that is clearly darker
   than anything that was there before, in a still picture, means "look". Only the new ink is sent
   at full contrast, so old symbols are not answered twice. The sheet may slide while you write:
   the remembered page is lined up with it again.
4. `glyph/highlights.py` finds highlighter by color on the Mac, with no model call.
5. `glyph/brain.py` sends the page to the vision model with the symbol legend and gets back a hint,
   definition or explanation. Swapping to another model means changing one method there.
6. `glyph/app.py` and `glyph/static/index.html` are the web page.

Every session saves its feed, highlight photos, study guide and model inputs under `sessions/`.

## Checks

```
source venv/bin/activate
python -m tests.test_pipeline
python -m tests.test_rough
python -m tests.test_tools
```

- `test_pipeline` (12): the full flow, a half-drawn symbol, a hand on the page, a nudged sheet, a new
  sheet, model errors.
- `test_rough` (9): the same flow on a worse camera: lamp on one side, glare, soft focus, a dim room,
  a tilted camera, sensor grain and flicker.
- `test_tools` (23): model fallbacks and usage limits, choosing the camera, a wooden desk with a
  shadow, a sliding sheet, shadows, blank or dark views, study guide by page, timing log, the tuning page.

Run them one after another, not at the same time: they are timed like a live camera, and a busy
computer makes them miss their cues.

Known limit: a strong glare patch directly on a highlight splits or hides it.

None of these call Gemini. What only a real run can show: live model speed and answers, and the real
camera in real light.
