# Lab notebook

Findings, measurements and dead ends, newest first. ADRs record *decisions*; this records
*what we learned*, including the things that turned out to be wrong.

It exists because a lot of hard-won nuance lives nowhere else. An ADR says "score the
discriminants"; it does not say "the flux-weighted second moment reads 7% high and here is
why". That second kind of knowledge is what gets lost, and losing it means re-learning it
the expensive way.

**Rule:** if a session discovers a number, a gotcha, or a wrong assumption, it lands here
before the session ends.

---

## Reproducing the numbers on this page

| Product | Command | Committed output |
|---|---|---|
| Detector diagnostics | `uv run rbh inspect` | — |
| Destination sky | `uv run rbh fetch-destinations` | `data/destinations/` (git-ignored) |
| Generator calibration | `uv run rbh calibrate` | [`docs/data/phase2-calibration.json`](../data/phase2-calibration.json) |
| Completeness grid | `uv run rbh completeness` | [`docs/data/phase2-completeness.json`](../data/phase2-completeness.json) |

Both studies live in `rbh.studies`, not in scratch scripts. They were prototyped as
throwaway files and that was a mistake — they generate the numbers the project's claims rest
on, and a script in a temp directory satisfies nothing in
[ADR-0012](../adr/0012-reproducibility-contract.md).

---

## 2026-08-01 — Phase 2: the blind test failed, 20 out of 20

ADR-0017's blind test was taken. **The result is 20/20 correct, 4.5σ above chance.** The
synthetic wakes are trivially distinguishable from transplanted real pixels, so the generator
is not representative and any completeness measured with it is optimistic.

This is the check working exactly as intended, and it is worth being clear how badly the
statistics had failed to notice. The generator was fitted to reproduce four measured
statistics of the real object — recovered length, measured width, fragmentation rate, axis
ratio — and it reproduced all four. It still looked obviously wrong to a person at first
glance. **Matching four numbers is not the same as looking right**, which is precisely the
argument ADR-0017 made for building this test rather than trusting the fit.

### The tells, and the code behind each

Reported by the participant, unprompted, in their own terms:

| What they saw | What it was |
|---|---|
| "a large head at the start of the wake" — like a shooting star | `terminal_knot_fraction=0.12` put 12% of the flux into a knot a few pixels across at one end. **None of the four calibration statistics is sensitive to it**, so the fit never constrained it and it sat at a guessed value. The transplant is the *detected* part of RBH-1 and has no such head. |
| "an extremely clean and linear trail" versus real ones "much more irregular, a bit blobby" | The transverse profile was a Gaussian of constant width along the entire length. Real wakes thicken and thin. |
| "a slight curve in the same direction, along the trail length" | The spine bend was a parabola whose sign was **fixed in code**, so every synthetic bowed the same way. |
| noticed afterwards: "all of the real ones are in the same direction" | `inject_template` never rotated the template, so every transplant carried RBH-1's own position angle of 148.3° while synthetics got a random one. A systematic difference between the classes unrelated to the question being asked. |

The first three are generator defects. The fourth is a defect in the *test*, and the
participant reported it did not affect their answers — but it had to be fixed regardless.

### What it costs

- **The transplant-based numbers stand.** They are real pixels; nothing about this touches
  them. The headline 50% completeness limit of 24.61 was measured with the transplant.
- **The parametric numbers are optimistic**, and the existing grid already showed by how
  much: at magnitude 24.8 the transplant gave 27% against 30–46% for the generator. The
  50% limits agreed to 0.14 mag, so the divergence is in the faint tail rather than at the
  half-power point.
- **The whole length grid rests on the generator** and must be re-measured after
  recalibration. It is the one result with no transplant anchor, because a fixed set of real
  pixels cannot be stretched to another length without resampling away its knots.

### Fixes made

`terminal_knot_fraction` defaults to 0; curvature sign and vertex position are drawn per
render; transverse width varies along the feature via a smooth random profile
(`width_jitter`, default 0.45); and the blind test now applies a random quadrant rotation and
reflection to the transplant. Quadrant only — an arbitrary angle would resample and smooth
the knots, which is the bias ADR-0017 exists to avoid — so eight orientations rather than
uniform coverage, and that limitation is real.

### The general lesson

**An unconstrained parameter left at a guessed value is invisible to a fit and obvious to a
human.** The terminal knot was never measured by anything, so the calibration was free to
leave it wrong, and it turned out to be the loudest signal in the image. Worth checking, for
any fitted model: which parameters does the objective actually constrain, and what is
carrying the rest?

---

## 2026-07-30 — Phase 2: the long-feature collapse was my own harness

The first length grid showed completeness collapsing for long features — 8% at 16″ and
magnitude 23.8, against the 63% the corrected grid gives. Before writing that up as a
detector property, three candidate causes were tested by relaxing each in turn:

| variant | 16″ @ 23.8 |
|---|---|
| as configured | 8% |
| straightness cut relaxed **10×** | 8% (no change at all) |
| axis-ratio floor removed | 13% |

Neither window cut was responsible, so the loss was upstream of the window. It turned out to
be **the truth-matching radius in `run_trial`**, which was a fixed 4″. A feature recovered as
a fragment has its centroid displaced toward that fragment by up to half the feature's
length, so a fragmented 16″ feature lands 8″ from the injection centre and was scored a miss
despite being detected perfectly:

| match radius | 16″ detected | 16″ passes window |
|---|---|---|
| 4″ (as used) | 69% | **19%** |
| 8″ | 100% | **69%** |
| 15″ | 100% | 62% |

So completeness for long features was understated by roughly a factor of 8. Fixed: the radius
is now derived as `max(4, 0.5 × length + 2)` arcsec, with the injected length carried on the
`Injection` record — which meant giving `SourceTemplate` a `length_arcsec` too, since
transplants previously reported NaN.

Note the radius has an optimum rather than a floor: at 15″ on an 8″ feature completeness
*falls* from 94% to 88%, because an over-wide radius starts matching unrelated detections.

Two lessons worth carrying:

- **A completeness measurement can be limited by the measuring apparatus.** The number looked
  like a statement about the detector and was a statement about my matching criterion. Any
  parameter of the harness that is absolute where the thing it measures is scale-dependent is
  a candidate for the same error.
- **Chasing the mechanism paid.** Reporting "long features are lost" would have been true of
  the numbers and false about the world, and would have gone into the selection function.

The 8.1″ results are unaffected (94% at radius 4 and 8 alike), so the headline
completeness-versus-magnitude measurement stands.

Corrected grid, against the buggy one, at magnitude 23.8:

| length | buggy | corrected |
|---|---|---|
| 8.1″ | 98% | 98% |
| 12″ | 63% | **84%** |
| 16″ | 8% | **63%** |

---

## 2026-07-30 — Phase 2: completeness across feature length

Completeness (%) at fixed **total** magnitude, generator at calibrated parameters, measured
with the corrected truth-matching radius:

| length | 23.0 | 23.8 | 24.4 | 25.0 | mean SB at 25.0 |
|---|---|---|---|---|---|
| 2.5″ | 84 | 100 | 87 | 27 | 24.4 |
| 4.0″ | 100 | 98 | 92 | 46 | 24.9 |
| 6.0″ | 100 | 98 | 83 | 24 | 25.3 |
| 8.1″ | 100 | 98 | 65 | 10 | 25.6 |
| 12.0″ | 100 | 84 | 30 | 10 | 26.1 |
| 16.0″ | 95 | 63 | 13 | 10 | 26.4 |

Total magnitude is the misleading axis: at fixed magnitude a longer feature is spread thinner,
so its surface brightness falls by 2 mag from 2.5″ to 16″. Converting each row's 50% limit to
mean surface brightness is the fair comparison:

| length | 50% limit (mag) | 50% limit (SB) | axis ratio |
|---|---|---|---|
| 2.5″ | 24.77 | **24.12** | 11.4 |
| 4.0″ | 24.95 | 24.81 | 18.2 |
| 6.0″ | 24.73 | 25.03 | 27.3 |
| 8.1″ | 24.56 | 25.19 | 36.8 |
| 12.0″ | 24.18 | 25.23 | 54.5 |
| 16.0″ | 23.96 | **25.33** | 72.7 |

**Surface-brightness reach improves monotonically with length**, 24.12 → 25.33 over the range,
a spread of 1.20 mag. That is what a matched filter should do: a longer feature integrates
more signal along its length, so it can be found at lower surface brightness. The only
departure is the short end, which is the selection window doing its job — a 2.5″ feature sits
just above the 2″ floor and its measured axis ratio scatters across the 8.0 threshold.

**This reverses the interpretation drawn from the buggy grid**, which had the reach peaking at
exactly RBH-1's own length and looked like the selection window admiring its own reflection.
There is no such peak. Worth remembering how convincing the wrong version was: it had a
plausible mechanism ready-made ([ADR-0007](../adr/0007-target-selection-window.md) was derived
from RBH-1, so of course it would favour RBH-1) and it was wrong.

**Consequence for the science.** At fixed *surface brightness* — which is what the shock
physics sets, while length is set by time since ejection — completeness **improves** as a wake
ages and lengthens. The earlier claim in this notebook that we are "biased toward young wakes"
was an artefact of the bug and is withdrawn. Both statements below are true and it matters
which is quoted:

- at fixed total magnitude, longer features are *harder* (spread thinner);
- at fixed surface brightness, longer features are *easier* (more signal integrated).

### Limits on this measurement

- **It cannot cover its own selection window.** Tiles are 20″; nothing beyond ~16″ fits.
  ADR-0007 admits features to 25″. Cells that do not fit are emitted with a note rather than
  omitted, because a missing row reads as "not measured" instead of "cannot be measured".
  Phase 3 should use larger tiles.
- **The 12″ and 16″ rows are compromised anyway.** A 16″ feature can only be centred within
  ~4″ of the tile centre, so the three trials per tile sit on nearly the same background.
- **Only the 8.1″ column is anchored.** The transplant cannot travel along this axis —
  stretching real pixels resamples and smooths the knots, the exact bias ADR-0017 exists to
  avoid — so every other length rests on the generator extrapolating from where it was
  calibrated.

---

## 2026-07-30 — Phase 2: the wake-versus-disc features

Built the stage 6 feature vector ([ADR-0008](../adr/0008-scored-discriminants-not-cuts.md))
and a harvester for its negative class, then measured how well the features actually
separate. Positives: 29 recovered RBH-1 transplants. Negatives: 9 elongated sources harvested
from the control tiles by segmentation photometry — deliberately a *different* detector from
the ridge filter, since using the same one would select only the galaxies that already look
like ridges, which is circular.

AUC for "wake scores higher":

| feature | wakes | galaxies | AUC | verdict |
|---|---|---|---|---|
| `transverse_colour_dip` | −0.185 | +0.050 | **0.12** | strongest; discs higher, as designed |
| `terminal_knot_contrast` | 1.55 | 1.75 | 0.26 | **reversed** — discs are more concentrated |
| `longitudinal_asymmetry` | 0.042 | 0.032 | 0.57 | no useful separation |
| `filling_factor` | 1.00 | 1.00 | 0.43 | none for wake/disc — but see below |

**Three of four behaved differently from their design.** Only the colour dip worked as
predicted. Worth being specific about why the others failed, because the reasons generalise:

- *Longitudinal asymmetry* assumed we see the whole wake. We do not — only the bright middle
  is detected, and that part is roughly symmetric. The asymmetry lives in the faint tail the
  detector never reaches. A feature can only measure what got detected.
- *Terminal knot contrast* discriminates in reverse: galaxies have bright centres, so they
  score *higher* on peak-over-median than wakes do. Still informative, but it is a
  central-concentration statistic favouring discs, not a terminal-knot detector.

**The features do solve the spurious-join problem**, which was the question worth asking:

| | filling | asymmetry | knot contrast |
|---|---|---|---|
| transplanted wakes | 1.00 | 0.04 | 1.55 |
| real galaxies | 1.00 | 0.03 | 1.75 |
| **spurious joins** | **0.80** | **0.15–0.18** | **2.3–5.8** |

The two spurious linking joins separate cleanly from *both* real classes on three features at
once. So the [ADR-0016](../adr/0016-rejoin-collinear-fragments.md) false positives are
tractable by scoring even though no geometric cut could touch them — which is what
[ADR-0008](../adr/0008-scored-discriminants-not-cuts.md) predicted in general terms.

### Caveats that outweigh the numbers

- **The negative sample is nine objects at axis ratio 3.1–4.5**, far rounder than the ≥ 8 the
  selection window demands. These are not yet the contaminants we actually face. 2.1 arcmin²
  of sky simply does not contain many thin edge-on discs; a representative sample needs
  Phase 3 area.
- **The strongest discriminant in ADR-0008 is not computable here at all.** Both filters are
  optical, and at z ≈ 1 even F814W samples rest-frame ~4100 Å, so there is no rest-frame
  near-infrared measurement to be had. Fields with WFC3/IR or NIRCam will do better — an
  argument for the Tier A prioritisation in ADR-0006.
- **The colour dip may be measuring thinness, not dust.** For a feature narrower than the
  sampling strip the "flanks" are largely empty sky, so part of the signal could be the
  absence of flux rather than the presence of a dust lane. Untangling that needs a wider
  feature or a narrower strip.

Treat these AUCs as a first look, not a calibration. No weights fitted, no threshold set.

---

## 2026-07-30 — Phase 2: negative controls

### What fragment linking costs

Over 19 non-overlapping archival tiles (2.11 arcmin², RBH-1's own field excluded), survivors
of the selection window went **1 → 5** when linking was enabled — five-fold, +4. Raw
detections meanwhile *fell*, 261 → 256: five merges happened, and four of them turned
fragments that each failed the window into single objects that passed it. The debt
[ADR-0016](../adr/0016-rejoin-collinear-fragments.md) left open is settled, and the cost is
larger than "assumed small" would have allowed.

Rates: 1700 ± 2400 per deg² unlinked, 8500 ± 4200 linked. The Poisson errors overlap, so the
*rates* are barely constrained; the paired ratio is what carries the result, since both arms
see identical pixels.

**The mechanism is not the one ADR-0016 guessed.** It worried about unrelated collinear
*noise* blobs. Over 33 arcmin² of pure noise, linking added exactly **zero** survivors — the
noise false-positive rate is under ~108/deg² with or without it. What linking joins is
unrelated collinear **real sources**.

Eyeballing every survivor (figure: [`docs/data/phase2-control-candidates.png`](../data/phase2-control-candidates.png)):

| Field | What it is | Linking's role |
|---|---|---|
| `dest_008` | two unrelated compact sources, well separated | spurious join |
| `dest_016` | compact source plus a nearby knot | spurious join |
| `dest_013` | elongated bright object, almost certainly an edge-on galaxy | reassembled one real object |
| `dest_018` | unremarkable field — see the correction below | joined fragments of something faint |
| `dest_015` | thin streak, passes with and without linking | none |

Two follow-ups were proposed on the strength of this, and **measurement rejected both**. See
below. The spurious joins therefore stand unmitigated; the right lever is the wake-versus-disc
scoring of [ADR-0008](../adr/0008-scored-discriminants-not-cuts.md), which is Phase 4.

### The noise model is sound across coverage

Worth having as a positive result, since every threshold in the pipeline is denominated in the
noise map. The scatter of the signal-to-noise image should be exactly 1.0 everywhere by
construction. Measured over 20 tiles, in bins of weight relative to the tile median:

| weight / median | 0–0.3 | 0.3–0.5 | 0.5–0.7 | 0.7–0.9 | 0.9–1.05 | > 1.05 |
|---|---|---|---|---|---|---|
| S/N scatter | 0.99 | 0.96 | 0.99 | 0.98 | 0.97 | 0.93 |

Within 7% of unity over a hundred-fold range in weight, and biased slightly *conservative*
(below one means the map marginally overestimates the noise, so thresholds are marginally
stricter than nominal). The `1/sqrt(weight)` scaling holds. Now a permanent check,
`rbh.controls.noise_model_scatter`.

It did surface one real flaw: `background_and_sigma` measured the sigma over the whole band
while `noise_map` scales it from the *median* weight, so the normalisation is off by a constant
whenever weights are broadly spread — 1.8x on a synthetic half-and-half tile. Now measured from
pixels near the reference weight. On real data it is a no-op (RBH-1's recovery is unchanged to
four significant figures), but it is correct rather than approximately correct. Note it cannot
help a strongly *bimodal* weight map, where the median describes no actual pixel; such a map
cannot be normalised from a single sigma at all.

### Other control results

- **The selection window rejects ~99% of raw detections** — of order 150 raw ridges per
  2 arcmin² become 1–5 survivors. That is where purity comes from.
- **The detector is exactly invariant** under all three quadrant rotations and reflection:
  identical counts, verified not to be a no-op. Pinned as a test.
- **Shuffled filters give zero survivors** while producing a comparable number of raw
  detections. Pairing band A of one field with band B of another destroys the real
  cross-filter coincidence, and the survivors vanish with it — [ADR-0006](../adr/0006-two-tier-filter-requirement.md)'s
  assumption behaving as advertised, on small numbers.

### Things that were wrong

**Reported "linking adds zero false positives" on 8 tiles.** With 12 tiles it became 1 → 2,
with 17 it became 1 → 4, and with 19 it became 1 → 5. The first result was not wrong
arithmetic, it was an
under-powered sample being read as a null result. A ratio of 1.00 from one survivor
constrains nothing; it should have been reported as "no constraint" rather than "no cost".
Lesson, generally applicable: quote the power alongside the point estimate, or a null is
indistinguishable from an absence of data.

**Described the rotation control as decoupling sky structure from detector geometry.** It does
not. Rotating the pixels rotates any detector-frame artifact with them, so nothing is
isolated. It tests rotation *invariance*, which is worth having but is a different thing. The
real artifact test is cross-visit — same sky, different roll angle — and needs Phase 3
coverage.

**The control sample contained the target.** `fetch-destinations --layout grid` starts at the
reference position, so `dest_000` is the RBH-1 discovery field: its centre is 4.0 arcsec from
the published coordinate. One of the "false positives" in blank sky was RBH-1 itself. The
`controls` command now takes `--exclude`, and any field with a known object must be dropped.

**Called `dest_018` "visible vertical detector striping". It is not striped.** Column and row
striping significances are 2.2 and 2.1 — indistinguishable from clean tiles — and with a
stretch matched across tiles the field is unremarkable. The apparent banding came from
per-panel zscale in the inspection figure: a low-contrast crop gets stretched hard and ordinary
noise turns into visible stripes. **Lesson: never judge background quality from stamps at
independent stretches.** Compare at a shared stretch, or better, use a statistic.

**Proposed two follow-up cuts; measurement rejected both.**

- *Maximum gap-to-length ratio.* Gap over union-span came out 0.30 and 0.39 for the two
  spurious joins, against 0.40 for the real galaxy and 0.18 for `dest_018`. The classes are
  not separated, so any cut that kills the spurious joins kills a real object too. Also worth
  noting: RBH-1's own field produces **no** linkable pairs at default thresholds, so the one
  real example could not have constrained such a cut at all — exactly the unconstrained tuning
  ADR-0010 exists to prevent.
- *Coverage-based data-quality cut.* Not warranted: see the noise-model result above. The
  suspicion was reasonable — `dest_013` really does sit in poor coverage, 30% of pixels below
  0.8x median weight against 5–12% typical — but the noise model already absorbs it.

---

## 2026-07-30 — Phase 2: injection–recovery

### The headline

Completeness is **~100% down to F606W ≈ 23.8** (RBH-1 itself is 23.77), with a **50% limit at
24.61**. Across the full clumpiness range 0.0–0.9 the 50% limit moves only **0.14 mag**
(24.60 / 24.68 / 24.69 / 24.74).

That last number is the important one. Clumpiness is the morphological property we can least
constrain from a single object, and it barely matters — because fragmentation *does* climb
hard with it (68% → 100%) but collinear fragment linking
([ADR-0016](../adr/0016-rejoin-collinear-fragments.md)) absorbs it before the selection
window sees it. A step added to fix a Phase 1 annoyance turns out to be what makes the
Phase 2 measurement robust.

44 injection sites across 11 real archival tiles; binomial uncertainty ±7.5% at p = 0.5.

### Reproduction check (half the sites)

Re-running through the promoted `rbh completeness` command at `--per-tile 2` (22 sites
instead of 44) gives limits of 24.70 / 24.62 / 24.53 / 24.62 / 24.55, spread **0.17 mag**.

Two conclusions, one reassuring and one corrective:

- **The headline survives.** The spread stays ~0.15 mag, and every limit sits within about
  0.1 mag of the 44-site value — consistent with the ±10.7% binomial noise at n = 22.
- **The apparent monotonic rise with clumpiness does not reproduce.** In the 44-site run the
  limits ordered neatly 24.60 < 24.68 < 24.69 < 24.74; at 22 sites the ordering vanishes.
  That trend was flagged as ~1.9σ at the time and it was right to flag it: it was sample
  noise. **Do not read the ordering in the tables as a real effect** — only the smallness of
  the spread is established.

### Calibration outcome

| | length | width | axis ratio | fragmentation |
|---|---|---|---|---|
| Real RBH-1 | 5.50″ | 0.256″ | 21.4 | — |
| Transplanted real pixels | 5.60″ | 0.274″ | 20.6 | 64–72% |
| Generator, **before** calibration | **8.27″** | 0.234″ | **34.5** | 36% |
| Generator, after calibration | 5.87″ | 0.258″ | 23.3 | 79% |

Fitted: `tail_brightness=0.02`, `clumpiness=0.1`, `width_arcsec=0.22`.

### Things that were wrong

**Sequential parameter tuning.** Fitted tail brightness, then clumpiness, then width. The
width step silently undid the length match — 6.4″ → 3.8″ against a 5.6″ target — because
widening a feature at fixed total flux lowers its peak surface brightness, so less clears the
threshold. The parameters interact; the grid must be joint. Costly mistake to repeat, cheap
to avoid.

**Assumed clumpiness 0.6; measured 0.0–0.2.** The reasoning had been "wakes are knotty,
knots cause fragmentation". True but not dominant: a nearly *smooth* feature already
fragments 65–80% at this surface brightness, because the threshold cuts wherever noise dips.

**Tried to measure the PSF from the fixture.** Got 0.39″ from five "compact" sources — but
they are 175–215 pixel *galaxies*, so that measured their sizes, not the telescope's blur.
There are no stars in a 20″ high-latitude extragalactic field. The effective drizzled PSF is
therefore **unmeasured**, assumed 0.11″, and degenerate with the generator's fitted width.

### Open questions

- **Width–PSF degeneracy.** The fit wants 0.22″ intrinsic against a published 0.06–0.15″. An
  effective drizzled PSF near 0.2″ reconciles them exactly. Resolving this needs a field
  containing a star. Until then the generator is calibrated for *detectability* and its width
  is not a physical claim.
- **The colour profile is not monotonic.** The overall gradient has the published sign
  (−0.047 ± 0.021 mag/arcsec, bluer away from the host) but the bin nearest the host bucks
  the trend by ~3σ. Could be contamination from the bright neighbouring galaxy, or a real
  turnover. Unresolved.
- **Fragment linking must raise the false-positive rate** and we still have not measured by
  how much. This is the most valuable outstanding measurement.

### Caveats on the completeness numbers

- One slice: 8.1″ length, one colour, one instrument and depth.
- Injections avoid bright sources, so this is completeness for **uncrowded** sky.
- 44 sites → ±7.5% per point; background realisations are reused across magnitudes, so
  differences *between* curves are more reliable than absolute values. The apparent rise at
  24.8 with clumpiness (27% → 46%) is ~1.9σ: suggestive, not established.
- Transplant noise is conservative by up to √2, so these are lower bounds.

### Bugs found, all by something downstream trying to *use* a value

| Bug | Consequence |
|---|---|
| Provenance card values truncated to 68 chars | Every recorded S3 URI silently became an unusable prefix (`s3://stp`). Found when `fetch-destinations` tried to read one. |
| `fetch_tile` did not check cutout bounds | A negative slice start is not an error in numpy — it counts from the far end — so an out-of-bounds request returned **pixels from the wrong part of the sky** instead of failing. |
| Width from a flux-weighted second moment | Biased high ~7% (0.256 → 0.274″ on RBH-1): clipping negatives leaves background noise contributing weight at large transverse offsets where the lever arm is greatest. |

None would have been caught by a test that merely checked the code ran.

---

## 2026-07-28/29 — Phase 1: the detector

### Recovered geometry

| Quantity | Recovered | Published |
|---|---|---|
| Length (bright section) | 5.50″ | — |
| Host coordinate → far endpoint | **8.10″** | **7.8″** (62 kpc) |
| Width (FWHM) | 0.256″ | 0.06–0.15″ intrinsic |
| Axis ratio | 21.4 | > 50 intrinsic |
| Position angle | 148.3° | — |
| Straightness residual | 0.035″ | slight curvature reported |
| Peak S/N | 13.6 | — |

Applying the [selection window](../adr/0007-target-selection-window.md) to the discovery
field leaves **exactly one** candidate, and it is the right one.

### The published coordinate is the host galaxy, not the feature

It sits 5.5″ from the detection centroid, which looked like a bug for some time. It is
**0.11″ off the feature's own axis** — essentially exactly on it — one feature-length beyond
the end of the section bright enough to detect. Zooming in shows a compact round galaxy
there. So: host at the published coordinate, wake extending ~8.1″ away, terminal knot at the
far end.

### Fragmentation thresholds, measured

| Threshold | Longest recovered |
|---|---|
| 2.5σ | 6.44″ (intact) |
| 3.0σ | 6.43″ (intact) |
| 3.5σ | 6.40″ (intact) |
| **4.0σ** | **3.94″ (fragments)** |

Hysteresis moves this cliff but does not remove it, which is what produced
[ADR-0016](../adr/0016-rejoin-collinear-fragments.md). Linking bridges gaps up to 1.40″ and
cleanly refuses at 1.75″, either side of the 1.5″ tolerance.

### Things that were wrong

**Normalised the ridge response by a median absolute deviation.** The Meijering response is
positive-definite and strongly right-skewed, so its MAD comes out ~35% *larger* than the
sigma-clipped standard deviation — silently making every nominal threshold stricter than it
claimed. Iterative sigma clipping instead.

**Compared fragment axes to each other when linking.** Two parallel lanes offset sideways
have perfectly parallel axes, so the test saw nothing wrong and merged them. Must compare
each fragment to the axis of their **union**, which is noticeably tilted with respect to
either.

---

## Environment gotchas (this machine)

Not science, but each of these cost real time.

- **PowerShell 5.1 corrupts source files.** It reads as ANSI and writes UTF-8-with-BOM, so
  any `Get-Content | Set-Content` round-trip mangles every non-ASCII character. It happened
  once, and the attempted repair made it worse. Python sources are now **pure ASCII**; use
  the editor, never a shell round-trip.
- **MAST's query endpoint is unreliable; its S3 bucket is not.** `find_drizzled_products`
  timed out repeatedly and killed two long jobs. Both fetch commands now resolve URIs from
  the fixture's own provenance, or from explicit `--uri`, and only fall back to MAST.
- **`Select-Object -Last N` on a background command buffers everything** until the process
  exits, so progress cannot be watched. Write to a file inside the script instead.
- **`.ptp()` is gone in numpy 2** — use `np.ptp(...)`.
- **`gh run list --json X --jq '...\(.y)...'`** — PowerShell eats the backslash; keep jq
  expressions to bare field selectors.
