# Event-day plan: HackwithBay 4.0

Tue Nov 24, 2026, AWS Builder Loft, San Francisco. A proposal for Yoon Woo and Skylar to edit.
Rebuild from scratch in a new repo; this file is the plan and the lessons, not code to copy.

## What the event page says (checked Nov 17)

Source: the Luma event page, https://luma.com/x05cmrqh

- Theme: **"Thoughtful Agents for Productivity"**.
- 10:00 opening, **11:00 hacking starts**, 12:00 to 13:00 lunch, **15:30 submission deadline**,
  16:00 to 16:40 final presentations by the **top 5 teams**, 17:00 networking.
- **No rule about pre-built code** is listed. No team size, judging criteria, sponsor tools or
  submission format either. Ask the organizers at the opening: "Can we reuse our own earlier code, and
  what do we submit?" Rebuilding stays the plan either way.

So there are about 3.5 working hours, 4.5 if you work through lunch. That is the main constraint.

## Pitch in one line

Glyph is a study agent you never type to: draw a mark on paper, get a hint, not the answer.
"Thoughtful" is the hint-first rule. "Productivity" is staying on paper and off the screen.

## What to build, in order

Stop wherever the clock says stop. Each step ends with something you can demo.

| Clock | Goal | Done when |
|---|---|---|
| 11:00 to 11:30 | Camera frame in, sheet found and flattened, shown in a browser page | You see the flat page live |
| 11:30 to 12:15 | **Spark gives a hint**, end to end, on the real camera | Draw a spark, read a hint |
| 12:15 to 13:00 | Eat. One person fixes whatever is shaky | |
| 13:00 to 13:45 | Underline gives a definition. Only new ink is sent | Second mark does not re-answer the first |
| 13:45 to 14:30 | Highlights by color, then a study guide button | Guide shows two colors |
| 14:30 to 15:00 | Make the right side look good: one big answer card | A stranger understands the screen |
| 15:00 to 15:30 | **Freeze.** Rehearse the demo twice, record a backup video, submit | Submitted by 15:20 |

Cut first if behind: study guide, then underline. Never cut the 15:00 freeze.
Stretch only if ahead at 14:30: stuck nudge (no model call, quick to add).

## Who does what (agreed Nov 18)

- **Yoon Woo:** all the code. He has the phone and the mount.
- **Skylar:** the business side: logo, colors, what each mark means, who it is for, the demo story,
  the slides and the submission text. During the build he is the test student at the desk and keeps
  the clock.
- With one person coding, the order in the table above matters more: get spark → hint working on the
  real camera before anything else, and keep the model call simple.

## Lessons from the practice build

Everything here cost real time between Nov 17 and 19. Read it before writing the first line on the day.

Model
- Ask for the `v1beta` API explicitly. Newer `google-genai` versions default to `v1`, where the
  `-latest` model names return 404.
- Gemini rejects a deadline under 10 s. Set the timeout to 10 s, not lower, and turn the library's
  own retries off. Otherwise a slow model looks like a freeze.
- Turn thinking off. With it on, full-page reads ran past the timeout.
- Keep a fallback list, fastest model first. Drop a model that returns 404, rest a model that returns
  429 for a minute or more, and move a model that times out to the back. Do not ask the same model
  twice in one read unless it said "busy".
- **A free key runs out fast**: a few dozen reads used up the day's allowance, mid-test. Turn billing
  on for the key days before, set a spending cap, and run one full session on it. Bring both keys.
- Count requests. Every automatic read and every fallback model is a request. Do not read a blank
  sheet, a dark frame, or a sheet that was already read.
- Ask for JSON only, and throw away anything that is not a known action.
- On the real camera `gemini-3.5-flash-lite` answered a full page in 1 to 6 s. The tests never call
  Gemini, so they cannot catch a bad timeout or model name: make one live call after every change
  to the model code.

Camera
- A Mac only offers the iPhone as a camera when the phone is **locked and still**. Wireless drops;
  bring a cable.
- A gooseneck is not tall enough for the main lens: the sheet does not fit and the picture is out of
  focus. Use the **0.5x lens** (Video icon in the menu bar, Center Stage off). Check it after every
  reconnect.
- Do not make people type a camera number. Pick the camera that sees a sheet of paper.
- Never show the camera through the analysis loop: it runs a few times a second and looks laggy.
  Serve camera frames straight from the camera, one picture per request. A never-ending MJPEG
  stream froze when two views were swapped.
- Install libraries once, not on every start. The venue Wi-Fi may be down when you need to restart.

Seeing the page
- Brightness alone does not find white paper on a glossy wooden desk with shadows on it. Paper is the
  big area that is **not colorful and not dark**: threshold on saturation first.
- Corners found frame by frame wobble by 3 to 6 pixels. Fit a line to each side of the outline, keep
  the outline fixed once a page is accepted, and move it only when several frames agree.
- The sheet slides a few pixels every time someone writes on it. Line the remembered page up with the
  page now before comparing, or all the old ink looks new. Matching small blocks of the page and
  fitting one transform to them held up on dense print; one shift for the whole page did not.
  **Send nothing until the two line up.** On Nov 19 shifted print was sent as "new ink" again and again.
- Judge new ink by **how much darker** a spot is than the remembered page nearby, not by a yes/no ink
  mask. Faint pencil crosses a yes/no line at random and gets sent as "new ink".
- Use the middle of the last three frames, so one noisy frame cannot create or erase ink.
- A shadow is not an object. A shadow darkens the paper and keeps its color; a hand changes the
  color. Shadows pass over the page constantly while someone writes.
- Show the model which strokes are new by **recoloring them** (hot pink) and say "answer only the
  pink strokes". Fading the old ink instead left it little to read around an underline on print.
- **One answer per mark.** Remember (action, target) for each page and drop a repeat before it
  reaches the screen. The model will happily answer the same spark on every read.
- Drop specks and anything hugging the sheet's edge before calling it new ink: fingertips and the
  desk showing at the edge were being sent to the model.
- Decide "is there paper here at all?" before anything else. With no sheet in view the wooden desk
  was read as a page and pieces of it were saved as highlights.
- Clothing beside the sheet (a gray hoodie sleeve) is as pale and colorless as paper. Check that each
  side of the outline is a real paper edge and that the corners are roughly square.
- Wait for the picture to hold still (about 1 s) before reading. Ignore ink next to a hand.
- A sheet partly outside the picture flattens into a skewed close-up. Hold the last good view and
  say so.
- To tell one sheet from another, compare the shapes of the words piece by piece. Two pages of the
  same reading have their lines in the same places. Compare upside down too. Give sheets plain
  numbers (1, 2, 3), keep the number when a sheet comes back, and let the user say "same sheet" with
  one click for the times it gets it wrong.
- Correct white balance and brightness before judging highlighter color. Detect highlights locally:
  it costs no model calls. Glare on a highlight still breaks it: angle the lamp.
- Save a camera picture whenever the sheet is not found. Those pictures are what made every fix
  above possible. Replay them with noise added to test without the camera.

Added Nov 20 and 21
- **Test on more than one desk.** A light gray table by a window passed for paper, and near the
  window it was 0.9 times as bright as the sheet. The whole camera picture was read as "the page"
  and four requests went on the ceiling, the table and a pair of jeans. Paper on gray is found by
  the step in brightness round it (the desk beside the sheet has something brighter close by), not
  by any one brightness level. Bring the dark mat anyway: it makes this problem go away.
- **Never send a picture with nothing written on it.** A ceiling or a bare table has a handful of
  dark pieces; a printed sheet has hundreds. Count them before spending a request.
- A sheet in the writer's own shadow turns beige and stops looking like paper. Allow more color when
  the bright things in view fall into two clear groups (paper and desk).
- The first look at a new sheet is not "reading a mark". Say "Taking in the page" and keep it calm,
  or it looks like a bug.
- For checking an answer, have the model solve the problem first in a field the student never sees,
  then give the verdict. No clear verdict means "could not tell", never "right".
- Show a close picture of the one mark that was answered, chosen by its shape, not everything that
  was new on the page.
- Two timeouts in a row: stop the round. Four models times 10 s is a 40 s freeze.
- Marks drawn in the first seconds, before the sheet is taken in, are easy to lose. Let the first
  look answer up to three of them.
- One mark, one meaning per mode. A box means "check this" on a problem set and "find this" in a
  reading; say which mode is on with color, so nobody has to read a label.
- People want less on the screen than you think: the legend, the tuning button, the model name and
  five of the seven readouts all came off in one afternoon.

Demo
- Have a mode that runs with no camera and no network, in case the venue Wi-Fi or the camera fails.
- Show the cut-out of the mark next to its answer. It makes the cause and effect obvious.
- Draw frames and labels in the browser on top of a clean picture, from numbers the engine sends.
  Painted into the picture they could not be animated or restyled.
- Show live numbers (sheet locked, ink on page, new ink, frame rate, seconds per answer). They make
  it look like the instrument it is, and they are the first thing to check when something is off.
- The sheet lies sideways to the camera more often than not: keep a Rotate button.

## Bring

- Laptop and charger, phone and cable, gooseneck clamp.
- A dark mat or dark folder to put under the paper.
- Printed practice sheets (several copies), black pen, highlighters in two or more colors.
- A small lamp if you have one. Venue lighting is unknown.
- Both Gemini keys, with billing on and a spending cap, each tested the night before.
- A cable from the phone to the Mac.

## Before the day

- [ ] Run the camera test checklist (`docs/camera-test-checklist.md`) and write down the timings.
- [ ] Each of you rebuilds your half once from a blank folder, timed. That is the real rehearsal.
- [ ] Decide what counts as notes you may bring (this plan, the prompt wording, the mark table).
- [ ] Write the 60-second demo script. (A draft is in the doc "Glyph: judge questions and demo script", Nov 21.)
- [ ] Decide the demo cut: which three or four marks, which sheet for each mode. The build table above predates the modes and the box-as-check; redo it once the cut is chosen.
- [ ] Check the event page for sponsors and sponsor prizes (HackwithBay 3.0 had a partner stack). If a sponsor tool is rewarded, decide where one fits before the day.
- [ ] Screen-record one clean run of the demo as a backup video.
