# ADR-0018 — Stratify the selection function by depth, measured by degrading real tiles

**Status:** Accepted

**In plain terms:** Our completeness number was measured on one visit at one depth, but the
archive we are about to search is wildly uneven — some sky has one orbit on it, some has
hundreds. A wake we would find easily in the deep parts may be invisible in the shallow
ones, so a single completeness number would be wrong nearly everywhere. We therefore measure
completeness separately in bands of depth, and we simulate the shallow end by adding noise to
the data we already have rather than downloading more.

## Context

[ADR-0001](0001-search-the-full-archive.md) commits us to the whole public extragalactic
archive and states plainly that "depth is wildly non-uniform across the corpus… the selection
function must be evaluated as a function of depth". [ADR-0009](0009-injection-recovery.md)
makes the selection function the thing that turns a null result into a publishable limit.

Phase 2 delivered exactly one slice of it: ACS/WFC, F606W + F814W, at the depth of the RBH-1
discovery visit — one orbit per filter. Every completeness figure the project currently
quotes, including the headline 50% limit of 24.58, is conditional on that depth and says so
nowhere outside the lab notebook.

This is the largest gap between what has been measured and what Phase 3 is about to assume.
Sweeping the corpus without it produces candidate counts that cannot be converted into a
space density, which is the entire deliverable.

Two ways to get depth into the measurement:

1. **Fetch genuinely shallower and deeper real tiles** and repeat injection–recovery in each.
2. **Degrade the tiles we have**, adding noise to simulate fewer exposures.

## Decision

**Completeness is reported in bands of effective depth, never as a single number**, and the
depth axis is measured by *degrading real tiles* — option 2 — with the limits of that
approximation stated wherever the numbers appear.

Degradation is well defined by the drizzle convention already relied on throughout — see
`BandImage` in `src/rbh/tile.py` — where weight is proportional to effective exposure time
and pixel noise scales as `1/sqrt(weight)`. To simulate a fraction `f` of the exposure, scale the
weight by `f` and add independent Gaussian noise of variance `sigma^2 (1/f - 1)` per pixel,
drawn against the tile's own noise map. Total flux is untouched; only the noise changes.

**Depth is expressed as a limiting magnitude, not as an exposure time.** Exposure time is not
comparable across instruments, filters or epochs — the same 1000 seconds buys very different
depth on ACS/WFC and NIRCam — and the corpus spans all of them. The point of the axis is to
predict detectability, so it is indexed by the quantity that does.

## Consequences

- **Degrading captures photon noise and nothing else.** Real shallow data also has more
  cosmic-ray residual, poorer sky subtraction, fewer dithers and hence a worse effective PSF,
  and more surviving artifacts. Every one of those makes real shallow data *worse* than our
  simulation of it, so **the depth-degraded completeness is an upper bound**, and it must be
  quoted as one. This is the main cost of choosing option 2 and it is not a small one.
- The bound is one-sided and in the safe direction for a null result: overstating our own
  completeness understates the space-density limit we can claim.
- It costs no network and no new archive products, so the axis can be measured now rather
  than after the Phase 3 manifest exists. Given that the manifest depends on knowing which
  depths are worth including, that ordering matters.
- Nothing validates the simulation against genuinely shallow real data. **Phase 3 must close
  that loop once the manifest exists**: pick real tiles at a measured shallower depth, run the
  same trials, and compare. If they disagree, this ADR's numbers are the ones that move.
- The noise model this rests on is independently checked: `rbh.controls.noise_model_scatter`
  holds the `1/sqrt(weight)` relation to within 7% across a hundred-fold range in weight.
- Deeper than the discovery visit cannot be simulated this way at all — noise cannot be
  removed. The deep end of the axis needs real deep tiles, and until it has them the
  selection function is measured downward from one anchor only.

## Alternatives considered

- **Fetch real tiles across the depth range (option 1).** Strictly better science: it captures
  the systematics degradation cannot. Rejected as the *first* step only because it needs the
  Phase 3 manifest to choose tiles by depth, and the depth axis is needed to decide what the
  manifest should include — a circularity broken by simulating first and validating later.
  It remains required, not optional.
- **One completeness number for the whole corpus.** Rejected: it is wrong nearly everywhere,
  and wrong in an unknown direction, which forfeits ADR-0009's argument entirely.
- **Index depth by exposure time.** Rejected: not comparable across instruments or filters,
  and the corpus is heterogeneous in both.
- **Assume completeness scales with signal-to-noise analytically**, sidestepping measurement.
  Rejected for the reason the project keeps rediscovering: the selection window is a cascade
  of thresholds and cuts, and its response to noise is not something to be derived on paper
  when it can be measured. The length grid inverted the last time an analytic expectation was
  trusted over a measurement.
