# Camera test checklist

About 15 minutes. The goal is to answer the open questions in `CLAUDE.md`, so write numbers down.
Put results in `HANDOFF.md` when done.

## Setup

- [ ] Phone on the gooseneck, camera pointing straight down, about 35 to 45 cm above the desk.
- [ ] Phone unlocked, Wi-Fi and Bluetooth on, same Apple ID as the Mac (Continuity Camera needs all three).
      A cable between phone and Mac is steadier than wireless.
- [ ] White sheet on a **darker** surface, lamp on, no hard shadow from the phone across the page.
- [ ] Start: double-click **Start Glyph camera test** on the Desktop (or `bash start.sh --list-cameras`,
      then `bash start.sh --camera <n>`).

## 1. Does it see the page? (2 min)

- [ ] **Camera** view shows a green outline around the sheet.
- [ ] **Page** view shows the sheet flat and upright. Sideways: click **Rotate**.
- [ ] Nudge the sheet a little. It should not trigger an answer.
- [ ] Tap the gooseneck. Note how long the picture takes to settle: ____ s

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

- [ ] Did any hint give away the answer? It must not.
- [ ] Which model answered? (shown with the "answered in N s" line, and in `sessions/<ts>/timings.jsonl`)

## 3. Highlights (3 min)

- [ ] One line in each highlighter color you own. Each should appear once under the right color.
- [ ] Rest your hand over half of a highlight, then lift it. It must not be saved a second time.
- [ ] Tilt the lamp so there is glare on a highlight. Known weak spot: note what happens.
- [ ] **End session** builds a study guide with the highlighted text readable.

## 4. If something is off (4 min)

- [ ] Open http://127.0.0.1:8765/tune. Ink missed or noisy: move the ink slider. Wrong highlight
      colors: click the color on the page to pick it. Press **Save**.
- [ ] Re-run the one thing that failed.

## Write down

- Seconds per answer (best, typical, worst): ____ / ____ / ____
- Marks that were missed or misread:
- Highlighter colors that failed, and under what light:
- Anything that needed the tuning page, and the values that fixed it:
- Did Continuity Camera drop or freeze? How often?
