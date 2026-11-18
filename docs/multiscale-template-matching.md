# Learned multi-scale template matching

A detectObject template is cut on one screen (its `sourceScreenWidth` x
`sourceScreenHeight`, the **source screen**) and often runs on another: a
Windows host's own 1920x1080 screen cut the template, a PiKVM capturing
1280x720 runs it; a VDI runs at 1280x720 in one place and 1920x1080 in
another. This document is how the engine matches a template on a screen whose
size differs from its source screen, and how it learns, per device, which
template sizes work there.

## What it replaces

Before, `ImageMatcher.produce_template_matches` matched the template at its
stored size, and only when that found nothing and the capture's size differed
from the source screen, it stretched the whole capture to the source size and
matched again. That assumes everything on the screen scales with the
resolution, which is wrong in two of the three cases that occur:

| Case | What happens to a UI element | Old behaviour |
|---|---|---|
| The device scales the whole picture (a PiKVM capturing a 1920x1080 HDMI output at 1280x720, a scaled screenshot) | shrinks with the resolution, by `capture / source` | works, but stretching the capture up blurs thin text |
| A desktop or VDI renders at another resolution with the same display scaling | keeps its pixel size; only the layout moves | the stored-size match works; the stretched retry never can |
| A desktop renders with another display scaling (100 % vs 125 %, Retina) | changes by the scaling ratio, not the resolution ratio | fails |
| The aspect ratio changes (1920x1080 to 1280x1024, a stretched KVM picture) | x and y scale by different factors | works only for a stretched picture |

Every detect that missed on a mismatched screen paid for the second match too,
including the many that miss by design (the siblings of a firstMatch group).

## Terms

- **Capture size**: the full screenshot the detect searches, or for a detect
  whose input is an earlier match, the screenshot that match came from
  (`original_width` x `original_height`).
- **Scale** `(sx, sy)`: the factors the template is resized by before
  matching, so a match is in capture pixels. `(1, 1)` is the stored size.
  x and y are independent, so an aspect change is one scale.
- **Pair**: a device and a (source size, capture size). What is learned is
  learned per pair: the same device at another capture size is another pair,
  and templates cut at another source size are another pair.
- **Confident match**: a match whose score meets the detect's threshold and
  is at least `LEARN_MIN_SCORE` (0.9), at a scale that is not ambiguous (see
  below). Only confident matches teach.

## Behaviour

1. **Sizes equal** (capture size == source size, or the template has no
   source size): unchanged. One match at the stored size, nothing learned.
2. **`useImageRescaledToScreenOnly`**: unchanged. The capture is stretched to
   the source size and matched once; nothing learned. The option exists for
   scripts that asked for exactly that.
3. **Searching** (the pair has no learned set yet):
   1. Match at the stored size. A confident match there is recorded as an
      observation of `(1, 1)`.
   2. Then the scales observed so far, most observed first, and the
      stretch to the capture `(rx, ry)` (the old matching's retry), each
      with its whole-pixel neighbours: a pair that has seen its scale once
      learns from cheap hits instead of searches, and a searching pair never
      finds less than the old matching did.
   3. On a miss, search the scale range (below). The best scale whose best
      score meets the threshold gives the matches; a confident one is
      recorded as an observation of that scale. Searches back off like
      explorations: the first 4 misses in a row search, then the 8th, 16th
      and 32nd, then every 64th. A detect that looks for a screen that is
      not there cannot be told from one at an unknown scale, and on a device
      where most detects miss, a search on every miss costs more than the
      old stretched retry (measured: ~1 s per miss at 1920x1080).
4. **Learned** (the pair has a learned set): try only the learned scales,
   most observed first, and stop at the first that meets the threshold. A
   scale that falls short by less than 0.15 is also tried at its whole-pixel
   neighbours (below). The stored size is tried only when `(1, 1)` is in the
   set. A miss counts
   toward a miss streak; the 8th, 16th and 32nd miss in a row, then every
   64th, also search the likely scales (an **exploration**, no grid). Most
   misses are screens that are not there, not a wrong scale, and the two
   cannot be told apart without searching, so explorations back off; a hit
   resets the streak.
   - An exploration that finds a confident match at a scale outside the set
     records it as an observation, so it can join the set (a device that
     shows two scales, a set learned from few detects). When `RELEARN_AFTER`
     (2) explorations do that with no hit on a learned scale between them,
     the pair goes back to **searching**: the observations of the set the
     first of them missed are dropped, the new ones kept (the device's
     display scaling or capture changed, and the old set still dominates the
     counts).
   - A hit on a learned scale resets the miss streak and the outside count.

### When a set is learned

After every observation the pair's set is recomputed from its observations:

- Observations within 2 % in both x and y are one scale; its value is the
  observation-weighted mean, so repeated hits refine it.
- The set is the fewest scales, most observed first, at most `MAX_LEARNED`
  (3), that hold at least `COVERAGE` (80 %) of all observations, each with at
  least 2. It exists once the pair has `PROMOTE_AFTER` (3) observations and
  such a set can be found; a device that matches at many unrelated scales
  keeps searching.
- Observations age: when their sum passes 60 they are all halved, so a
  change on the device can win within a few dozen detects.

### The search

The search scores candidate scales at half resolution (image and template
both halved), matches the best `COARSE_KEEP` (3) of them at full size, and
refines around the best:

1. **Likely scales**: the stretch to the capture `(rx, ry)` (`rx = capture
   width / source width`), the uniform `(rx, rx)`, `(ry, ry)` and the
   geometric mean, and each of `1`, `rx`, `ry` multiplied by the display
   scaling ratios between 100, 125, 150, 175 and 200 % (`5/4`, `4/5`, `6/5`,
   `3/2`, `2/3`, `7/4`, `4/7`, `2`, `1/2`, ...).
2. **Grid**: uniform scales from 0.5 to 2.0 in steps of 6 %, when no likely
   scale met the threshold.
3. **Refine**: around the best scale so far, x then y in steps of 2 % and
   then 1 % (coordinate ascent), while the score rises; then its whole-pixel
   neighbours.

Scales whose template would be smaller than 8 px on a side, or larger than
the image searched, are skipped; one smaller than 12 px at half resolution is
matched at full size instead. Scales within 1 % of one already tried (the
stored size, the learned scales) are skipped. The grid runs only when the
likely scales, refined, found nothing that meets the threshold.

**Whole pixels.** A resized template has a whole number of pixels, and the
best size of a small one is the floor or the ceiling of `width x sx` (and
`height x sy`), depending on where the element falls on the pixel grid: a
119 px wide template at 2/3 is 79 or 80 px, and on a real capture one of the
two scored 0.76 and the other 0.89. So a scale's **whole-pixel neighbours**
(the other floor and ceiling sizes) are tried when it falls just short; and
when those fall short too, the scale is matched at the template's own
resolution (the capture resized by `1 / scale`, as the old stretched retry
did): thin text and small icons can score higher there than with the template
shrunk (0.82 → 0.91 and 0.73 → 0.91 on two templates the old retry found and
the shrunk template missed). It costs one larger match, on near misses only.

**Enlarging.** A scale above 1 in both directions is matched the other way
round: the image is shrunk by `1 / scale` and the template kept as cut, and
the scores are mapped back to the image's positions (nearest). An enlarged
template is blurrier than the screen it is matched on: on real captures a
template enlarged 1.5 times scored 0.84 where the capture shrunk to the
template's screen scored 0.92 (the old stretched match). Shrinking a
template keeps it sharp, so scales below 1 resize the template.

**What is learned** is not the refined scale, which carries that pixel noise,
but the first likely scale that sizes the template the same within a pixel
or 2.5 % (`(1, 1)`, `(rx, ry)`, ...); only a scale no likely one explains is
learned as found.

A scale is **ambiguous** when the scales that met the threshold span more
than 30 % (max / min of their uniform part): a flat or repetitive template
matches at many sizes, and learning from it would teach noise. Its matches
are still used; it is not recorded.

### What a match at a scale returns

A match found at scale `(sx, sy)` is in capture pixels, as if the template
had been cut on this screen:

- `point` is in the input's pixels (plus the input's match point, as today);
  nothing is translated back.
- `output_mask`, `width` and `height` are the template's output mask resized
  to the matched size (nearest neighbour), so a click's relative point
  (ClickActionHelper picks a point of the mask) lands inside the matched
  element. Before, a stretched match kept the source-size mask, so a click
  inside a large element landed off by the scale.
- `matched_area` is the capture's area under the match, masked by the scaled
  output mask and cropped by the scaled `maskLocation`. A detect whose input
  is this match searches that area, at the same learned scale.
- The click then maps the point from capture to device pixels as today
  (`remap_points_to_screen`).

A detect whose input is an earlier match (nested) now uses the pair's scales
too, with the capture size of the screenshot that match came from. Before, it
always matched at the stored size.

The action log's `template` result gains `scale` (`[sx, sy]` of the matches,
or of the best score on a miss), `scale_mode` (`same-size`, `legacy`,
`searching`, `learned`, `exploring`), `scales_tried` (full-size matches
made) and `searched` (a search or an exploration ran); `resized` keeps its meaning, the legacy stretch of the capture.
score_detects (detect_scorer.py) reports the scale of each detect's best
score and always searches (it has no device to learn for).

## What is stored

Learned scales live in `{data root}/deviceScales/{device}.json`, one file per
device (`host`, `pikvm:...`, `bluestacks:...`; a still image bound with
`file:` learns in memory only):

```json
{"version": 1, "pairs": {
  "1920x1080->1280x720": {
    "observations": [{"sx": 0.6667, "sy": 0.6667, "n": 7.0}],
    "learned": [[0.6667, 0.6667]],
    "outside": 0, "outside_of": [],
    "updated": "2026-11-18T17:02:11Z"}}}
```

Detects run in the main process and in pool workers at once, so each process
keeps its own copy, re-reads the file when its modification time changes, and
writes its own changes as a list of pending operations replayed onto the file
it has just read (under a lock file, replaced atomically). A state change (a
new observation in searching mode, a promotion, an exploration, a relearn) is
written at once; hits on a learned scale are written at most every 30 s.
Losing a write loses some counts, never the learned set.

`SCREENPLAN_SCALE_MATCH=legacy` (environment) turns all of this off and
restores the old behaviour, for comparison and as an escape hatch.

## What it does not change

- fixedObject (detectScene) and the scene compare of a firstMatch detect
  still stretch the scene mask to the capture: a fixed location only means
  something at one layout.
- A click from the action's own point list (no input expression) is still
  remapped by the resolution ratio.
- Templates are not re-cut or stored at other sizes; the resized template is
  made per detect (cheap next to the match).
- A device that shows elements at another size **on a screen the size of the
  source screen** (the same resolution with another display scaling, a
  Retina capture of the same size) is not searched: equal sizes keep the old
  single match, as asked. Learning for that case would need a search on the
  misses of every same-size device, which the measurements below say costs
  more than it would save unless the device is known to differ (a per-device
  setting, a follow-up).

## Measurements

`tools/scale_bench.py` runs a script's detects through the engine's own
detection on captures of another size, once with `SCREENPLAN_SCALE_MATCH=legacy`
and once learning from an empty device, in the same shuffled order, and
reports how many matched, at the right place, their scores and the time per
detect. Measured 2026-11-18 on this repo's development Mac (10 cores, other
work running; times are comparable within a table, not across machines).

**Synthetic: the same screen, resized.** 75 templates cut at 1920x1080 on a
Windows host's own screen (five scripts), each matched on its own source
screenshot resized to another size (where the true place is known) and on two
other scripts' screenshots: 225 detects per size.

| Capture | Own screen found, old → new | Mean best score, old → new | Learned scale | Learned after | ms per detect, old → new (once learned) | 225 detects, old → new |
|---|---|---|---|---|---|---|
| 1280x720 | 25 → 67 of 75 | 0.866 → 0.934 | 0.667 | 7 detects | 75 → 38 | 16.9 s → 10.9 s |
| 1366x768 | 36 → 72 (71 at the right place) | 0.884 → 0.933 | 0.711 | 12 | 83 → 43 | 18.6 s → 14.8 s |
| 1600x900 | 64 → 75 | 0.918 → 0.945 | 0.833 | 13 | 89 → 50 | 20.0 s → 17.3 s |
| 1280x1024 (aspect change) | 46 → 70 | 0.898 → 0.937 | 0.667 x 0.948 | 11 | 85 → 47 | 19.2 s → 19.3 s |
| 2560x1440 | 75 → 75 | 0.980 → 0.980 | 1.333 | 4 | 157 → 72 | 35.3 s → 23.0 s |

The whole-run column includes the learning (258 to 768 ms per detect until
the set was learned). Of the old matching's finds on their own screens, the
new one misses 5, from 3 templates: a 760x32 masked strip at 1280x1024 and at
1366x768 (best 0.62 to 0.65 shrunk, against a threshold of 0.85, too far
below it for the template-size fallback, which runs within 0.15), and a
43x20 icon at 1280x720 (0.73 against 0.9). One match at 1366x768 is at
another place than the template's.

**Real: a VDI at two sizes.** The same VDI's screens cut at 1920x1080 on a
Windows host's own screen and captured at 1280x720 through a PiKVM. The VDI
renders at its window's size, so its elements keep their pixel size: the
right scale is 1.0, and the old stretched retry can never match.

| Templates → captures | Detects | Matched, old / new | Learned | Learned after | ms per detect, old → new once learned | Whole run, old → new |
|---|---|---|---|---|---|---|
| 1920x1080 → 1280x720 | 494 | 65 / 65 | 1.0 | 19 | 77 → 29 | 39.3 s → 30.0 s |
| 1280x720 → 1920x1080 | 315 | 19 / 19 | 1.0 | 68 | 85 → 62 | 27.5 s → 56.7 s |

The same matches, at the same scores; once learned, a detect skips the old
retry's second match on every miss. The second row is the expensive case:
9 in 10 detects miss, the hits are few, so the pair searched for 68 detects
(434 ms each) before it learned, and that run alone does not earn it back.
What is learned is kept, so a device pays it once.

**Real: a laptop through a PiKVM at two sizes.** The laptop's gateway sign-in
page, templates cut at 1280x720 through a PiKVM, against older captures of
the same laptop at 1920x1080: 774 detects, with 6 true matches among them.

| | Matched (true) | Learned | Learned after | ms per detect once learned | Whole run |
|---|---|---|---|---|---|
| old | 10 (6) | | | 143 | 111.0 s |
| new | 11 (6) | 1.5 | 203 detects | 56 | 144.7 s |

(This run's machine was busier than the others': the old matching took
111 s here and 74 s in an earlier run of the same detects.)

Both found the 6 at the same places and scores (0.91 to 0.94), at scale 1.5. The old matching reported them at the template's size (81x73 for one), so its click area covered the top left two thirds of an element that is 122x110 on this capture, the size the new one reports. The others
are one template with a threshold of 0.7 that matches loosely in both: the
search found it once more at a scale of 0.48 (score 0.81). A match below 0.9
never teaches, so it learned nothing from them.

What the measurements changed in the design: whole-pixel neighbours and
learning the likely scale (one script at 1280x720: 12 → 13 of 13 found, and
learned after 13 detects instead of 20), shrinking the image for enlarged
scales (2560x1440: 72 → 75 found; the PiKVM's 1.5: 0.84 → 0.925),
backed-off explorations and searches (the 1280x720 → 1920x1080 VDI run:
300 → 197 ms per detect), the stretch to the capture as a step before
searching (the PiKVM run found 2 of the 6 before it, all 6 after), and the
template-size fallback on near misses (the synthetic runs: 7 → 5 finds of
the old matching missed).

Not measured: a device whose display scaling differs at the same capture
size (not searched, above), and templates on a live device through a whole
run (the measurements call the detection directly, one detect at a time, not
in the process pool).
