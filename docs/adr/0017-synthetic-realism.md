# ADR-0017 — Anchor synthetic realism on transplanted real pixels

**Status:** Accepted

**In plain terms:** Our completeness number is only as trustworthy as the fake wakes we
measure it with, and a fake built from a formula is always smoother than the real thing.
So the primary fake is not a model at all: it is the actual RBH-1 pixels, cut out and
pasted elsewhere. A formula-based generator still exists, because we need shapes RBH-1
does not cover, but it only counts as realistic once it reproduces what the transplanted
real object does.

## Context

[ADR-0009](0009-injection-recovery.md) makes injection–recovery the mechanism by which
this project produces knowledge: completeness over a known area is what turns "we found
nothing" into a space-density limit. That makes the realism of the injected sources the
load-bearing assumption of the entire result. If the synthetics are easier to find than
real wakes, completeness comes out too high, the limit comes out too tight, and we
overclaim.

**The bias has a known direction, and we have already measured it.** A parametric wake is a
smooth ribbon. Real wakes are chains of clumps joined by faint bridges — which is precisely
why RBH-1 fragments into three pieces at a 4-sigma cut and needs
[ADR-0016](0016-rejoin-collinear-fragments.md) to survive. A smooth synthetic would never
fragment, so it would never pay the linking penalty, so it would report a completeness that
no real wake could achieve. This is not a hypothetical failure mode; it is the specific
thing we watched happen to the one real object we have.

Other ways a model can be unrepresentative, with the direction each biases:

| Unrealism | Effect on measured completeness |
|---|---|
| Smooth instead of clumpy | **too high** — never fragments |
| Uniform brightness instead of a bright terminal knot | too low — no strong pixel to seed hysteresis |
| Gaussian PSF instead of the real one | either way, depending on wing strength |
| No curvature | slightly too high — passes straightness cleanly |
| Injected into blank sky instead of real fields | **too high** — no real blending or confusion |
| Modelled at one morphology only | unknown — the population's spread is unconstrained |

Note that these do not all push the same way, so we cannot reason our way to a correction
factor. An empirical anchor is required.

One thing is already handled: injection happens into **real archival tiles**, so the
background, its correlated noise, real neighbours, real blending and real artifacts all
come for free. Only the *source* needs modelling, which halves the problem.

## Decision

Realism is established in three tiers, each validating the next.

### Tier 1 — Transplanted real pixels (the reference standard)

The primary injected source is **RBH-1 itself**: its pixels, background-subtracted, with
neighbours masked, pasted into other real sky. No morphological model, no assumptions about
clumpiness, brightness profile, PSF or colour.

Handled explicitly:

- **Its own noise comes with it.** Pasting adds the template's noise on top of the
  destination's, so a transplant at matched depth is noisier than a real source there by up
  to √2. This makes transplant completeness a **lower bound** on the truth, which is the
  conservative direction for an upper limit — a property worth keeping rather than
  correcting away.
- **Rescaling flux to probe the brightness dependence needs a noise correction.** Scaling a
  transplant by `f` scales its carried noise by `f` too, so faint injections would arrive
  proportionally *cleaner* than bright ones and the completeness curve would acquire a
  spurious brightness-dependent tilt. Adding compensating noise of variance `(1 − f²)σ²`
  makes the carried noise `σ` regardless of `f`.

    To be precise about what this does and does not achieve: it makes the penalty a
    **constant offset rather than a slope**. It does not remove the penalty — the injected
    source still sits in sky noisier than a real one by up to √2 — and it cannot, since the
    template's noise is inseparable from its pixels. Constant-and-conservative is
    interpretable; sloped is not.
- **Rotation is restricted to multiples of 90°** where possible, so no interpolation
  smoothing is introduced; other angles are permitted but flagged, and the smoothing
  measured.
- **Resampling** is used to probe angular size, and to port the template to other pixel
  scales for Euclid and Roman ([ADR-0013](0013-survey-agnostic-io.md)).

Limitation, stated plainly: this gives us one morphology. It cannot tell us how much real
wakes vary.

### Tier 2 — Parametric generator, validated against Tier 1

A parameterised generator is still needed for shapes RBH-1 does not cover: other lengths,
widths, inclinations, and above all other degrees of clumpiness.

**Clumpiness is a first-class axis of the completeness grid, not a fixed choice.** We have
demonstrated that it controls fragmentation, and fragmentation controls whether an object
passes the selection window at all.

Its acceptance test is concrete and falsifiable: **set the generator's parameters to
RBH-1's values, and it must reproduce the transplant's recovery statistics** — not merely
the same length, but the same fragmentation rate, the same measured width, the same peak
signal-to-noise distribution, and the same colour gradient. A generator that cannot
reproduce the one real object we have is not evidence about anything.

### Tier 3 — Report completeness as conditional, with sensitivity

With N = 1 we genuinely cannot know the population's morphology distribution, and no amount
of care changes that. So:

- **Never publish a single completeness number.** Publish
  C(μ, L, W | clumpiness, profile shape) and the derived limit as a function of those
  nuisance parameters.
- **Publish how far the limit moves** across the plausible range of morphology assumptions.
  If it is stable to within a factor of two, that is a strong result and should be said. If
  it moves by an order of magnitude, that is the headline caveat, not a footnote.

### Two cheap checks that catch what statistics miss

- **Blind human discrimination.** Mix synthetic and real cutouts and ask a person which is
  which. If they can tell, the synthetics are not representative — regardless of what any
  summary statistic says. This tests "representative" more directly than any metric we
  could construct, and costs an afternoon.
- **Full feature-distribution comparison.** Compare the whole measured feature vector from
  synthetics against the real object, not just whether it was detected. Matching detection
  rates while mismatching measured widths would mean the generator is right by accident.

## Amendment, 2026-07-30 (Phase 2 calibration outcome)

The Tier 2 gate was run. It worked, in the sense that it caught the generator being wrong,
and three things came out of it that were not anticipated above.

**1. The parameters are not independent, so tuning them one at a time is invalid.** The
first attempt fitted tail brightness, then clumpiness, then width, in sequence. Widening a
feature at fixed total flux lowers its peak surface brightness, so less of it clears the
threshold and the recovered length drops - the width step silently undid the length match,
taking recovered length from 6.4 to 3.8 arcsec against a 5.6 arcsec target. Calibration is
now a single joint grid against a combined objective over recovered length, measured width
and fragmentation rate.

**2. Uncalibrated, the generator was substantially too easy to find.** At RBH-1's
brightness the transplant is recovered at 5.6 arcsec with axis ratio ~19; the initial
parametric guess gave 8.3 arcsec and axis ratio ~35. It also looked obviously wrong: too
smooth and too uniformly bright, and a person could pick it out of a mixed set at a glance.
That is the blind-discrimination check failing before it was formally run, and it is exactly
the direction of bias this ADR was written to prevent.

**3. Most of RBH-1's fragmentation is not intrinsic clumpiness.** The fitted clumpiness is
0.0-0.2, where 0.6 had been assumed. A nearly smooth feature at this surface brightness
already fragments about 65-80% of the time, because the threshold cuts it wherever noise
dips. Clumpiness remains a real axis of the grid - fragmentation rises monotonically with it,
reaching 100% by 0.6 - but at RBH-1's brightness it is a second-order effect behind the
noise. That is a correction to the reasoning in the Context above, which attributed
fragmentation primarily to lumpiness.

**Fitted defaults** (`rbh.synthetic.WakeParameters`): `tail_brightness=0.02`,
`clumpiness=0.1`, `width_arcsec=0.22`.

**4. The completeness turns out to be nearly insensitive to clumpiness - which is the whole
worry defused.** Measured over 44 injection sites in 11 real tiles, the 50% completeness
limit is:

| Source | 50% limit (F606W, AB) |
|---|---|
| Transplanted real pixels | 24.61 |
| Parametric, clumpiness 0.0 | 24.60 |
| Parametric, clumpiness 0.3 | 24.68 |
| Parametric, clumpiness 0.6 | 24.69 |
| Parametric, clumpiness 0.9 | 24.74 |

A spread of **0.14 mag across the entire plausible range** of the one morphological property
we cannot constrain from a single object.

Read the *spread*, not the ordering. Those limits happen to increase monotonically with
clumpiness here, and that is not significant: a half-sample rerun reproduces the small
spread but scrambles the order. Only the smallness is established. Fragmentation over that same range climbs from
about 68% to 100%, so clumpiness is doing exactly what was expected to the *detector* - the
reason it barely reaches the *catalogue* is that collinear fragment linking
([ADR-0016](0016-rejoin-collinear-fragments.md)) absorbs it.

That is a stronger result than this ADR set out to obtain. The Tier 3 requirement to publish
completeness as a function of clumpiness still stands, but the honest summary is now that the
derived space-density limit is robust to the morphology assumption at the 0.15 mag level,
rather than hostage to it.

**A degeneracy that must not be misread.** The fitted intrinsic width of 0.22 arcsec sits
well above the published 0.06-0.15. It is degenerate with the effective PSF of the drizzled
products, which cannot be measured from the discovery cutout because there are no stars in
it - the only compact objects are 175-215 pixel galaxies, which measure their own sizes, not
the PSF. An effective drizzled PSF near 0.2 arcsec would reconcile the two exactly. The
consequence: the generator is calibrated for **detectability**, and its width parameter is
not a physical claim about wake widths. Separating the two needs a field with a star in it.

## Amendment, 2026-08-01 (the blind test failed)

The blind discrimination check listed above as one of the "two cheap checks that catch what
statistics miss" was run. **A participant scored 20 out of 20, 4.5 sigma above chance.** The
synthetic wakes were trivially distinguishable from transplanted real pixels.

The generator had been fitted to reproduce four measured statistics of the real object and
did reproduce all four. It still looked obviously wrong at a glance. The prediction in this
ADR - that a person "uses everything at once, including whatever we forgot to measure" - held
exactly, and the cheap check earned its place.

Three generator defects and one flaw in the test itself were identified from the
participant's description, each traceable to a specific line: a terminal knot bright enough
to read as a "shooting star" head, a constant-width ribbon where real wakes are irregular, a
spine bend whose sign was fixed in code so every wake bowed the same way, and transplants
that were never rotated and so all carried RBH-1's own position angle. All four are fixed;
details in the lab notebook.

**Consequences for the measurements.** The transplant-based numbers are untouched - they are
real pixels, which is the entire reason this ADR made them the reference standard. The
parametric numbers are optimistic, by an amount the existing grid already bounds: 27% against
30-46% at magnitude 24.8, with the 50% limits still agreeing to 0.14 mag. The length grid has
no transplant anchor and must be re-measured after recalibration.

**The lesson worth carrying beyond this project.** An unconstrained parameter left at a
guessed value is invisible to a fit and obvious to a human. The terminal knot was not
measured by any of the four statistics, so the calibration was free to leave it wrong, and it
turned out to be the loudest signal in the image. For any fitted model: ask which parameters
the objective actually constrains, and what is carrying the rest.

## Amendment, 2026-08-01 (recalibrated, and a second way a fit can lie)

Refitted against the transplant with the four blind-test fixes in place. All three fitted
statistics land inside tolerance — 5.50″ against 5.61″, 0.298″ against 0.274″, 95%
fragmentation against 86% — at a combined cost of 1.84, of which width contributes 0.96.
Width remains the binding constraint.

The fitted parameters moved a long way, which measures how much the old fit had been
absorbing the defects: `tail_brightness` 0.02 → **0.22**, `width_arcsec` 0.22 → **0.28**,
`clumpiness` 0.1 → **0.0**.

**A second failure mode, caught this time by the code rather than by eye.** The first rerun
put `width_arcsec` on the largest value in the grid. A fit at the edge of its search range
is not the best fit but the best *available*, and it is dangerous precisely because it
presents as success: every statistic inside tolerance, while the parameter strains against a
bound chosen by guesswork. Extending the grid to 0.40 and re-running left the answer
unchanged, so 0.28 is a genuine interior optimum — the concern was real and is now settled
by measurement.

`CalibrationResult.is_pinned` now reports this and the CLI warns on it. Note this is the
same lesson as the terminal knot one level up: there, a parameter that no statistic
constrained; here, a parameter the search could not reach. Both are ways for a fit to be
confidently wrong while every number it reports looks fine.

The check's first version flagged `clumpiness=0.0`, which is a *physical floor* rather than
an arbitrary bound — a perfectly smooth feature, with nothing below it to widen towards. A
warning that fires on a correct answer trains the reader to ignore it, so `PHYSICAL_FLOORS`
now exempts such a floor while still flagging the top of the same parameter.

**Still outstanding:** the length grid, which has no transplant anchor, and a second round
of the blind test. Neither the recalibration nor the pinning check tells us whether the
synthetics now *look* right; only a person can, which is the whole argument of this ADR.

## Amendment, 2026-08-01 (the pre-flight, and making the same mistake twice)

Round 2 was generated and **not handed over**. Three statistics targeting the round 1 tells
were measured on the stamps and scored by rank-sum AUC against the key:

| statistic | real | synthetic | AUC |
|---|---|---|---|
| head contrast | 9.5 ± 6.6 | 11.8 ± 18.1 | 0.59 — fixed |
| flux variation | 1.15 ± 0.27 | 1.08 ± 0.36 | 0.62 — fine |
| **width variation** | **0.19 ± 0.03** | **0.14 ± 0.04** | **0.84 — separates** |

The shooting-star head was gone; the width irregularity was not. **`width_jitter` had been
set to 0.45 by eye, and no statistic constrained it** — the terminal-knot failure repeated
within an hour of the lesson being written into this ADR. Fixing a guessed parameter by
guessing a better value is not a fix.

**The rule this establishes.** Any property a person could use to tell the classes apart has
to be a *measured* statistic in the calibration objective. Adding a parameter to the
generator without adding the statistic that constrains it recreates the failure every time.
`Morphology.width_variation` now measures the coefficient of variation of the width along a
feature, it is a calibration term, and `width_jitter` is fitted rather than assumed.

**Two further defects surfaced by doing that.** The jitter axis pinned at the top of its
grid, which turned out to be a genuine bias rather than a missing grid point: the width was
`width_sigma * (1 + jitter * wobble)` clipped from below to keep it positive, and above
jitter ≈ 0.65 that clip bit on every negative excursion, so the narrowing saturated while the
widening kept growing. Turning the parameter up quietly made features *wider on average*
instead of more variable, and the fit had walked straight into that regime. Width is a
positive quantity, so the scatter is now multiplicative — `width_sigma * exp(jitter *
wobble)`, where `exp(+j)` widens by exactly the factor `exp(-j)` narrows, with no clip.
Separately, `tail_brightness` pinned against a bound created by trimming the grid to keep a
run short — a self-inflicted instance of the very thing the pinning check exists to catch,
and one with no excuse now that trials run across cores.

**The pre-flight is now part of `rbh blind-test` and runs automatically.** It does not
replace the human test and cannot: a machine misses what a person sees at a glance, which is
how round 1 happened. Its value is the converse. If one number separates the classes, the set
has a tell and there is no point spending a person's attention on it. It runs automatically
rather than on request because the one time it was left to be remembered, a set with an AUC
of 0.84 came within a message of being handed over.

## Amendment, 2026-08-01 (the pre-flight needs its own, larger sample)

That 0.84 did not survive contact with a decent sample size. The pre-flight had inherited
the human test's 20 stamps, where the standard error on an AUC is **0.13** — and six
successive estimator designs were steered by readings of 0.84, 0.88, 0.49, 0.65 and 0.70,
all taken against the *same* 20 stamps while the estimator itself was being varied. A garden
of forking paths, one fork at a time, each step looking like careful measurement-driven work.

Re-scored on 200 stamps, standard error 0.058: head contrast 0.44, width variation 0.47,
flux variation 0.46. **Nothing separates the classes.**

Two changes follow, and both are now properties of `rbh blind-test`:

1. **The pre-flight draws its own sample, defaulting to 200.** The human set is small
   because a person looks at every stamp; nobody looks at these, so there was never a reason
   for the limit to carry over.
2. **It uses a different seed from the set being handed over.** Scoring the very set about to
   be given to a person invites tuning until that particular set passes.

This does not weaken the ADR's central claim — a summary statistic is no substitute for a
human — but it adds a corollary. **A check is only as good as its error bar**, and a check
too coarse to resolve the differences it is being used to decide between is worse than none,
because its noise reads as signal. Three of the six rounds did find genuine defects; those
stand because each was confirmed by something other than the AUC, and they are recorded in
the lab notebook alongside the ones that were not.

## Consequences

- Phase 2 gains a transplant machinery step before the parametric generator, so the
  [roadmap](../design/roadmap.md) order is: transplant, then generator, then completeness
  grid. The generator cannot be validated before the transplant exists.
- Completeness will come out **lower** than a naive smooth-ribbon estimate. That is the
  correction working, not a regression.
- The published limit becomes a family of limits with a stated dependence, which is less
  quotable and more honest.
- The transplant becomes a permanent reference standard. If the detector is ever retuned,
  transplant recovery is re-measured, which keeps the generator from drifting along with
  the detector.
- Real cost: masking neighbours out of the RBH-1 template is fiddly and somewhat
  subjective, and errors there propagate into every completeness number. The masked
  template must be committed and inspected, not regenerated silently.

## Alternatives considered

- **Parametric generator only.** Much less work and the obvious default. Rejected: its
  realism would be unverifiable, and the one bias we can already identify inflates
  completeness in exactly the direction that would make us overclaim.
- **Transplant only.** Fully empirical and beautifully assumption-free, but limited to one
  morphology, so it cannot say anything about wakes that look different from RBH-1 — and it
  cannot probe the clumpiness axis at all, which we know matters most.
- **Physically-derived generator** from the shock and star-formation physics: clump mass
  function, spacing set by cooling timescales, ages giving colours. More defensible in
  principle, and the right long-term answer. Rejected for now as a large modelling project
  whose extra assumptions would themselves need validating against the same single object.
- **Report completeness marginalised over an assumed morphology prior.** Produces one
  quotable number, but hides the assumption doing the work inside a prior nobody can check.
