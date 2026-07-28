# ADR-0013 — Abstract the I/O layer for Euclid and Roman

**Status:** Accepted

**In plain terms:** All the telescope-specific details — pixel sizes, filter names, file
layouts — live in one isolated part of the code. Everything else just sees "an image".
That way, pointing this at Euclid's 1,900 square degrees in October is a small job instead
of starting over. Euclid is where we actually expect to find something; Hubble is where we
prove the method works.

## Context

The HST + JWST archive gives us ~15–20 deg². That is where the one known positive lives,
so it is where the method must be calibrated. It is not where the yield is.

| Survey | Availability | Area |
|---|---|---|
| HST + JWST archive | now | ~15–20 deg² |
| Euclid Q1 | public since 23 Mar 2025 | 63.1 deg² |
| **Euclid DR1** | **21 Oct 2026** | **~1900 deg²** |
| Roman | launched 30 Aug 2026 | eventually thousands of deg² |

Euclid DR1 alone is ~100× the v1 survey area, and Euclid VIS at 0.1″ pix⁻¹ comfortably
resolves and detects an RBH-1 analogue — an ~8″ feature at μ ≈ 23.5 mag arcsec⁻² is far
above VIS's surface-brightness limit. Van Dokkum et al. name Euclid and Roman as "the
obvious datasets to look for these features in a systematic way".

DR1 lands **in under three months**. A pipeline that hard-codes HST conventions will not be
ready; one with a clean survey adapter boundary will be.

## Decision

Everything survey-specific lives behind a **survey adapter** interface. The detection,
morphology, vetting, discrimination, injection and reporting stages know nothing about
which telescope produced the pixels.

The adapter owns:

- Manifest construction (archive query, footprints, filters, depth, S3 URIs)
- Tile assembly (WCS, pixel scale, reprojection)
- PSF model
- Photometric calibration and zero points
- Weight/exposure and DQ array conventions
- Instrument-specific artifact geometry (diffraction-spike pattern, detector-frame masks)
- Filter → rest-frame band mapping for the colour discriminants

Everything downstream consumes a **normalised tile object**: science array, noise map,
exposure-count map, WCS, PSF, per-band zero points, and provenance.

Adapters ship for HST (ACS/WFC, WFC3/UVIS, WFC3/IR) and JWST (NIRCam) in v1. Euclid and
Roman adapters are Phase 6 work, and the interface is designed against them now — not
retrofitted later.

## Consequences

- Some abstraction cost is paid in v1 for a benefit that arrives in Phase 6. Accepted
  deliberately, on the timing above.
- Adding a survey means: write an adapter, re-derive the PSF and pixel scale, **re-run
  injection–recovery**, and re-tune the discriminator. Not a rewrite — but also not free,
  and pretending otherwise would be dishonest. The selection function is survey-specific
  and must be measured per survey.
- The interface must not leak HST assumptions. Concretely: no assuming 0.05″ pixels, no
  assuming a `SCI`/`WHT`/`CTX` extension layout, no assuming filter names of the form
  `F###W`.
- Euclid Q1 (63 deg², public now) is available as a low-risk shakedown for the Euclid
  adapter well before DR1 arrives. Recommended in the [roadmap](../design/roadmap.md) if
  Phase 3 completes before October.
- Roman data will not be science-ready for some time after launch; treat it as a later
  target than Euclid DR1.

## Alternatives considered

- **Build for HST only, port later.** Simplest now. Rejected on the DR1 date — "port
  later" reliably means "rewrite in a hurry".
- **Build for Euclid first.** Maximum area immediately. Rejected: Euclid contains no known
  positive, and calibration against RBH-1 must come first
  ([ADR-0010](0010-rbh1-regression-test.md)).
- **A fully generic astronomical image framework.** Over-engineering. The abstraction is
  scoped to exactly the four surveys named above and no further.
