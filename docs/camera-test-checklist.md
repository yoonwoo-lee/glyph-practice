# Camera test checklist

About 15 minutes. The goal is to answer the open questions in `CLAUDE.md`, so write numbers down.
Put results in `HANDOFF.md` when done.

## Setup

- [ ] Phone on the gooseneck, camera pointing straight down. **Lock the phone** (screen off) and keep
      it still. Wi-Fi and Bluetooth on, same Apple ID as the Mac. A cable to the Mac is steadier
      than wireless and cuts the lag.
- [ ] White sheet on the desk, lamp on. Nothing white or cream (pencil case, another sheet) touching
      the edge of the sheet.
- [ ] Start: double-click **Start Glyph.command** in the Glyph folder (or `bash start.sh`). It picks the
      camera that sees the sheet, and waits with instructions if the phone is not connected.
- [ ] Switch the phone to **0.5x** if the whole sheet does not fit: Video (camera) icon in the Mac's
      menu bar, Center Stage off, 0.5x. All four corners in view, some desk around them, text sharp.
      Check again after any reconnect: the lens setting can reset.
- [ ] Gemini key has allowance left. A free key runs out after a few dozen reads in a day.

## 1. Does it see the page? (2 min)

- [ ] **Camera** view shows a white outline around the sheet with a pink dot on each corner, and it
      holds still.
- [ ] **Page** view shows the sheet flat with blue corner brackets, and the readout says Sheet:
      Locked. Sideways or upside down: click **Rotate** until upright.
- [ ] The sheet is read once in full within a couple of seconds of settling. Seconds it took: ____
- [ ] Nudge the sheet a little. It should not trigger an answer, and the outline should follow it.
- [ ] Wave a hand above the sheet so its shadow crosses the page. No dashed box, no "Reading".
- [ ] Slide the sheet half out of view. The page holds and asks you to slide it back.
- [ ] Tap the gooseneck. Note how long the picture takes to settle: ____ s
- [ ] Take the sheet away. Within about 2 s it should say "No sheet in view", read nothing and save
      no highlights. Rest a sleeve or a hoodie next to the sheet: the outline should stay on the paper.

## 1b. The Nov 19 problems (4 min)

These four went wrong on Nov 19 and were fixed without a camera. Check each one first.

| Try | What should happen | What happened |
|---|---|---|
| Draw one spark, then leave the sheet alone for a minute | One hint, and no more answers | |
| Write a few more lines under it, no marks | Still no new answer | |
| Printed page (the speech): underline one word | A definition of that word | |
| Same page: underline a second word on another line | A definition of the second word only | |
| Take the sheet out, wait, put it back (also try upside down) | Same page number, not read again | |
| Bring in a second sheet, then the first again | Page 2, then back to Page 1 | |

- [ ] If a sheet does get a new number: click the number it should have had, then **Yes, same sheet**.
- [ ] After any wrong answer, keep `sessions/<latest>/looks/`. The close-up there should show the new
      stroke in pink and the rest of the page readable.

## 2. Marks (6 min)

Write a real physics problem with some working first. Lift your hand off the sheet after each mark.

| Try | Worked? | Seconds to answer | Notes |
|---|---|---|---|
| Spark next to the problem (hint) | | | |
| Second spark on the same problem (hint should get more specific) | | | |
| Underline one word (definition) | | | |
| Circled question mark (explanation) | | | |
| Ordinary writing, no mark (should stay quiet) | | | |
| Mark drawn with your hand left on the page (should wait) | | | |
| Mark drawn while the sheet slides a little under your hand | | | |

- [ ] Did any hint give away the answer? It must not.
- [ ] Which model answered? (shown with the "answered in N s" line, and in `sessions/<ts>/timings.jsonl`)

## 3. Highlights (3 min)

- [ ] One line in each highlighter color you own. Each should appear once under the right color.
- [ ] Rest your hand over half of a highlight, then lift it. It must not be saved a second time.
- [ ] Tilt the lamp so there is glare on a highlight. Known weak spot: note what happens.
- [ ] Swap to a second sheet, highlight and ask something there, swap back to the first.
- [ ] **End session** builds a study guide with the highlighted text readable, a Page 1 and a Page 2
      section, and the first sheet not counted twice.

## 3b. Added Nov 19 evening (2 min, no requests spent)

- [ ] Switch to **Camera** view and draw a spark: a pink frame with "Reading" sits on the spark on the
      desk picture, not beside it. Highlights are outlined there too.
- [ ] Stop writing for 90 seconds with the sheet in view: exactly one "Keep going" card appears, and
      no second one until you write again.

## 3c. Added Nov 20 evening: the four things that went wrong that afternoon (5 min, about 5 requests)

- [ ] Put the sheet down sideways, click **Rotate**: the page number stays the same.
- [ ] Draw one spark and wait 20 seconds: one hint, not two.
- [ ] Underline a short word in small print, close under the letters ("ball"), and nothing else: its
      definition comes within about 10 seconds.
- [ ] Highlight one line with the green highlighter: a green row appears under "Saved for your study
      guide" on the right, and the line is outlined in green on the page.
- [ ] Click **End session**: the study guide lists the highlight and the words you looked up.

## 4. If something is off (4 min)

- [ ] Open http://127.0.0.1:8765/tune. Ink missed or noisy: move the ink slider. Wrong highlight
      colors: click the color on the page to pick it. Press **Save**.
- [ ] Re-run the one thing that failed.

## Write down

- Seconds per answer (best, typical, worst): ____ / ____ / ____
- Which model answered, and which ones failed first (`tried` in `timings.jsonl`):
- Marks that were missed or misread:
- Highlighter colors that failed, and under what light:
- Anything that needed the tuning page, and the values that fixed it:
- Did Continuity Camera drop or freeze? How often?
