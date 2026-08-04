# ADR-0019 — The survey denominator is effective area, not sky area

**Status:** Accepted

**In plain terms:** To turn "we found none" into "there are fewer than N of these per unit
volume", you divide by how much sky you searched. But a patch with one orbit on it and a
patch with twenty are not equally searched — we would miss a faint wake in the first and
find it in the second. So the number we divide by is not raw sky area; it is sky area
weighted by how likely we were to find the thing, which depends on brightness. Raw area is
still published, because it is what everyone else quotes and it is needed to check our work.

## Context

[ADR-0001](0001-search-the-full-archive.md) makes the unique sky area of the corpus, as a MOC
union, "a first-class data product — it is the denominator of every density limit we derive".
[ADR-0009](0009-injection-recovery.md) makes a null result publishable only because
injection–recovery measures what we would have found.

Those two commitments are in tension, and until now the tension was hidden because the
project had a single completeness number. [ADR-0018](0018-selection-function-stratified-by-depth.md)
removed that excuse: completeness varies systematically across the corpus, and we now know
by how much. The wake 50% limit sits 3.03 ± 0.09 mag brighter than a tile's own 5σ
point-source limit, so a sixteen-fold spread in exposure moves it by 1.3 mag.

Dividing by raw sky area therefore treats sky we searched well and sky we barely searched as
equivalent. For a null result that inflates the denominator and understates the limit — the
safe direction, but wrong, and wrong by an amount that varies with the source brightness
being constrained.

The corpus also overlaps itself heavily. The same sky is observed repeatedly at different
depths, in different filters, across thirty years.

## Decision

**The published denominator is effective area as a function of source magnitude:**

```
A_eff(m) = sum over tiles of  area_i * C(m | depth_i)
```

where `C(m | depth_i)` is the completeness at magnitude `m` for a tile of that depth, taken
from the ADR-0018 relation rather than from trials on every tile. Raw unique sky area
continues to be published alongside it, unchanged, because it is the comparable number and
because the ratio of the two is a useful description of the survey.

**Where sky is covered more than once, the effective area uses the deepest coverage of that
sky and counts it once.** Shallower duplicates add no area and would only lower the average
if averaged in.

**Duplicate coverage stays in the manifest.** It is not searched for area, but repeat visits
of the same sky are the only way to run the cross-visit artifact control that Phase 2 could
not — a real feature appears in both epochs and a detector artifact does not. Deduplicating
at the manifest level would throw that away permanently.

## Consequences

- **The space-density limit becomes a curve, not a number**, since `A_eff` depends on
  magnitude. That is the honest form: we constrain bright wakes better than faint ones, and a
  single number would have hidden which.
- Every tile needs a measured depth. This is cheap — it comes from the weight map — and is
  the reason ADR-0018 was worth doing before the manifest rather than after.
- `A_eff <= A_raw` always, with equality only where completeness is 1. Publishing both makes
  the weighting auditable rather than buried in a pipeline.
- **The bound inherits ADR-0018's one-sidedness.** The depth relation is an upper bound on
  completeness, so `A_eff` is an upper bound, so the density limit derived from it is a lower
  bound on how constraining we can claim to be. Consistent, and in the safe direction, but it
  must be quoted that way.
- Selecting the deepest coverage requires the overlap geometry, not just per-tile depth: two
  observations may overlap partially. The MOC machinery ADR-0001 already commits to handles
  this, at the cost of the accounting being per-MOC-cell rather than per-tile.

## Alternatives considered

- **Raw unique sky area alone.** What ADR-0001 originally implied and what most such searches
  quote. Rejected now that the variation is measured: it weights a one-orbit tile equally
  with a twenty-orbit one, and the error varies with the magnitude being constrained, so it
  cannot even be corrected with a single factor afterwards.
- **A depth cut — discard sky shallower than some threshold.** Simpler, and it makes a single
  completeness number defensible again. Rejected: it throws away real area for no reason
  other than bookkeeping convenience, and the threshold would be arbitrary. Effective area
  already down-weights shallow sky continuously and correctly; a cut is the crude version of
  the same idea.
- **Coadd overlapping visits to a common deeper mosaic.** Tempting, and it would genuinely
  increase depth. Rejected for v1: coadding changes the PSF, the noise correlation and the
  artifact population, and the entire selection function was measured on drizzled products
  with the properties ADR-0003 fixed. A coadd is a different search plane and would need its
  own calibration from scratch. Worth revisiting once the v1 sweep is done and the cost is
  known.
- **Report completeness-weighted counts instead of a weighted denominator.** Algebraically
  equivalent for a simple limit, but it hides the weighting inside the numerator where it
  cannot be checked, and it breaks as soon as anyone wants the area for a different purpose.
