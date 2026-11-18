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

## Who does what (proposal)

- **Yoon Woo:** camera, sheet detection, new-ink detection, highlights. He has the phone and the mount.
- **Skylar:** the model call (prompt, JSON reply, fallbacks, timeout), then the web page.
- Agree in the first 10 minutes on one thing: the data passed between the halves
  (page image, close-up of new ink, and the reply `{action, target, response}`).

## Lessons from the practice build

Model
- Ask for the `v1beta` API explicitly. Newer `google-genai` versions default to `v1`, where the
  `-latest` model names return 404.
- Set a timeout and turn the library's retries off. Otherwise a slow model looks like a freeze.
- Keep a fallback list and drop any model that returns 404. The 2.5 models are closed to new keys.
- Ask for JSON only, and throw away anything that is not a known action.
- Skylar measured `gemini-flash-lite-latest` at 0.8 s for one call. Not yet measured on the real camera.

Seeing the page
- Dark desk under white paper. The sheet edge is what everything else depends on.
- Send only the **new** ink at full contrast and fade the rest, or old marks get answered again.
- Wait for the picture to hold still (about 1 s) before looking. Ignore ink next to a hand.
- A hand over a highlight leaves a smaller piece of it. Treat a piece inside a saved highlight as the same one.
- Correct white balance and brightness before judging color. Warm light makes paper look yellow.
- Glare on a highlight still breaks it. Angle the lamp; do not try to fix this in code on the day.
- Detect highlights by color locally. It costs no model calls.

Demo
- Have a mode that runs with no camera and no network, in case the venue Wi-Fi or the camera fails.
- Show the cut-out of the mark next to its answer. It makes the cause and effect obvious.
- Rate-limit calls (cooldown, calls per minute) so a shaky camera cannot burn the quota mid-demo.

## Bring

- Laptop and charger, phone and cable, gooseneck clamp.
- A dark mat or dark folder to put under the paper.
- Printed practice sheets (several copies), black pen, highlighters in two or more colors.
- A small lamp if you have one. Venue lighting is unknown.
- Both Gemini keys, each tested the night before.

## Before the day

- [ ] Run the camera test checklist (`docs/camera-test-checklist.md`) and write down the timings.
- [ ] Each of you rebuilds your half once from a blank folder, timed. That is the real rehearsal.
- [ ] Decide what counts as notes you may bring (this plan, the prompt wording, the mark table).
- [ ] Write the 60-second demo script.
