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
cd ~/Desktop/glyph-practice
bash start.sh --demo
```

The first run takes about a minute to set up. `--demo` needs no camera: it plays a simulated worksheet that
gets a spark, an underline and two highlights, so you can see the whole thing work. A browser tab opens at
http://127.0.0.1:8765. Press Ctrl+C in Terminal to stop.

`start.sh` copies your Gemini key from the `talking-menu` project the first time. Without a key, Glyph runs
with fake answers so everything else can still be tested.

## Test with your real camera

1. Mount the iPhone above the desk, camera pointing straight down, lamp on. Put a sheet of paper on a
   **darker** surface so its edges stand out.
2. Find the phone's camera number:
   ```
   bash start.sh --list-cameras
   ```
   macOS asks to let Terminal use the camera the first time. Allow it and run the command again.
   Open the photos in `camera_check/` to see which number shows your desk.
3. Start Glyph with that number: `bash start.sh --camera 1`
4. In the browser, click **Camera**. The sheet should have a green outline. Click **Page**: you should see
   the sheet flat and upright. If the text is sideways, click **Rotate**.
5. Write a physics problem, then try each mark from the table above. **Lift your hand off the sheet** after
   drawing. A blue box shows what Glyph is reading; the answer appears in the feed a few seconds later.
6. Highlight a few lines, then click **End session: build study guide**.

Things worth writing down while you test: how long each answer takes, which symbols get missed, and how the
highlight colors behave under your lamp.

## If something is off

| What you see | What to try |
|---|---|
| "no sheet outline: using whole picture" | Darker surface under the paper, or move the camera so all four edges show. It still works without the outline, only less precisely. |
| A symbol gets no answer | Draw it bigger and with a thicker pen. Look in `sessions/<latest>/looks/` to see exactly what was sent to the model. Click **Look now** to force a full read. |
| Highlights are not picked up | Add light. Then adjust the color ranges in `glyph/config.py` (`HIGHLIGHT_HSV`). |
| Glyph reacts to nothing, or to everything | `GLYPH_INK_C` in `.env`: lower catches fainter ink, higher ignores more. |
| "Paused: reached the calls-per-minute limit" | Raise `GLYPH_MAX_CALLS_PER_MIN` in `.env` if your key allows it. |
| A red outline on the page view | Glyph thinks something is lying on the sheet there and ignores ink next to it. |

## Change what the symbols do

Edit `symbols.json`. Each symbol has a name, a description of what it looks like, and an action (`hint`,
`explain` or `define`). Highlight colors map to study guide sections there too.

## How it works

1. `glyph/camera.py` reads frames (camera, video file, photos, or the demo).
2. `glyph/page.py` finds the sheet, flattens it, and finds dark ink.
3. `glyph/engine.py` compares the ink with what was there before. New ink plus a still picture means
   "look". Only the new ink is sent at full contrast, so old symbols are not answered twice.
4. `glyph/highlights.py` finds highlighter by color on the Mac, with no model call.
5. `glyph/brain.py` sends the page to the vision model with the symbol legend and gets back a hint,
   definition or explanation. Swapping to another model means changing one method there.
6. `glyph/app.py` and `glyph/static/index.html` are the web page.

Every session saves its feed, highlight photos, study guide and model inputs under `sessions/`.

## Checks

```
source venv/bin/activate
python -m tests.test_pipeline
```

Twelve checks run on simulated camera frames: the full flow, a half-drawn symbol, a hand on the page,
a nudged sheet, a new sheet, model errors.

Not yet tested, because it needs your desk: the real camera, real lighting, real handwriting, and live
calls to Gemini.
