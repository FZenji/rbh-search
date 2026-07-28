# ADR-0001 — Search the full HST + JWST archive, not just deep fields

**Status:** Accepted

**In plain terms:** RBH-1 was easy to spot in a short, ordinary exposure. So we don't need
the famous long-exposure "deep field" images — we need *lots* of images. Searching only the
deep fields would throw away about 90% of our available sky for no benefit.

## Context

The instinct when hunting faint extragalactic structure is to go to the deep fields. That
instinct is wrong here, and the evidence is in the discovery itself.

RBH-1 was found in **one orbit** (~2400 s) of HST/ACS in each of F606W and F814W. Its
integrated magnitude is F814W = 22.87, giving a mean surface brightness of roughly
23.5–24 mag arcsec⁻². In a single-orbit ACS image that is a **high signal-to-noise
detection**, not a marginal one — van Dokkum's team spotted it by eye and initially
mistook it for a cosmic ray precisely because it was so obvious.

The consequence is arithmetic:

- Deep fields (JADES, CEERS, PRIMER, COSMOS-Web, NGDEEP, HUDF/HLF) total ~1–2 deg².
- The full usable extragalactic HST archive is ~10–12 deg² (an archival lens search
  measured ~7 deg² of ACS/WFC in 2012), plus ~2–4 deg² of JWST NIRCam.
- HST has imaged ~0.1% of the sky in total.

Restricting to deep fields discards **roughly 90% of the searchable area** in exchange for
depth the target signature does not require.

Going deeper does extend sensitivity to intrinsically fainter or higher-redshift wakes.
But surface-brightness dimming goes as (1+z)⁻⁴, and the confusion limit against edge-on
disk galaxies rises faster than the signal does. Depth is not where the marginal detection
comes from; area is.

## Decision

The v1 production sweep covers **every public, drizzled, extragalactic imaging mosaic** in
the HST (ACS/WFC, WFC3/UVIS, WFC3/IR) and JWST (NIRCam) archives, restricted to Galactic
latitude \|b\| > 20° and excluding crowded fields. Deep fields are processed as a subset,
not as the target.

The unique sky area of that corpus, computed as a MOC union, is published as a first-class
data product — it is the denominator of every density limit we derive.

## Consequences

- The corpus is tens of TB, forcing the compute-next-to-data decision
  ([ADR-0002](0002-compute-next-to-the-data.md)) and tile-based work units
  ([ADR-0004](0004-work-unit-is-a-sky-tile.md)).
- Depth is wildly non-uniform across the corpus. Detection thresholds must be normalised
  by the local noise from the weight map, never globally, and the selection function must
  be evaluated as a function of depth.
- Filter coverage is heterogeneous, which forces the tiering in
  [ADR-0006](0006-two-tier-filter-requirement.md).
- We inherit thirty years of instrument-specific artifacts rather than the well-characterised
  handful in a few curated fields. This is the price, and
  [false positives](../science/false-positives.md) is where it is paid.

## Alternatives considered

- **Deep fields only.** Simpler manifest, uniform depth, well-characterised artifacts,
  existing high-quality HLSP mosaics. Rejected: ~10× less area for sensitivity we do not
  need.
- **HST only.** Simpler, and it is where the known positive lives. Rejected: JWST NIRCam
  adds area *and* the rest-NIR bands that power the best wake-vs-disk discriminant.
- **Add Euclid Q1 (63 deg²) immediately.** Tempting — it is public and quadruples the
  area. Deferred to Phase 6 because Q1 contains no known positive to calibrate against,
  and calibration must come first. See [roadmap](../design/roadmap.md).
