# ADR-0008 — Score the wake-vs-disk discriminants, do not cut on them

**Status:** Accepted

**In plain terms:** Instead of a rule that says "reject this, keep that", we measure lots of
properties and give each candidate a score. Why? Because expert astronomers argued for
three years over whether RBH-1 was a black hole wake or an edge-on galaxy, using better
data than we'll have. We're not going to settle that with a threshold. So we keep
everything, record every measurement, and rank — which also means someone who disagrees
with our ranking can redo it without re-running the whole search.

## Context

The dominant astrophysical contaminant is the **bulgeless edge-on disk galaxy**. This is
not a hypothetical: it is the interpretation that was published against RBH-1 in 2023,
supported by deep HST imaging in 2024, and only overturned by JWST spectroscopy in 2026.
For three years the field could not decide, using better data than we will have.

That history is the argument. If the world's experts could not settle it with deep
broadband imaging, **no threshold we write will settle it either**. Any hard cut we apply
is a decision made with less information than the people who got it wrong.

We do have real discriminants (see [false positives](../science/false-positives.md)), and
some are strong — particularly the absence of a rest-frame NIR counterpart, since a wake
has no old stellar population and a disk galaxy does. But each is individually defeasible:
a dusty or genuinely young edge-on disk can be NIR-faint; a wake projected onto a
background galaxy can look NIR-bright.

## Decision

Stage 6 produces a **feature vector and a calibrated score**, never a verdict.

Recorded features include, at minimum:

- rest-UV to rest-NIR flux ratio along the feature
- longitudinal profile asymmetry (monotonic vs centrally peaked)
- sign and monotonicity of the colour gradient along the axis
- transverse colour structure (presence of a central dust lane)
- terminal-knot contrast and which end it sits at
- vertical (transverse) profile shape and its constancy along the length
- host-galaxy anchor cross-match, with photo-z consistency
- counter-feature search result on the opposite side of the host
- curvature and its sign

Weights are **fitted**, not hand-tuned: positives from synthetic injection
([ADR-0009](0009-injection-recovery.md)), negatives from real edge-on disk galaxies drawn
from existing morphological catalogues. The resulting ROC curve is published with the
catalogue.

Candidates are **ranked**, and the ranking threshold is set by the human inspection budget
([ADR-0011](0011-human-vetting-protocol.md)) rather than by a purity target. Every
discriminant's individual value is stored, so a future reader who disagrees with our
weighting can re-rank the catalogue without re-running the sweep.

Hard cuts remain acceptable for **instrumental** vetting, where the signature is
deterministic and the physics is not in dispute.

## Amendment, 2026-07-30 (first measurement of the features)

The feature vector now exists (`rbh.discriminate`) along with a harvester for its negative
class (`rbh.negatives`), and the features have been measured against real objects for the
first time: 29 recovered RBH-1 transplants versus 9 elongated galaxies harvested from the
control tiles.

**Three of the four features behave differently from their design.** Only the transverse
colour dip discriminates in the intended direction. Terminal-knot contrast discriminates in
*reverse* — galaxies have bright centres and score higher — and longitudinal asymmetry does
not discriminate at all, because only the bright middle of a wake is detected and that part
is roughly symmetric. The full table is in the lab notebook and in the `WakeFeatures`
docstring, which now records measured power rather than intended power.

This is the Decision working as designed. Because the features are stored rather than cut on,
discovering that one runs backwards costs nothing: it re-weights, it does not invalidate a
catalogue. Had these been hard cuts, two of the four would have been actively removing the
wrong objects.

**The features do separate the spurious linking joins from both real classes** — filling
factor 0.80 against 1.00, asymmetry 0.15-0.18 against 0.03-0.04, knot contrast 2.3-5.8 against
1.5-1.8. That matters because a geometric gap cut could not
([ADR-0016](0016-rejoin-collinear-fragments.md) amendment): scoring solves a problem cutting
could not, which is this ADR's central claim, tested.

**Two limits worth stating plainly.** The negative sample is nine objects at axis ratio
3.1-4.5, considerably rounder than the ratio >= 8 the selection window demands, so it is not
yet representative of real contaminants; 2.1 arcmin^2 of sky does not contain many thin
edge-on discs, and a proper sample needs Phase 3 area. And the discriminant this ADR rates
highest, the rest-frame near-infrared counterpart, is **not computable in this field at all**:
both filters are optical and at z ~ 1 even F814W samples rest-frame ~4100 A. No weights have
been fitted and no threshold set.

## Consequences

- Nothing is thrown away on an astrophysical judgement call. Low-scoring candidates persist
  in the catalogue with their features intact.
- The catalogue is re-rankable by anyone, which is the honest response to a genuinely
  unsettled classification problem.
- Storage cost is higher — full feature vectors for every stage-4 survivor. This is cheap
  relative to the pixel processing that produced them.
- The score is only as good as the synthetics behind its positive class, which puts the
  realism of the wake generator on the critical path.
- Some real wakes will rank below some edge-on disks. Publishing the ROC curve makes that
  cost explicit rather than hidden.

## Alternatives considered

- **Hard cuts on each discriminant.** Simple, fast, and produces a short clean list.
  Rejected on the RBH-1 history: the prototype would plausibly have been cut by a
  reasonable-looking rest-NIR or symmetry threshold.
- **Binary classifier with a single decision boundary.** Same objection, plus it discards
  the individual feature values that make re-ranking possible.
- **Defer all discrimination to human vetting.** Rejected: unmeasurable, unreproducible,
  and it puts thousands of edge-on disks in front of a human who will stop looking
  carefully by stamp 200.
