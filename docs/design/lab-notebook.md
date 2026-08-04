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

## 2026-08-04 — Throughput: the sweep is detect-bound, and compute is not the constraint

Timed over the 20 cached tiles, single-process, splitting read from detect:

| | |
|---|---|
| **throughput** | **0.207 deg² per core-hour** |
| **cost** | **$0.21 per deg²** at $0.043/core-hour, egress excluded |
| read | 14% of the time |
| detect | 86% |

**Detect-bound, so the answer to "what do we buy" is cores**, not faster storage or better
compression. Worth knowing before anyone optimises the FITS reader.

Egress is excluded because ADR-0002 puts the compute next to the data. If that ever stops
being true this number stops being the whole cost by a wide margin — pulling tens of TB out
of S3 costs far more than searching it.

### The extrapolation is safe, and was checked rather than assumed

The cached tiles are 20″ cutouts, 0.11 arcmin² each, while a production ACS mosaic is around
a hundred times larger. If per-tile fixed costs mattered, the measured rate would understate
production throughput. Timing detection against tile size:

| side | pixels | seconds per megapixel |
|---|---|---|
| 256 | 65k | 2.19 |
| 512 | 262k | 2.06 |
| 1024 | 1.0M | 2.26 |
| 2048 | 4.2M | 2.34 |

Flat across a 64-fold range, so detection is linear in area and the small-tile rate carries
over. The independent arithmetic agrees: 1 deg² at 0.05″/pixel is 5184 megapixels, which at
2.2 s each is 3.2 core-hours, or 0.32 deg² per core-hour before read and morphology are added.

### What it means for the survey

At this rate the compute for the whole HST extragalactic corpus — of order a few hundred
deg² — is **~1,500 core-hours and under $100**. That is not the constraint on this project,
and it reframes what Phase 3 is for: the sweep is cheap, so the scarce resources are archive
I/O if the compute ever moves away from the data, and human vetting time in Phase 5.

Reported per *core*-hour rather than wall-hour deliberately. The sweep is embarrassingly
parallel over tiles, so wall time is a scheduling choice; quoting it would let the pipeline
look faster merely by adding machines.

---

## 2026-08-04 — The first real sweep, and a published number that had gone stale

`rbh sweep` over the 20 cached control tiles: **264 raw detections, 5 window survivors**, and
re-running it searches nothing and skips all 20 — the Phase 3 gate, working on real sky
rather than in a test.

One of those five is **the real RBH-1**, in `dest_000`: 5.50″ long, axis ratio 21.4, and 5.5″
from the published coordinate, which is exactly the host-galaxy offset Phase 1 established.
So the sweep independently reproduces the litmus result through a completely different code
path, which is worth more than the test that asserts it.

### The number that had drifted

That leaves **4 spurious survivors over the 19 non-RBH-1 tiles**, where the roadmap records
**5**. Small, and exactly the kind of discrepancy that gets waved through as noise.

It is not noise, and chasing it was worth it. Both current code paths — `rbh.controls` and
the new sweep — agree on 4, so the sweep is right and the record was stale. Checking out the
commit that recorded the 5 and re-running it there gives 5, with survivors in dest_008,
**dest_013**, dest_015, dest_016, dest_018. Today dest_013 is gone.

The first suspect was wrong. A refactor of `_measure_width` had changed the degenerate case
from returning a width of exactly 0 — which passes both the width and axis-ratio cuts for
free — to a second-moment fallback. Plausible, and restoring the old behaviour changes
nothing.

The actual cause is `BandImage.background_and_sigma`. The Phase 2 fix restricted the sigma
measurement to pixels near the *median weight*; before it, sigma was measured across the
whole band and so averaged over the weight distribution. That was recorded at the time as
worth under 7% on real archival tiles, and it was fixed because it was free to get right.

**A sub-7% change in the noise normalisation removed 20% of the spurious survivors.**

Every threshold in the detector is denominated in that sigma, so it moves the signal-to-noise
of every pixel at once, and dest_013's candidate was sitting close enough to the line to be
pushed across it. The direction is right — the tighter estimate is the correct one — but the
sensitivity is the finding:

**The window-survivor count is far more sensitive to the noise normalisation than to anything
else measured so far.** Phase 4's gate is a false-positive rate per square degree, and that
number now has to be quoted with the normalisation it was computed under. A detector change
nobody would think of as affecting purity moved it by a fifth.

It also justifies a habit: the roadmap's numbers are not annotations, they are claims, and
this one had quietly stopped being true four commits ago. Corrected there.

---

## 2026-08-04 — Phase 3 opens: the wake limit tracks a tile's own depth to 0.09 mag

Every completeness number this project quotes was conditional on one visit's depth, while
[ADR-0001](../adr/0001-search-the-full-archive.md) commits the search to an archive whose
depth spans orders of magnitude. [ADR-0018](../adr/0018-selection-function-stratified-by-depth.md)
closes that by degrading real tiles: weight scales with exposure, noise as `1/sqrt(weight)`.

Sanity check first — the 5σ point-source limits come out **27.80, 27.41, 27.03, 26.67,
26.29** across exposure fractions 1, ½, ¼, ⅛, 1/16, falling 0.375 mag per halving against a
predicted `2.5 log10(sqrt 2) = 0.376`. The arithmetic is doing what it claims.

### The result worth having

| 5σ point-source limit | wake 50% limit (transplant) | offset |
|---|---|---|
| 27.80 | 24.64 | 3.16 |
| 27.41 | 24.43 | 2.98 |
| 27.03 | 23.98 | 3.06 |
| 26.67 | 23.66 | 3.00 |
| 26.29 | 23.36 | 2.93 |

**The wake 50% limit sits 3.03 ± 0.09 mag brighter than the tile's 5σ point-source limit**,
holding across a sixteen-fold range in exposure. r² = 0.990.

That is what makes the selection function usable as a survey: the 5σ limit is computable
directly from a tile's own weight map, so **completeness can be predicted per tile to about
0.1 mag without running injection–recovery on it**. Without this, Phase 3 would have to
either assume one depth everywhere or run trials on every tile it touched.

A regression gives a slope of 0.88 ± 0.05 rather than 1.00, and the offsets do drift very
slightly downward. Over the 1.5 mag probed the two descriptions are not distinguishable, and
a slope below one should not be extrapolated far outside this range on five points.

### The generator tracks real pixels across depth, not just where it was fitted

Transplant minus parametric 50% limit, by exposure fraction: **+0.02, +0.03, −0.15, −0.10,
−0.04 mag**. Agreement is best at and near the calibration depth, as expected, and never
worse than 0.15 mag anywhere. This is the first evidence that ADR-0017's tier-2 generator is
useful *away* from the single point it was calibrated at — worth having, because the length
and inclination axes rest entirely on it.

### What this measurement is not

**An upper bound, and quoted as one everywhere it appears.** Degrading adds photon noise and
nothing else. Real shallow archival data also carries cosmic-ray residual surviving fewer
dithers, poorer sky subtraction, a worse effective PSF and more surviving artifacts — all of
which make real data *harder* than this. The bound is one-sided in the safe direction, since
overstating completeness understates the space density we can claim, but ADR-0018 records
that validating it against genuinely shallow real tiles is **required, not optional**, once
the manifest exists.

Deeper than the discovery visit cannot be simulated at all: noise can be added, not removed.
The deep end of the axis needs real deep tiles, so the whole relation above is measured
*downward* from a single anchor.

---

## 2026-08-03 — The length grid inverts: reach now peaks near 4 arcsec, not at 16

Re-measured after the profile-shape fix. **The previous version of this grid said the
opposite of the new one**, and the old headline — *"surface-brightness reach improves
monotonically with length, 24.12 at 2.5″ to 25.33 at 16″"* — is superseded.

Completeness (%), injected length against total magnitude, `bright_fraction = 0.72`:

| injected | bright | recovered | 23.0 | 23.8 | 24.4 | 25.0 | 50% limit | SB at 25.0 |
|---|---|---|---|---|---|---|---|---|
| 2.5″ | 1.80″ | 1.96″ | 7 | 7 | 7 | 2 | **< 23.0** | 24.0 |
| 3.0″ | 2.16″ | 2.38″ | 76 | 64 | 45 | 31 | 24.25 | 24.2 |
| 3.5″ | 2.52″ | 2.80″ | 100 | 93 | 79 | 45 | 24.91 | 24.4 |
| **4.0″** | 2.88″ | 3.18″ | 100 | 100 | 93 | 57 | **> 25.0** | 24.5 |
| 6.0″ | 4.32″ | 4.70″ | 100 | 100 | 88 | 40 | 24.88 | 24.9 |
| 8.1″ | 5.83″ | 6.08″ | 98 | 98 | 71 | 19 | 24.65 | 25.3 |
| 12.0″ | 8.64″ | 8.69″ | 98 | 90 | 48 | 12 | 24.37 | 25.7 |
| 16.0″ | 11.52″ | 10.96″ | 98 | 75 | 18 | 10 | 24.06 | 26.0 |

### A hard short-length cutoff, exactly where predicted

A 2.5″ injection presents a **1.80″ bright segment**, below ADR-0007's 2.00″ floor, and
recovers 1.96″ — so it fails the window at *every* brightness, 7% even at magnitude 23.0.
The cutoff sits between 2.5″ and 3.0″ injected, and it is not a detector limit: the feature
is found and then rejected for being too short.

**This cutoff is inherited from a bright fraction measured on one object at one length.**
Whether a 3″ wake devotes the same 72% of itself to bright material as an 8″ one is an
assumption doing real work in the selection function, and it should be stated wherever the
short end of the grid is quoted.

### The relationship is non-monotonic now

Reach peaks around 3.5–4″ and falls away on both sides: short features die on the window
floor, long ones spread their flux too thin. The old grid found monotonic improvement with
length because a monotonic *ramp* concentrated flux at one end regardless of how long the
feature was, which is not what the real object does.

The 8.1″ row — the only length with any anchor to the real object — gives a 50% limit of
24.65, consistent with the 24.58 the transplant gives on the brightness grid.

### A NaN that meant two opposite things

The first version of this table printed "never" for both 2.5″ and 4.0″.
`half_completeness_limit` returns NaN when the curve never crosses 50%, and that happens
for opposite reasons: 2.5″ never *rises* to it, 4.0″ never *falls* to it. One is the worst
row in the table and the other is the best. `describe_half_limit` now reports `< 23.0` or
`> 25.0`, and both cases are pinned by tests.

Also corrected: `mean_surface_brightness` was spreading the flux over the whole injected
length, which stopped being right the moment `bright_fraction` existed. Every figure it
produced was 0.36 mag too faint.

### Gotcha: `mypy src/rbh` is not the gate, `mypy` is

CI went red on a commit whose gates had all passed locally. The cause was running
`uv run mypy src/rbh` — 24 files — where CI runs bare `uv run mypy`, which picks up the
project config and checks **47**, tests included. The failure was in a test file:
`dict[str, tuple[float, ...]]` inferred from a literal does not satisfy
`dict[str, Sequence[float]]`, because `dict` is invariant in its value type.

The lesson is not about variance. **A local gate that is narrower than CI is not a gate**,
and the discipline is to run the exact commands from `CLAUDE.md` — `ruff check .`,
`ruff format --check .`, `mypy`, `pytest -m "not network"` — with no arguments bolted on to
make them faster.

---

## 2026-08-03 — Round 3: discriminability down 2.5x, and confidence carries no information

**15/20, +2.2σ, one-sided p = 0.021**, against 20/20 and +4.5σ in round 2. Reported as
*"so much harder... I still struggled immensely to tell them apart"*.

Raw accuracy is the wrong summary here, because the participant was biased toward calling
things synthetic — 13 synthetic calls against 7 real, on a set that was 10/10.

| | round 2 | round 3 |
|---|---|---|
| accuracy | 100% | 75% |
| hit rate (real called real) | 100% | **60%** |
| false alarms (synthetic called real) | 0% | 10% |
| **d′ (bias-free sensitivity)** | **3.38** | **1.33** |
| criterion c | 0 | +0.43 (leans "synthetic") |

**d′ fell by a factor of 2.5.** That is the honest headline, and it is a much better measure
than the score: it is unaffected by the response bias, which raw accuracy is not.

**Four of the ten real stamps were called synthetic**, against none in round 2. Real RBH-1
pixels now routinely pass for our generator, which is what indistinguishability looks like
from the inside — the failure mode has flipped from "the synthetics are obviously fake" to
"the real one looks fake too".

### Confidence did not track correctness, and that changes the next move

| how sure | stamps | right | rate | |
|---|---|---|---|---|
| guess | 3 | 2 | 67% | +0.6σ |
| leaning | 9 | 8 | 89% | +2.3σ |
| fairly sure | 8 | 5 | 62% | +0.7σ |
| **certain** | **0** | — | — | — |

Two things stand out. **Nothing felt certain** — in a round the participant scored 20/20 on,
every call would have been. And the ordering is *inverted*: the bucket that felt best did
worst (Kendall τ = −0.33, meaningless on three points, but the point is that it is not
positive).

This is exactly the case the confidence scale was built to detect, and it says something the
score cannot: **the residual 2.2σ is not a single nameable cue.** If it were, feeling sure
would mean being right. It doesn't, so there is no point asking for a description this time —
rounds 1 and 2 each produced a tell that traced to a line of code, and this one will not.

That also means the marginal value of another 20-stamp round is low. At n = 20 the standard
error on accuracy is 11 points, which cannot separate 75% from 60%. Resolving whether the
residual is real needs either a much larger round or a different instrument.

### Where that leaves the Phase 2 gate

ADR-0017 asks for accuracy near 50%. **75% is not 50%, and p = 0.021 means the generator is
not yet formally indistinguishable.** That should be stated rather than rounded away.

But it is also no longer the binding constraint on anything. The transplant is the reference
standard and remains the number to quote; the generator now agrees with it on the 50%
completeness limit to **0.16 mag**, which is within the binomial noise on 42 sites. The
parametric numbers were never meant to stand alone, and their disagreement with real pixels
is now smaller than the uncertainty on either.

---

## 2026-08-03 — Recording confidence, because "20/20" threw away most of the data

Yesterday's entry concluded that a repeat participant's score is spent — memorisation and an
unrealistic generator both predict 20/20, so the number cannot separate them. The participant
pushed back: *"I think my score can still inform the generator... there were numerous stamps
last time which I found very hard to differentiate."*

They were right, and the error is worth naming precisely. The argument is sound about the
**aggregate**, and wrong about the **experiment**. Difficulty was not uniform across stamps,
and that variation is exactly what distinguishes the two explanations — recognition of a
memorised object should feel uniformly easy. I had collected one number and thrown away the
twenty judgements that produced it.

Round 3 records **confidence per stamp** on a four-point scale:

| what it looks like | what it means |
|---|---|
| confident **and** correct | a real cue; compare those stamps against the uncertain ones to localise it |
| uncertain | the generator already works here — a positive result, previously invisible |
| uniformly high confidence | the signature of memorisation, now *detectable* rather than assumed |
| accurate but unconfident | the cue is below the level it can be described at; go looking statistically |

The general lesson: **an aggregate is a lossy summary of an experiment, and the loss is
usually the interesting part.** A score of 20/20 and a score of 20/20 with half the stamps
marked "guess" are completely different results, and only one of them says the generator is
in trouble. This is the same shape of mistake as reporting detection and completeness
together, which Phase 2 already learned once and clearly did not generalise.

Round 3 generated with the new profile shape; pre-flight over 200 stamps clean at 0.47, 0.53,
0.48.

---

## 2026-08-03 — The brightness model was the wrong shape, and nobody had ever looked

The fit had driven `tail_brightness` to 0.02 — a trail fading to 2% at one end — in direct
contradiction of a participant reporting that RBH-1's brightness "barely changes". Rather
than believe either, the real object's flux along its own axis was measured. **This had never
been done in the whole project.**

| offset | flux | |
|---|---|---|
| −3.20″ | 0.09 | `####` |
| −2.66″ | 0.74 | `##################################` |
| −2.12″ | 0.51 | `#######################` |
| −1.58″ | 0.39 | `##################` |
| −1.03″ | 0.54 | `#########################` |
| −0.49″ | 0.69 | `################################` |
| +0.05″ | 0.88 | `#########################################` |
| +0.59″ | 1.00 | `##############################################` |
| +1.13″ | 0.41 | `###################` |
| +1.67″ | 0.91 | `##########################################` |
| +2.21″ | 0.93 | `###########################################` |
| +2.76″ | 0.08 | `####` |

Zero at both ends, lumpy and trendless in between — exactly what was reported.

**The generator modelled brightness as a monotonic ramp across the whole length.** That shape
*cannot* put low flux at both ends, whatever its parameters. To make a compact bright region
it had one option: fade one end to nothing. Which is the "shooting star" reported in round 1.
**A single wrong shape had been generating tells for three rounds**, and each round it was
patched somewhere else — a terminal knot removed, a curvature sign randomised, a tail
brightness refitted — because the shape itself was never questioned.

Replaced with a flat-topped window falling to zero on both sides. Mean absolute difference
against the real profile: **0.334 → 0.118**.

### Fit the thing you can measure directly

Those three shape parameters are a least-squares on sixteen numbers — a second's arithmetic.
They had been inferred indirectly, and noisily, through hour-long injection-recovery grids.
That indirection is what let a wrong shape survive: a ramp with an extreme asymmetry produces
roughly the right *recovered length*, so the objective was satisfied while the picture was
wrong. **If a quantity can be read off the data, read it; do not infer it from a downstream
statistic that a wrong model can also satisfy.**

### How much of a fit to believe is itself measurable

The direct fit returns `bright_fraction` 0.65, `edge_power` at whatever upper bound it is
given, and `tail_brightness` 0.20. But the residual scatter inside the bright segment is
**0.242 against a mean residual of 0.118** — the bins are dominated by lumpiness, not by the
smooth shape. So the sixteen numbers support *"falls to zero at both ends over roughly two
thirds of the length"* and nothing more precise. `edge_power` is therefore fixed at a
sensible 8 and deliberately **not** made a fitted axis, and the asymmetry is set to 0.80
rather than the fitted 0.20, which was fitting the lumps.

### What the new shape fixed, and what it did not

| | transplant | before | after |
|---|---|---|---|
| completeness at mag 23.77 | 1.00 | 0.74–0.90 | **1.00** |
| recovered length | 5.61″ | 5.63″ | 5.67″ |
| width | 0.274″ | 0.274″ | 0.274″ |
| fragmentation | 0.86 | 0.95 | 1.00 |

**Completeness now matches exactly, at every point on the grid** — structurally, not by
tuning. That was the entire 0.29 mag pessimism.

`clumpiness` also moved from 0.0 to 0.4. Its previous value had been written into this
notebook as a finding — "most of RBH-1's fragmentation is the threshold cutting a smooth
feature, not intrinsic lumpiness". **That was an artefact of the wrong shape**: a ramp fading
to nothing already fragments constantly, leaving the fit no budget for real knots. With the
correct window the fit wants clumping, which is what the participant described twice.

**Fragmentation is now the one systematic miss**: 0.95–1.00 across the entire grid against a
target of 0.857, so no parameter setting reaches it. It is a ~2σ difference on 42 sites
(42/42 against 36/42) and sits just inside one tolerance unit, so it may be nothing — but it
is the only statistic the model cannot reach, and it should be watched rather than tuned.

### Completeness, remeasured

| | 50% completeness limit |
|---|---|
| **transplant (real pixels)** | **24.58** |
| parametric c = 0.0 | 24.58 |
| parametric c = 0.3 | 24.56 |
| parametric c = 0.6 | 24.62 |
| parametric c = 0.9 | 24.74 |

Worst-case generator-versus-transplant gap **+0.16 mag**, against −0.29 before the shape
change and −0.41 before that, and now on the *optimistic* side rather than the pessimistic
one. Clumpiness spread 0.18 mag. The model and real pixels agree to within the binomial
noise on 42 sites, which is the first time that has been true.

### `length_arcsec` no longer means the length you measure

A test that had passed for weeks began failing: a bright 6″ synthetic came back at **1.57″**
and fell below the window's 2″ floor. Isolating each new default:

| | recovered from a 6.0″ injection |
|---|---|
| calibrated defaults | 1.57″ |
| `bright_fraction = 1.0` | 6.03″ |
| `tail_brightness = 1.0` | 2.79″ |
| path wander off | 4.76″ |
| all roughening off | 6.14″ |
| **at the calibrated width 0.22″** | **4.83″** |

Not a bug. `bright_fraction` means only 72% of the feature carries flux, so a shorter
recovery is the *correct* behaviour — it is how the real object is injected at 8.10″ and
recovered at 5.61″. The test was using a 0.12″ width, far narrower than the fitted 0.22″.

Two things follow, both now asserted in `tests/test_window_diagnostic.py`:

- **`WakeParameters.length_arcsec` is the full extent, not the recovered length.** Anything
  reading it as "what the detector will report" is wrong. The completeness-versus-length grid
  is indexed by the *injected* value, and that grid still needs re-measuring — the
  injected-to-recovered mapping has changed materially with the new shape.
- **`path_wander_arcsec` is absolute, so its effect scales with how narrow the feature is.**
  A 0.14″ wander on a 0.12″-wide feature displaces it further than its own width and breaks
  it up. It was fitted at RBH-1's width and does not scale, so injecting much narrower wakes
  would measure a harsher selection than intended. A limitation of the parameterisation, not
  a defect — but one that Phase 3 must not stumble into unaware.

---

## 2026-08-03 — The most discriminating statistic was the one not being fitted

Refitting with the two round-2 tells addressed dropped the cost from 1.40 to **0.88**, and
fragmentation went from 95% to **86%, exactly the transplant's**. `tail_brightness` moved
0.10 → 0.40, in the direction the debrief predicted. `path_wander_arcsec` came out at 0.10, a
clean interior optimum, with the straightness residual tracking it monotonically — 0.021,
0.026, 0.034, 0.048 against a target of 0.037 — so the new parameter is genuinely
constrained by the new statistic rather than floating.

Then the marginals showed this, at RBH-1's own magnitude:

| | completeness |
|---|---|
| transplant | **1.00** |
| best-fit synthetic | **0.74** |

and, along the `tail_brightness` axis: 0.95, 0.90, 0.81, 0.74, 0.71, 0.64, 0.60.

**Completeness varies by 35 percentage points across the grid at the calibration magnitude,
and it was not in the objective.** The fit was free to trade it away for a slightly better
morphology match, and did.

### The correction

Two days ago this notebook explained the generator's 0.29 mag pessimism by saying the
objective is "evaluated where the answer cannot move" — that completeness saturates at the
calibration magnitude and therefore carries no information. **That was wrong.** It saturates
for the *transplant*, which is the number I looked at; the synthetics span 0.60–0.95. The
mechanism was plausible, it explained the observation, and it was never checked against the
one number that would have falsified it. It then sat in the notebook for two days looking
like a finding.

The real explanation is duller and worse: **the single most discriminating statistic
available was the one excluded from the fit**, and it is the quantity the entire project
exists to report. `completeness` is now in `CALIBRATION_TOLERANCES` at 0.05.

The general form, which is the third variant of the same lesson: a statistic being *absent*
from an objective is invisible, and asking "which parameters does this objective constrain?"
is not enough. The other half is **"which measured quantities is it ignoring, and how much
do they vary?"** Cheap to answer — the numbers were already in every scan file.

### Adding it voided every grid decision made before it

Refitting with `completeness` in the objective **inverted the cost surface**. Along
`tail_brightness`, the previous scan ranked 0.40 best and 0.02 worst; the new one ranks 0.10
best and everything above it monotonically worse — 2.93, 4.91, 5.65, 6.63, 7.61, 6.85.

**Three axes pinned simultaneously** — `tail_brightness`, `width_arcsec`, `width_jitter` —
and every one of them at the bottom of a range trimmed two hours earlier. The trimming had
been argued for explicitly: each axis had a sharp interior minimum with steep sides, so the
outer points looked redundant, and the reasoning was even written into the docstring as
*measurement-justified rather than clock-justified*. It was still wrong.

**A cost surface is a property of the objective, not of the model.** Change the objective and
every measurement used to justify narrowing a grid is void. Two hours of scan results became
worthless the moment a term was added, and the argument for trimming looked exactly as sound
after that as before — nothing about it flagged its own expiry.

Third time the pinning check has caught something it should not have needed to.

### A tension worth watching

The two fits bracket a problem the model may not be able to solve:

| | fragmentation | completeness |
|---|---|---|
| transplant (target) | 86% | 100% |
| fit without `completeness` in the objective | **86%** | 74% |
| fit with it | 95% | **90%** |

The generator can match one or the other, not both. The real object **fragments most of the
time and still passes the selection window every time** — its pieces are bright enough to be
relinked. Ours either fragment as often and lose the faint ones, or stay intact and fragment
too rarely. That is a statement about the model's structure rather than its parameters, and
if the refit on restored grids cannot close it, it should be reported as a limitation rather
than tuned away.

---

## 2026-08-02 — Round 2: 20/20 again, and the test has a shelf life

Round 2 of ADR-0017's blind test: **20/20 again, 4.5σ**, but reported as "MUCH harder".
Every number the project has says the classes are identical — five fitted statistics
matched, and a 200-stamp pre-flight scoring head contrast, width variation and flux
variation at 0.44, 0.47 and 0.46. A human still separates them perfectly.

### The finding that limits the method

> *"Now I know what the actual trail of RBH-1 looks like, I will probably always be able to
> distinguish it."*

**There is only one real object.** Every "real" stamp is the same set of pixels from RBH-1,
rotated by a quadrant, mirrored, and rescaled in flux. After two rounds a participant has
seen it around forty times. The task has quietly stopped being *"is this real or
synthetic?"* and become *"is this the object I have already memorised?"* — and the second
question can be answered perfectly by someone who would fail the first.

This is not a bug to fix. It is a **property of having one example**, and it means:

- **A repeat participant's score is not evidence about the generator** once they have seen
  the template. Their *debrief* still is — a named cue can be checked against the code —
  but the accuracy figure has been spent.
- **The 20/20 does not distinguish** "the synthetics are unrealistic" from "the participant
  recognises one specific object". Both predict the same score.
- The honest reading of round 2 is therefore: *the debrief is data, the score is not.*

What can be done about it, in rough order of cost:

1. **A fresh participant per round.** Cleanest, and the only one that fully restores the
   test. Expensive on a solo project, and there are only so many naive people available —
   each can be used once.
2. **Widen the real class beyond RBH-1** using other real thin structures — edge-on discs,
   tidal tails, satellite trails. They are not wakes, so the test becomes "does this look
   like a real astronomical object" rather than "does this look like a real wake". Weaker,
   but not memorisable and available in quantity.
3. **Score the debrief, not the accuracy.** What is actually being extracted is a named,
   checkable cue; the number was only ever a way of deciding whether to ask for one.

This belongs in ADR-0017 as a stated limitation, because Phase 5's blind vetting has the
same structure and will hit it harder: vetters who see injected positives repeatedly learn
what the injections look like.

### The two tells, and where each one lives

> *"All the synthetic trails still had that linear pattern. No jumps or lumps, or changes in
> direction mid trail, like the RBH-1 has."*

The spine is a **single parabola**. `curvature_arcsec` bends it once, and after round 1 the
sign and vertex were randomised — but a bow is still a bow, and no amount of randomising
*which way* it bows produces a direction change partway along. Added `path_wander_arcsec`,
a deviation drawn over seven nodes and interpolated piecewise-linearly, so the direction
genuinely changes at each node.

Per the rule from yesterday, it needs a statistic or it is another guessed parameter:
`straightness_arcsec` was **already measured** by `rbh.morphology`, already reported in the
litmus table, and had simply never been part of what the fit was asked to match. Now in
`CALIBRATION_TOLERANCES`. That is the **third** distinct instance of the same failure —
a parameter nothing constrained, a parameter the search could not reach, and now a
statistic that existed but was not in the objective.

> *"The brightness along the entire trail... in RBH-1 it seems to barely change, not the
> case in our synthetics."*

`tail_brightness` was fitted to **0.10** — the tail end at a tenth of the tip's brightness,
a tenfold ramp. The description is of something nearly uniform, i.e. a value near 1.0.

**The grid was `(0.02, 0.10, 0.22, 0.40)`. It stopped at 0.40.** The value being described
was never in the search space, and nothing flagged it: the pinning check cannot fire on
0.10 when 0.02 is also scanned, because 0.10 is an *interior* point — of a range that was
in the wrong place. A pinned fit is a range too narrow; this is a range correctly shaped and
wrongly positioned, and only a human looking at the picture found it. Extended to 1.00.

Worth noting the mechanism this may also fix: our synthetics fragment at 95% against the
transplant's 86%, and `clumpiness` fits to 0.0 because more clumping means more
fragmentation. A uniformly bright trail fragments less from faintness, which frees budget
for genuine knots — the lumps that were reported missing. If so, one wrong parameter was
suppressing two separate tells.

The most important entry here, because the error was in the method rather than in a number.

### What happened

The blind-test pre-flight scored width variation at **AUC 0.84** on 20 stamps, so the
generator was changed, the statistic re-measured on the same 20 stamps, changed again, and
so on. Six estimator designs in sequence: four segments then twelve, half-max then second
moment, fixed band then adaptive-from-a-moment then adaptive-from-a-crossing, whole-stamp
extent then feature extent. Readings of 0.84, 0.88, 0.49, 0.65, 0.70, each treated as
evidence about the generator.

**At 10 stamps per class the standard error on an AUC is 0.13.** Those readings are one to
two standard errors apart. Worse, they were all taken against the same 20 stamps while the
estimator was being varied — a garden of forking paths, constructed by me, one fork at a
time. Every individual step looked like careful measurement-driven work.

Re-scored on **200 stamps** (standard error 0.058), with the current generator:

| statistic | real | synthetic | AUC |
|---|---|---|---|
| head contrast | 8.27 ± 14.13 | 11.18 ± 33.29 | 0.44 |
| width variation | 0.180 ± 0.096 | 0.185 ± 0.089 | 0.47 |
| flux variation | 0.786 ± 0.559 | 0.842 ± 0.523 | 0.46 |

**Nothing separates the classes.** All three sit within about one standard error of chance.

### What it changes

The pre-flight now draws **its own sample of 200**, with a different seed from the human
set. Two separate reasons, both learned here:

- **Size.** The human test is capped at 20 because a person has to look at every stamp.
  Nobody looks at the pre-flight's stamps, so its only constraint is a few seconds of
  compute. There was never a reason for it to inherit the human limit.
- **Independence.** Scoring the very set about to be handed over invites tuning until that
  particular set passes. A different seed makes that impossible.

### What was nonetheless real

Not all of the six rounds were noise-chasing; three found genuine defects, and they stand
because each was verified by something other than the AUC:

- the **clip bias** in `(1 + jitter * wobble)`, which made a higher jitter widen the feature
  on average rather than vary it — an inspectable property of the formula, not a statistic;
- the **estimator mismatch**, where the calibration fitted a four-segment half-max while the
  pre-flight scored a twelve-segment second moment, so the objective and the test measured
  different things — a structural fact, confirmed by both estimators on the same stamps
  giving ratios of 1.11 and 1.31;
- **`tail_brightness` pinned** against a bound created by trimming a grid to save time.

The lesson is not "measure less". It is that **a measurement's error bar decides whether it
can be steered by**, and an AUC from 20 samples cannot resolve the differences that were
driving these decisions. The cheap fix — more samples, since no human was involved — was
available from the start.

---

## 2026-08-01 — The refit costs 0.41 mag, and I repeated the terminal-knot mistake

Two findings from the first measurements after the refit, both of which say the generator
is not finished.

### The generator is now 0.41 mag *pessimistic*

| | 50% completeness limit |
|---|---|
| transplant (real pixels) | **24.58** |
| parametric, c = 0.0 / 0.3 / 0.6 | 24.17 |
| parametric, c = 0.9 | 24.24 |

The transplant is unchanged within noise, as it must be — it is the same real pixels. The
generator has moved from **0.14 mag optimistic to 0.41 mag pessimistic**: synthetics are now
*harder* to detect than the real object. Wider features at fixed total flux have lower
surface brightness, and `width_arcsec` went 0.22 → 0.28.

**Why the calibration did not catch it.** ~~The three fitted statistics are measured at
RBH-1's own brightness, 23.77, where completeness is saturated at 100% for every
configuration, so the objective constrains morphology in a regime where the deliverable is
constant.~~

**That explanation was wrong, and it is corrected below (2026-08-03).** Completeness is
saturated at the calibration magnitude for the *transplant*, which is where the claim came
from — but across a later grid the *synthetics* ranged from 0.60 to 0.95 at that same
magnitude, falling monotonically as the brightness ramp steepened. Completeness was strongly
informative all along; it was simply not in the objective. The real answer is the plain one:
**the most discriminating statistic available was the one left out**, and it happens to be
the quantity the project exists to report.

Recorded rather than deleted because the failure mode is worth keeping: a plausible
mechanism was asserted as the explanation without checking the number that would have
falsified it, and it then sat in the notebook for two days looking like a finding.

Note which way this cuts. A pessimistic generator makes the published limits conservative
rather than overstated, so it is the safer of the two errors — but "safe" is not "measured",
and the transplant remains the number to quote.

**Final state after the width-variation work and the refit** (`tail_brightness` 0.10,
`clumpiness` 0.0, `width_arcsec` 0.22, `width_jitter` 0.8):

| | 50% completeness limit |
|---|---|
| **transplant (real pixels) — the number to quote** | **24.58** |
| parametric, c = 0.0 | 24.40 |
| parametric, c = 0.3 / 0.6 / 0.9 | 24.29 / 24.32 / 24.32 |

Worst-case generator-versus-transplant gap **−0.29 mag**, down from −0.41, and the
clumpiness spread is **0.11 mag** — now reported as the separate quantity it always was.
The generator is still mildly pessimistic and that is still unexplained by the calibration,
which is evaluated at a brightness where completeness is saturated. Quote the transplant.

### A reporting bug that would have hidden it

The CLI printed one line, `spread across clumpiness`, computed over **every** source
including the transplant. It conflated two different questions: how much the assumed
clumpiness matters, and whether the generator agrees with real pixels at all. With the old
numbers both were small and the label passed unnoticed. With these numbers it would have
reported a 0.07 mag clumpiness spread and a 0.41 mag model-versus-real disagreement as a
single "0.41 mag across clumpiness" — reading as *clumpiness matters a lot*, the precise
opposite of the truth. Now reported separately, with the gap highlighted when it exceeds
0.25 mag.

The earlier headline, "varies by only 0.14 mag across the full clumpiness range", was
therefore mislabelled too. It was conservative — the true clumpiness-only spread was smaller
— so the conclusion drawn from it stands, but the attribution was wrong.

### The blind-test pre-flight, and the same mistake again

Before spending a person's attention on round 2, three statistics targeting the round 1 tells
were measured on the stamps and scored by rank-sum AUC against the answer key (0.5 = no
separation):

| statistic | real | synthetic | AUC |
|---|---|---|---|
| head contrast | 9.5 ± 6.6 | 11.8 ± 18.1 | 0.59 — fixed |
| flux variation | 1.15 ± 0.27 | 1.08 ± 0.36 | 0.62 — fine |
| **width variation** | **0.19 ± 0.03** | **0.14 ± 0.04** | **0.84 — separates** |

The "shooting star" head is gone. But real wakes vary in width along their length more than
the generator does, strongly enough that a person could beat chance on that cue alone.

**`width_jitter = 0.45` was set by guesswork and no statistic constrains it** — exactly the
terminal-knot failure, repeated within an hour of the lesson being written down. Fixing a
guessed parameter by guessing a better value is not a fix. The generator's width variation
has to enter the calibration objective so the fit is forced to match it.

**The rule, stated so it stops recurring:** *any property a person could use to tell the
classes apart must be a measured statistic in the calibration objective.* Adding a parameter
to the generator without adding the statistic that constrains it recreates this failure every
single time. `Morphology.width_variation` is now measured, is a calibration term, and
`width_jitter` is fitted.

### Making the parameter fitted exposed two more defects

**The jitter axis pinned at the top of its grid, and that was a real bias.** The width was
`width_sigma * (1 + jitter * wobble)`, clipped from below at `0.35 * width_sigma` to keep it
positive. Above jitter ≈ 0.65 that clip bites on *every* negative excursion: the narrowing
saturates while the widening keeps growing, so **turning the parameter up quietly made
features wider on average rather than more variable** — and the fit had chosen 0.8, squarely
inside that regime. A width is a positive quantity, so its natural scatter is multiplicative:
now `width_sigma * exp(jitter * wobble)`, where `exp(+j)` widens by exactly the factor
`exp(-j)` narrows. No clip, no bias, and `width_jitter` reads as a log-width scatter — 0.6
means the width swings by a factor of about 1.8 either way.

**`tail_brightness` pinned against a bound I had created myself.** Adding the jitter axis
quadrupled the grid, so the tail range was trimmed from four values to three to keep the run
short — and the fit immediately strained against the new bottom. A self-inflicted instance of
exactly what the pinning check exists to catch. The excuse for it evaporated the moment
trials went parallel: breadth is cheap now, and the grids are wide again.

Successive costs as each of these was fixed: **1.84 → 1.68 → 1.53**.

### The pre-flight is now automatic

`rbh blind-test` runs it every time and prints the AUCs, rather than leaving it to be
remembered. The one time it *was* left to be remembered, a set at AUC 0.84 came within a
message of being handed to a person. The margin is 0.28 from 0.5 — about two standard errors
at 20 stamps, loose enough not to fire on noise and tight enough to catch a usable cue.

Both halves are tested: it must catch a planted width tell, and it must stay silent when both
classes are drawn identically. A check that never fires is decoration; one that always fires
teaches its reader to skip it, which is how the pinning warning's first version failed.

This is also the pre-flight's argument for existing: it is not a substitute for the human
test — a machine misses what a person sees, which is how round 1 happened — but the converse
is cheap. If a one-number summary separates the classes, the set has a tell and there is no
point running the human test yet.

---

## 2026-08-01 — Recalibration after the blind test, and a 9× faster measurement loop

### The generator, refitted

Rerun against the transplant with the four blind-test fixes in place. All three fitted
statistics land inside tolerance:

| | length | width | axis ratio | fragmentation |
|---|---|---|---|---|
| transplant (target) | 5.61″ | 0.274″ | 20.4 | 86% |
| generator (best fit) | 5.50″ | 0.298″ | 18.2 | 95% |
| tolerance | 0.40″ | 0.025″ | — | 0.15 |

Combined cost 1.84, of which width contributes 0.96 — nearly its whole budget. Width is
the tightest constraint and remains the one to watch.

New fitted defaults, and **the changes are large**, which is the honest measure of how
much the old fit was absorbing the defects:

| parameter | was | now | why it moved |
|---|---|---|---|
| `tail_brightness` | 0.02 | **0.22** | the old value faded one end almost to nothing, which with the terminal knot at the other end made the "shooting star" |
| `width_arcsec` | 0.22 | **0.28** | `width_jitter` narrows the feature over part of its length, so the base has to grow to hold the measured width |
| `clumpiness` | 0.1 | **0.0** | the new width and brightness variation already break the feature up |

### The fit was pinned, and nothing would have said so

The first rerun put `width_arcsec` at 0.28 — **the largest value in the grid**. A fit on
the edge of its search range is not the best fit, it is the best *available*, and the true
optimum may lie outside. It is a nasty failure mode because it looks exactly like success:
every reported statistic sat inside tolerance while the parameter strained against a bound
that had been chosen by guesswork.

Extending the grid to 0.40 and re-running: **the answer did not change.** 0.28 is a genuine
interior optimum; 0.34 and 0.40 are worse. So the concern was right to raise and is now
settled by measurement rather than by assumption.

`CalibrationResult.is_pinned` now detects this and the CLI prints a warning, so it cannot
happen silently again. This is the same lesson as the terminal knot, one level up: there,
a parameter no statistic constrained; here, a parameter the search could not reach.

**The check's first version was wrong**, and usefully so. It fired immediately on
`clumpiness=0.0` — but zero clumpiness is a *physical floor*, a perfectly smooth feature,
not an arbitrary bound that could be widened. A warning that fires on a correct answer is
worse than no warning, because it teaches the reader to skip it. `PHYSICAL_FLOORS` now
exempts the bottom of a range that has nothing below it, while still flagging the top of
that same parameter.

### Speed: 9× on the measurement loop

The gates were never the bottleneck. Measured, on this machine:

| | time |
|---|---|
| full test suite | ~75 s |
| ruff + mypy | ~25 s |
| CI, all four jobs in parallel | ~1 min |
| **one calibration run** | **~20 min** |

Two changes, both of which leave every number bit-identical:

1. **`_matches` measured everything and used the centroid.** It called
   `morphology.measure` — width profile, spine binning, endpoints, position angle — once
   per fragment and again per linked detection, roughly twenty times a trial, then read two
   of the twelve fields. The full measurement is wanted exactly once, for the winner.
   Computing only the centroid: **17% off every trial**.
2. **Trials now run across cores** (`rbh.parallel`). This is safe for a specific reason
   worth stating: each trial seeds its own generator as `seed + index`, so no trial can
   observe another and execution order cannot matter. Had the seeding been sequential —
   one generator threaded through the loop — parallelising would have silently changed
   every measured number, and would have been a change to the science rather than to the
   plumbing. `tests/test_parallel.py` asserts serial and parallel agree exactly rather than
   leaving that as an argument.

Measured together: **96 configurations in 5.7 min, against 48 in 20 min serially** — 3.6 s
per configuration against 25 s, a **7× speedup** on 14 workers, plus the 17%. Not 14×
because the batch does not divide evenly across workers and each task pickles its tile
across.

Two things learned about the pool, both Windows-specific:

- **Spawned workers re-import `__main__`.** A script without an `if __name__ == "__main__"`
  guard fork-bombs and the pool dies with `BrokenProcessPool`. The installed `rbh` command
  is fine; ad-hoc scripts calling into `rbh.studies` are not, unless guarded.
- **pytest's `filterwarnings = ["error"]` does not reach into worker processes.** A warning
  raised in a worker would print rather than fail the run. Hence `MIN_ITEMS_FOR_POOL`: small
  batches stay inline, which keeps the unit tests single-process where that check still
  bites, and the pool only engages for measurement runs where it earns its keep.

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
