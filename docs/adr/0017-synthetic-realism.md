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
  transplant by `f` scales its noise by `f` too, which would make faint injections
  unrealistically clean. Compensating noise of variance `(1 − f²)σ²` is added so the total
  matches what a source of that brightness would actually carry.
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
