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

## 2026-11-23 (23:15), Yoon Woo's Claude

**The plan for tomorrow changed. Read this before anything else.**

**Found.** The organizer's email of Nov 23 names the problem statement: an "AI GTM Engine" (product
in, then ICP, discovery with citations, a knowledge graph, enrichment, human-approved outreach, a
pipeline dashboard; +20 each for Band and Flexprice). Glyph does not answer it. Pre-building is
allowed (Yoon Woo asked).

**Done.** A new build, Tact, a GTM agent that sells Glyph in its demo. It lives in its own repo,
`yoonwoo-lee/tact-gtm` (Yoon Woo creates it tonight; it has its own `CLAUDE.md` and `HANDOFF.md`).
It runs end to end on sample data with no keys. Live services are not tested yet. Nothing in this
repo changed.

**Need from the other side.**
[open] Skylar: from now on, work from the handoff in `tact-gtm`. Your list there: the pitch (who
pays and why), the 2 to 3 minute demo video on sample data, a read of the architecture document.
[open] Both: finish the AWS Builder registration from the organizer's email and bring a physical ID.
The judge-questions doc for Glyph is set aside: only the "what Glyph is" part is still used.

## 2026-11-22 (13:20), Yoon Woo's Claude

Morning run: "everything is good". Last change: the "Reading your mark" pills use the answer tags'
fill (`--tag-fill`). He runs the whole demo once more today, then the practice build is done.
[open] Skylar: the four answers in the judge-questions doc, before pitch practice.

## 2026-11-22 (02:45), Yoon Woo's Claude

Fifth run: an old margin line (sheet lost and found) and ink off the desk were answered as
summaries. All new ink now has to be on paper and unlike any stroke near it on the sheet as taken
in (`_not_old`). 89 checks pass. Pulled onto his Mac; he tests in the morning. See `CLAUDE.md`,
"Nov 22, 02:25".

## 2026-11-22 (02:10), Yoon Woo's Claude

Fourth run: an old highlight was saved again, and the mode name's letter-by-letter effect looked
like a glitch. Highlights now also need the paper under them to have gained color since the sheet
was taken in; the effect is gone. 88 checks pass. See `CLAUDE.md`, "Nov 22, 01:57".

## 2026-11-22 (01:50), Yoon Woo's Claude

Third run: marks and highlights already on a sheet were answered/saved again. At his request
nothing already on a sheet is read now (first look off, old highlights skipped). Mode pill no
longer resizes or bounces. 87 checks pass. See `CLAUDE.md`, "Nov 22, 01:38".

## 2026-11-22 (01:20), Yoon Woo's Claude

Second run of the night: good apart from four things, all addressed, 86 checks pass (one check
rewritten to the new question-mark rule). Mode switch is a crossfade of two still layers (it
stuttered); a circled question mark is never answered from a first look (a printed one passed for
drawn); the practice card is not bold; the reading pill's glow is faint. Details in `CLAUDE.md`,
"Nov 22, 01:10". Not yet seen on the camera: all four.

## 2026-11-22 (00:50), Yoon Woo's Claude

Yoon Woo ran the "Tonight" camera list on live Gemini with the paid key (10 requests, 1.4 to 2.7 s).
- Answered: check mark, target, underline, circle, margin line, one green highlight, the study guide.
- Find (box in Humanities) is not good enough to show: one of two other places returned, outline off
  the word. Advice to him: leave it out of the demo. Not fixed.
- Changed at his request: synonyms are the words only; green highlights are "Important notes", not
  "Definitions"; the card's first sentence is bold; no answer time on the card; a softer tag color
  in Humanities.
- Open: his shadow over blank paper counts as "covered". Pictures of it are saved from the next
  start (`camera/covered_NN.jpg`). Details in `CLAUDE.md`, "Nov 22".
- [open] Skylar: nothing new. The four answers in the judge-questions doc are still wanted.


## 2026-11-21 (21:00), Yoon Woo's Claude

Yoon Woo: Sunday is the last working day. He asked for a plan for tonight (10:30pm to 1:30am), prep
he does not have to do himself, and judge questions.

**Done** (notes only; no code changed)
- A doc for both of you, "Glyph: judge questions and demo script":
  https://claude.ai/artifact/PGTZe79W6BTCd88MWe1DRq (Yoon Woo owns it and has to share it with Skylar).
  A 60-second demo script, about 40 likely questions with short answers, and a "Still to decide" list.
- `docs/camera-test-checklist.md`: a "Tonight" section at the top for the marks that have never
  answered on live Gemini (check mark as worked answer, target, all of Humanities, the study guide).
- `docs/event-day-plan.md`: lessons from Nov 20 and 21, and four more "Before the day" items.

**Found**
- HackwithBay 3.0 (July) had a sponsor partner stack: Neo4j, RocketRide, Butterbase, Daytona, Nebius,
  Opsera. The 4.0 page could not be opened from Claude's side. Glyph uses none of these.

**Need from the other side**
- [open] Skylar: the four open answers under "Users and business" in the doc (proof students want
  it, how it makes money, the competitor check, why this team), and the pitch length if you know it.
- [open] Skylar: does the 4.0 event page list sponsors or sponsor prizes?

## 2026-11-21 (14:45), Yoon Woo's Claude

Yoon Woo ran Glyph at a different desk (a light gray table by a window) and a spark got no answer.

**Found** (read from `sessions/2026-11-21_141531` on his Mac)
- The sheet was never found: the gray table passes for paper, and by the window it is 0.9 times as
  bright as the paper. The whole camera picture was taken for the page. Four requests spent, none
  on the spark: one on the ceiling (phone face up at the start), two on the whole table, one on a
  close-up of his jeans.

**Done** (one commit after `77bf705`; `main` and `camera-test`)
- `glyph/page.py`: `_sheet_by_edges` finds a sheet on a gray desk by the step in brightness round
  it, tried only when the usual way finds nothing and most of the picture is gray or white.
  `looks_written_on`: an empty gray picture is not a page. `glyph/engine.py` uses both.
- Replayed on his saved pictures: the sheet is found in all eight, the spark gets a look with the
  right close-up, the ceiling costs nothing. All 71 older camera pictures give the same outline as
  before. 85 checks pass (two new, on a made-up gray desk: `demo.on_gray_desk`).
- Not re-run on the camera yet.

**Need from the other side**
- Nothing new.

**Later, 14:55:** opening screen, his pick: the logo centered a little above the middle with the faded
line under it, plus a trial row of small marks under the line ("I'll probably want to delete it":
`#hints` in `index.html`). Only `index.html` and notes changed; 85 checks pass. He kept the row ("this is good") and asked for the line fainter and slightly italic: done at 15:00.

**15:20:** at his request the "Read page now" and "Tune" buttons and the model name are off the page
(`/tune` and `POST /api/look` still work). He is about to test the gray-desk fix on the camera.

**15:25:** a bit more pink on the left of the background, at his request ("and then perfect").

**15:45, after his camera test at 15:11 (gray table, live Gemini, five requests):** the fix works on
the camera. Sheet found; spark → hint, two boxed answers → "Not yet" and "Looks right", an
underlined phrase → definition, 2 to 3 s each. He reported one thing as a bug: Glyph "reading marks"
at the very start with nothing on the paper. That was the first look at the new sheet. Asked, he
chose to keep it and relabel it: the status now carries `reading` ("page" or "mark"), and for
"page" the web page says "Taking in the page" and stays on the opening screen. Also at his
request: the page view's shadow is purple in STEM and pink in Humanities. 86 checks pass (one new).

## 2026-11-21 (14:30), Yoon Woo's Claude

Yoon Woo asked for a cleaner right side and a color change between the modes, and chose the color
("warm peach") and the opening line ("Start by drawing a glyph") himself.

**Done** (one commit after `7fdd708`; `main` and `camera-test`; only `glyph/static/index.html` and notes)
- Opening screen: the logo and one faded line. The headline, the paragraph and the list of marks are gone from it.
- The marks of the mode are under a new **Legend** tab. The legend beside End session is removed.
- Humanities mode turns the background warm peach (`#F4A98C`), over 0.9 s. STEM is sky blue as before.
- 83 checks pass. Seen in screenshots of `--demo --mock` only; he has not seen it yet.

**Need from the other side**
- [open] Skylar: the G logo is a placeholder drawn by Claude, and the two mode colors are Yoon Woo's
  picks for now. Both are yours to change.

## 2026-11-21 (14:10), Yoon Woo's Claude

Yoon Woo asked for three things, answering questions first: the check mark gives the answer
("answer with the steps"), another mark checks an answer (he chose a box round it), and the page
should look "less built by AI" (he sent a list of 20 design fixes, to apply where they fit).
While I worked he added: modes renamed STEM and Humanities; "Glyph" with a capital; a logo that is
not Claude's asterisk; no label under the name; readouts down to Sheet and Page; strong pink is
"too much", lighten it.

**Done** (one commit after `3e6b81a`; `main` and `camera-test`)
- New action `answer` (check mark, STEM mode). `check` moved to the box in STEM mode through a
  per-mode override, `modes.student.marks` in `symbols.json`. Up to three boxed answers or check
  marks already on a sheet are answered on a first look, each kind counted on its own.
- Page: everything listed under "Nov 21 afternoon" in the Look section of `CLAUDE.md`.
- Demo worksheet: the corrected line is boxed (check), and a check mark comes last (answer).
- Checks: 83 pass (17 + 9 + 57).

**Not verified:** the `answer` prompt and a box as "check" have never been sent to live Gemini. The
logo is my drawing: Skylar owns the logo and may want his own.

`[open]` Yoon Woo's side: restart Glyph, then section 3d of `docs/camera-test-checklist.md`.
`[open]` Skylar's side: the logo (`.logo` in `glyph/static/index.html`, and the favicon) and the two
mode names are placeholders until he says otherwise.

---

## 2026-11-21 (01:10), Yoon Woo's Claude

Yoon Woo tested the check mark on the camera with live Gemini at 00:20 (`sessions/2026-11-21_002011`
and `_002520` on the Mac). His Mac was on `7fb0cad` (check mark, no modes), which is why he saw no
Editor switch. He reported: the check worked at first and "stopped working on the last question",
one question got nothing, the picture on the card showed several marks, it "only reads and responds
sometimes".

**Found (logs and pictures)**
- Two checks answered by `gemini-3.5-flash-lite` in 2.0 and 3.0 s, both verdicts right, with sound
  working in `looks/*_check.txt`. The check prompt works.
- Q11: its check was drawn at 0:19 with his hand on the sheet; the sheet was taken in at 0:25 and
  the first full read left check marks alone (my rule of the evening before).
- Q14: from 1:19 the paper's colorfulness was 82 (32 before) and its brightness 160 to 180 (211):
  his shadow, with warm light off the wooden desk. `find_sheet` needs under 75, so "No sheet in
  view"; the sheet was found again later as a returning sheet, and its new marks were old ink.
  He drew four checks for Q14 in all.
- The card's picture was a window at least half the page wide round all the new ink.
- Second start: all four models timed out on the first read (39 s, four requests). Page on its side.
- The sheet fills the camera picture: 940 of 1080 pixels high, one corner 20 px outside it.

**Done** (one commit after `fc69b27`; `main` and `camera-test`)
- `find_sheet`: second colorfulness limit from the picture itself when paper and desk form two
  groups; bigger clean sheet wins; the white part of a shaded sheet is not the sheet.
- `see_through`: light (old print still showing) is not a cover; a hand in the shadow still is.
- Highlights wait while colored light is on the sheet.
- First look: up to three check marks are answered; more than three, none.
- `pick_mark` and a close 3:2 picture of the one mark on the card.
- Two timeouts in a row end the round. Rotate's turn is kept in `sessions/view.json`.
- Replay of the saved pictures of that session: all four questions get a look and an answer.
- Checks: 83 pass (17 + 9 + 57).

**Not verified:** none of this on the camera. Editor mode and the target still have never been sent
to live Gemini.

`[open]` Yoon Woo's side: restart Glyph (the Mac is pulled), then the Nov 21 lines and the editor
lines of `docs/camera-test-checklist.md` section 3d. More desk around the sheet in the camera
picture would make it steadier.
`[done]` (from 23:50) Pull the modes onto the Mac.

---

## 2026-11-20 (23:50), Yoon Woo's Claude

Yoon Woo ran checklist section 3c on the camera at about 22:00 and reported that every fix works
("the product is working really well"). The session was not read back from the Mac. He then asked
for features: the check mark, and student and editor modes. His answers to four questions: switch
with a button on the page; box = find, circle = synonyms; a line down the margin = summary; the
visualization mark is left for later. He asked for the switch to be clean, in the color scheme, with
an animation that is "pretty cool" but "slightly minimalistic but techy".

**Done** (`7fb0cad` check mark, then the modes commit; `main` and `camera-test`)
- Check mark (student): `check` action. The model solves the problem in a `work` field first, then
  gives a verdict. Card titled "Looks right" / "Not yet" / "Could not tell". Never the answer.
- Target (student): `practice` action, one new problem of the same kind.
- Modes in `symbols.json` (`modes`), `config.legend_for`, a prompt per mode, `POST /api/mode`,
  `GLYPH_MODE`. Editor mode: box → `find` (other places outlined on the page from `box_2d`),
  circle → `synonym`, margin line → `summarize`. No stuck nudge in editor mode.
- First reads leave alone every mark on words and every check mark; "Read page now" answers them.
- The page: Student | Editor switch beside the name, one switch animation (described under "Look" in
  `CLAUDE.md`), marks list and bottom keys per mode, cards for the new answers.
- Demo: the worksheet ends with a checked answer and a target; switching to Editor puts a page of
  reading under the "camera" (`DemoSource`).
- Checks: 77 pass (17 + 9 + 51).

**Found**
- With a key in `.env`, `--demo` sends the demo sheets to live Gemini (one request per mark). The
  free one is `--demo --mock`. I had told him the plain demo was free, and corrected it.
- In the demo, the old sheet's highlight outlines stayed on the new sheet for the three seconds
  before it is taken in. Outlines are now hidden while the sheet on view cannot be matched to the
  remembered one.

**Not verified:** nothing built tonight has been sent to live Gemini or seen on the camera. The Mac
could not be reached at the end; its clone is at `7fb0cad` (check mark only) and needs
`git pull --ff-only origin camera-test`.

`[open]` Yoon Woo's side: pull, then `docs/camera-test-checklist.md` section 3d (about 8 requests;
the free key has about 10 a day). To see everything without a request: `bash start.sh --demo --mock`.
`[open]` Skylar's side (business): the two modes need a line each in the demo story, and the names
"Student" and "Editor" are Yoon Woo's working names: they are two strings in `symbols.json`.
`[done]` (from 19:30) Section 3c: passed on the camera, by Yoon Woo's report.

---

## 2026-11-20 (19:30), Yoon Woo's Claude

Second camera run on live Gemini (`sessions/2026-11-20_175202` on the Mac, 8 looks, all answered by
`gemini-3.5-flash-lite` in 1.5 to 5.8 s). The pink close-up works: spark, three underlines on print.
Yoon Woo: tracking and page "amazing", "starting to look like its final form". He reported two hints
for one spark, "ball" not working, was unsure about highlights, liked that old underlines were not
read, and asked for the answers side to be a little more organized. Then he left; all of this was
done unattended.

**Found (from the logs and pictures)**
- Two hints: look 2 was the first full read of the sheet after Rotate, with the spark already in
  its picture → hint. The spark was not in the remembered page, so look 3 sent it as new ink →
  second hint (the "second spark by the same problem" rule let it through).
- "ball": the underline lay one or two pixels under the letters, seven pixels thick, 25 long. The
  "new ink" rule refuses anything within four pixels of print, which left 35 pixels; a look needs 120.
  It was only read when "acceleration" was underlined a minute later (both defined in one look).
- Highlight: he drew one green stroke over a line of small print. Nothing was saved. The stroke is
  13 px tall, cut up by the letters (a 5x5 opening erased it), and half of it is paler than the range.
- Rotate gave the sheet a new page number: signatures were filtered along the text lines and then
  turned, and matched at 0.43 (0.6 needed). Turned first and filtered afterwards: 0.93.
- Old underlines on the speech were not answered only because the model happened to report none.

**Done** (`8f6105d` fixes, `90d1d66` answers side, then this note; `main` and `camera-test`)
- Full read that gave an answer → its picture becomes the remembered page (not under a hand).
- `new_ink` also takes solid ink beside print where the print has not moved (`_added_beside_print`);
  `short_underline` lets a short flat stroke under print trigger a look below 120 px.
- `detect_highlights`: paler color counts when joined to color in range, in a band that is solid
  together with its letters (keeps out-of-focus blue pen out). Real picture: green found, 432x18.
- Signatures kept unfiltered (`page_signature`), filtered in `same_page` (`_words`).
- First reads drop underlines in the engine (`reason != "you asked"`); symbols still answered.
- Answers side: heading for the newest answer with the reading pill in it (the card no longer
  moves, measured 141 px before and during a read), two-column card, earlier answers grouped by
  page, hints say which problem, counts on headings. Look unchanged.
- Checks: 64 pass (17 + 9 + 38); six new ones, each fails on the old code. Replays of the Nov 19
  and Nov 20 pictures give the expected looks.

**Not verified:** all of the above on the real camera and against live Gemini (replays and checks
only). The Mac could not be reached at the end, so its clone is at `7bff551`: it needs
`git pull --ff-only origin camera-test`.

**Left as it is**
- "functions" underlined → the model answered "functions of time t". Prompt not changed (cannot be
  tried against Gemini from here).
- Sheet outline unsure with pale floor in view (16:40 entry): not seen in the second run.
- The "arm across the sheet" replay ends with an ink look: its last picture has new marks in it, so
  that is right; the "expect" line in the replay script is out of date.

`[open]` Yoon Woo's side: pull, then `docs/camera-test-checklist.md` section 3c (five lines, about
five requests). He has roughly 10 requests a day on the free key; 8 were used on Nov 20.
`[done]` (from 16:40) He restarted and drew a spark: it was answered.

---

## 2026-11-20 (16:40), Yoon Woo's Claude

First camera run on live Gemini with the Nov 19 changes (`sessions/2026-11-20_161627` on the Mac,
free-tier key in a new project, about 10 requests a day). Yoon Woo: the page and tracking look right,
but no answer appeared.

**Found**
- Gemini did answer, both times with no marks: look 1 (full read, 2.2 s, correct: nothing drawn yet)
  and look 2 (new ink, 8.2 s) after he drew a small spark next to problem 7.
- Cause of look 2: `looks/002_new_ink.jpg` shows the spark as a **solid pink blob**. The spark was
  about 22 px across on the page; its arms are a pixel or two apart, so the new-ink area has no gaps,
  and `make_focus_crop` painted that whole area pink. The model was shown a blob, not a symbol.
- Sheet outline was "not sure" in the 8 pictures saved at look 1 (`find_page` gives a corner at
  (1767, 0)): pale floor is in view to the right of the desk and a black object touches the top right
  corner. It read anyway in the real run. Not fixed.

**Done** (this commit, on `main` and `camera-test`; Mac pulled)
- `make_focus_crop`: enlarge first (up to 4x, was 2.5x), then put the pink on the ink itself by how
  dark each spot is against the paper around it. Replaying his picture gives a pink eight-armed
  spark. A filled shape still gets colored whole. New check with a camera-sized spark (fails on the
  old code). 59 pass (17 + 9 + 33).

**Not verified:** the new close-up against live Gemini (sandbox cannot reach it; his key has about
8 requests left today). `[open]` Yoon Woo's side: restart Glyph, draw a new spark, say what came back.

---

## 2026-11-20 (00:20), Yoon Woo's Claude

- Yoon Woo said "check the session". The newest folder in `sessions/` on his Mac is still
  `2026-11-19_135230` (the afternoon run already studied), so there was no new camera run to read.
- The Mac's clone is now at `be02a9d` (pulled; it has the nudge and the camera-view overlay).
- The `[open]` camera run from the 21:30 entry stands.

---

## 2026-11-19 (21:30), Yoon Woo's Claude

Yoon Woo went out for the evening and asked for work to go on without him. His answers to three
questions: build the stuck nudge, then the camera-view overlay, then UI fixes; **no live Gemini
calls**; the look stays as approved (fixes only); push to `main`.

**Done** (`eff4577`, `3e8a446`, then this note; on `main` and `camera-test`, branch `stuck-nudge` merged)
- **Stuck nudge.** No new writing for `GLYPH_STUCK_SECONDS` (90; `0` = off) with a sheet in plain view
  → one "Keep going" card, from five fixed lines, no model call. The clock starts when a page is taken
  in and starts again on new ink, a new highlight, a new page and Rotate. One card per pause. None
  while a mark is being read, a full read is waiting, the page is covered or moving, or there is no
  sheet. In `glyph/engine.py`: `NUDGES`, `Settings.stuck_seconds`, `_wrote`, the check before `_publish`.
- **Camera view shows what is tracked.** `status.view.cam` carries the mark box, the highlights and
  the covers as four corners each in the camera picture (page box → undo the view's turn → back
  through the sheet's outline). The web page draws them on the camera view with the same styles.
- Checks: `test_pipeline` is now 17 (4 for the nudge, 1 that the camera-view boxes map back onto the
  page boxes, turned and not). 58 pass in all (17 + 9 + 32), run one after another.

**Found**
- New tests call `engine._tick(frame, now)` directly with a made-up clock (`_stepper`), half a second
  per step. Stepping by 0.1 s made the suite take over three minutes.
- Safari still not checked: WebKit cannot be installed in the sandbox. The `-webkit-` prefixes for
  the frosted tiles and the gradient headline are in place.
- The Mac stopped answering during this session (asleep or the app closed), so the Mac's clone is
  still at `f1eae8d`. It needs `git pull --ff-only origin camera-test`.

**Not verified:** the nudge and the camera-view boxes on the real camera (demo sheet and checks only).

`[open]` Yoon Woo's side: the camera run on live Gemini (`docs/camera-test-checklist.md`, 1b first) is
now the only thing between him and "done by Saturday". While there: switch to Camera view and see
that the pink frame sits on the mark; stop writing for 90 s and see one "Keep going" card.
`[done]` (from 19:10) He was reminded of the camera run; he chose the order above.

---

## 2026-11-19 (19:10), Yoon Woo's Claude

**Yoon Woo wants to be done building by Saturday Nov 21.** He asked whether the features all work.
What I told him, so the next session says the same thing:

- All 53 checks pass on `f9845e9` (12 + 9 + 32, run one after another).
- Seen working on his camera before today's changes: sheet found and flattened, Rotate, spark → hint,
  underline → definition on handwriting, yellow highlights.
- **Never yet run against live Gemini or his camera:** everything changed on Nov 19 (one answer per
  mark, the pink close-up and new prompt, underline on print, page numbers, "No sheet in view"), the
  circled question mark, green / pink / blue highlighters, the study guide on real highlights (it is a
  model call), the new look in Safari.
- The one thing that decides Saturday is a 15-minute run of `docs/camera-test-checklist.md` (section
  1b first) on a key with allowance left. Then fix what it shows, run it again, stop.
- Not built, his call: stuck nudge; the mark and highlights drawn on the camera view.

19:20 update: he showed the look to someone, who found the scan effect and the pink in the bottom
left corner a little too much. Both toned down (one soft corner glow; a thin slow scan line). He
then said: UI only for now, features later, "just remind me". So:

`[open]` Next session on his side: when the UI work wraps up, remind him of the camera run and ask
for its result before building anything new. If his Mac is reachable, read `sessions/<latest>/` there yourself (events, `looks/`,
`timings.jsonl`) instead of asking him to describe it.

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
- 18:50, settled: Yoon Woo said the answers side of the 16:15 version "was perfect"; what he had
  disliked was only the thick, full-width hot pink "Reading your mark" bar. Two tries in between (no
  pink on that side, `d051cca`; the answer as a filled blue block, `f1eae8d`) were misreadings and are
  undone. Now: the 16:15 answers side, with "Reading your mark" as a small sky-blue pill and the
  first-screen headline a little smaller (54 px at most). Lesson: when he says "too much X", ask or
  show which element before restyling everything that has X.
- 19:00: Motion. Answers and the study guide are written out letter by letter (`typeOut` in
  `index.html`: lays the text out, empties it, fills it back in place, so nothing jumps). The
  first-screen headline folds away when a read starts, the list of marks when the first answer
  arrives. Also fixed: the first answer of a session was treated as already there (`lastId === 0`),
  so it never animated. He asked whether the camera view shows what is tracked: it shows only the
  sheet outline; the page view shows the rest. Drawing the mark and highlights on the camera
  picture too is offered, not built (it needs the page's turn, which `status.view` does not carry).
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
