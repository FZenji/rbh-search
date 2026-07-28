# ADR-0009 — Injection–recovery is mandatory; the selection function is a deliverable

**Status:** Accepted

**In plain terms:** We secretly paste realistic fake wakes into the real telescope images,
then see how many our program finds. If we hide 1,000 and it finds 700, we know it catches
about 70% of what's really out there. That single number is what turns "we found nothing"
from a shrug into a real scientific result: *"there are fewer than X of these per patch of
sky."* This is the most important decision in the project.

## Context

The likely outcome of this search is **zero confirmed detections**. The archive is small
(~15–20 deg²), the phenomenon is rare enough that one example was found serendipitously in
thirty years, and confirmation requires spectroscopy we do not have.

A search that finds nothing and cannot say what it would have found produces no
information whatsoever. A search that finds nothing but has a **measured completeness over
a known sky area** produces an upper limit on the space density of star-forming SMBH wakes
— which is a real, citable, falsifiable result, and which directly predicts the yield of
Euclid DR1 and Roman.

The difference between those two outcomes is injection–recovery. It is not a validation
nicety; it is the mechanism by which this project generates knowledge.

There is a second, more immediate argument. Drizzled mosaics have **correlated noise** —
the drizzle kernel means the effective noise is not the naive per-pixel sigma. Any
analytic sensitivity estimate on such data is wrong by an unknown factor. The only
reliable way to know the detection threshold is to inject sources and count how many come
back.

## Decision

**Injection–recovery is a required component, not an optional test.** No detector change
merges without re-measuring the selection function.

Mechanics:

- A parameterised synthetic wake generator: length, intrinsic width, surface brightness,
  colour gradient, curvature, terminal-knot contrast, inclination, host-galaxy anchor.
- Sources are convolved with the **tile's actual PSF** and given correct per-band fluxes.
- Injection happens **before stage 2**, into real archival pixels, so injected sources
  experience every subsequent cut — detection, morphology, artifact vetting, MRT
  cross-check, discrimination — exactly as a real source would.
- Injection is seeded and reproducible ([ADR-0012](0012-reproducibility-contract.md)).
- Injection density is kept low enough not to perturb background statistics or to create
  synthetic blends.
- Completeness is measured on a grid: C(μ, L, W, band, depth, inclination, local
  background), separately per tier ([ADR-0006](0006-two-tier-filter-requirement.md)).

**Realism gate:** an injected RBH-1 analogue placed in the real GO-16912 field must recover
the same measured parameters as the real RBH-1. If the generator cannot reproduce the one
object we have, its completeness numbers are fiction.

The selection function is **shipped with the catalogue** as a first-class data product,
alongside the survey MOC, so that anyone can derive a density limit independently.

## Consequences

- Significant implementation effort before any sweep runs — this is Phase 2 of the
  [roadmap](../design/roadmap.md), ahead of Phase 3 scaling, deliberately.
- Compute cost rises: injection runs alongside the real sweep over the same tiles.
- A null result becomes publishable. This is the entire point.
- The synthetic generator's realism becomes a critical dependency, and its limitations must
  be documented as honestly as the completeness it produces.
- Injected positives are reused for the human vetting measurement
  ([ADR-0011](0011-human-vetting-protocol.md)) and as the positive class for the
  discriminator ([ADR-0008](0008-scored-discriminants-not-cuts.md)) — one investment,
  three returns.

## Alternatives considered

- **Analytic sensitivity estimate.** Cheap. Rejected: invalid on correlated-noise drizzled
  data, and it cannot capture the cascade's morphology and vetting cuts at all.
- **Completeness from the RBH-1 recovery alone.** N = 1 gives a single point, not a
  function.
- **Injection after detection** (into the candidate list rather than the pixels). Much
  cheaper, but measures only the ranking stage and misses everything the detector and
  vetting throw away — which is where most of the incompleteness lives.
