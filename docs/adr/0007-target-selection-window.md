# ADR-0007 — Fix the target selection window explicitly

**Status:** Accepted

## Context

Every threshold in a search pipeline is a claim about what the pipeline can and cannot
find. Leaving them implicit — buried as magic numbers in detector code — makes the
selection function unknowable and the catalogue uninterpretable.

The window has to be derived from something. We have exactly one calibrator, RBH-1, plus
a physical model that lets us extrapolate from it.

**Angular length.** RBH-1 is 62 kpc at z = 0.964, where the scale is ~8.0 kpc arcsec⁻¹, so
7.8″. Wakes of 20–150 kpc over 0.4 < z < 2 span roughly 2.5″ to 25″.

**Width.** RBH-1 is 0.5–1.2 kpc, i.e. 0.06–0.15″ — at or below the ACS PSF. A generous
ceiling of 0.6″ admits genuinely wider or lower-inclination wakes while still excluding
ordinary galaxies.

**Redshift bounds.** Above z ≈ 2, (1+z)⁻⁴ surface-brightness dimming makes an RBH-1
analogue ~5× fainter per unit area than at z = 1. Below z ≈ 0.3, a 62 kpc wake subtends
> 25″, is likely to be broken across tiles or masked as a galaxy, and the volume in a
~15 deg² footprint is small.

**Straightness.** Counter-intuitively, this is an *upper* bound on straightness as well as
a limit on curvature. RBH-1 shows slight but real curvature. A perfectly straight feature
is more likely a diffraction spike, a chip edge or a trail than a wake.

## Decision

The selection window is defined **once**, in `rbh.config.SelectionWindow`, versioned, and
hashed into every output row. Defaults:

| Parameter | Value | Basis |
|---|---|---|
| `min_length_arcsec` | 2.0 | ~20 kpc at z ≈ 1 |
| `max_length_arcsec` | 25.0 | ~150 kpc at z ≈ 0.4; also the tile overlap width |
| `max_width_arcsec` | 0.60 | 5× RBH-1's width; excludes ordinary galaxies |
| `min_axis_ratio` | 8.0 | Deliberately loose at detection; RBH-1 is > 50:1 |
| `max_straightness_residual_arcsec` | 0.35 | Admits real curvature, excludes wildly curved tidal features |
| `min_ridge_snr` | 5.0 | Standard detection threshold, on the noise-normalised response |

Every one of these is a tunable whose effect on completeness is **measured**, not asserted
([ADR-0009](0009-injection-recovery.md)). Changing any of them changes the settings
fingerprint and therefore marks the catalogue as coming from a different survey.

The [target signature](../science/target-signature.md) page states in plain language what
this window makes us blind to; that page is part of the published product.

## Consequences

- Anyone can compute what this pipeline could and could not have found, from the config
  alone.
- The window is deliberately looser at detection than at ranking. It is cheaper to detect
  generously and discriminate carefully ([ADR-0008](0008-scored-discriminants-not-cuts.md))
  than to cut hard early and never know what was thrown away.
- We are explicitly not sensitive to: non-star-forming wakes (nothing to see in
  broadband), z ≳ 2, z ≲ 0.3, near-end-on geometries, and wakes superimposed on bright
  extended galaxies. Injection–recovery quantifies each.
- Tuning the window against RBH-1 risks over-fitting to N = 1. Mitigated by keeping the
  window generous and by validating on synthetics spanning a much wider parameter range
  than RBH-1 occupies.

## Alternatives considered

- **No explicit window; rank everything.** Maximally inclusive. Rejected: computationally
  unbounded, and it merely moves the implicit selection into the ranking function where it
  is harder to see.
- **Tighter window matched closely to RBH-1.** Higher purity, but over-fits to one object
  and would make any resulting density limit apply only to RBH-1 clones.
- **Physical rather than angular units.** Attractive, but requires a redshift per candidate
  before we have one. Angular units are what the detector actually measures; physical
  conversion happens after a host redshift is associated.
