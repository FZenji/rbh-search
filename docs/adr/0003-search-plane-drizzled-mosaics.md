# ADR-0003 — Search drizzled, CR-rejected, Gaia-aligned mosaics

**Status:** Accepted

## Context

The search could operate on individual calibrated exposures (`flt`/`flc`, `cal`) or on
drizzled, combined products (`drz`/`drc`, level-3 mosaics, HAP SVM/MVM).

Individual exposures preserve maximum information and let us do our own artifact
rejection. But they carry every cosmic ray, every satellite trail, and every asteroid —
which is to say, they carry precisely the contaminant population that most closely mimics
our target signature.

Drizzled multi-exposure products get rid of that population **for free**. AstroDrizzle's
cosmic-ray rejection compares dithered exposures in a common sky frame: anything present
in only one exposure is rejected. A real sky feature is fixed in sky coordinates and
survives dithering; a cosmic ray, satellite trail or moving asteroid is not and does not.

This is the single highest-leverage false-positive decision available, and it costs
nothing to take.

Additionally, **HAP Single-Visit and Multi-Visit Mosaics** give the entire HST archive in a
uniformly reprocessed form with modern distortion models, uniform pixel scales, and
**alignment to Gaia DR3** — on a PS1-like tessellation of 4.2° projection cells subdivided
into 0.2° sky cells. Consistent astrometry across thirty years of heterogeneous programmes
is otherwise a project in itself.

## Decision

The search plane is **archive-grade drizzled, cosmic-ray-rejected, Gaia-aligned mosaics**:

- HST: **HAP SVM and MVM** products, preferring MVM where a field has multiple visits
  (multi-visit coverage enables the cross-visit roll-angle test, the strongest artifact
  discriminant available).
- JWST: calibrated **level-3 NIRCam mosaics**, preferring survey **HLSPs** where the
  team's mosaic is demonstrably better than the pipeline default.

We do **not** reprocess raw exposures. We do read the associated **weight/exposure and DQ
arrays**, which are required for noise normalisation and for the exposure-count test.

## Consequences

- Cosmic rays, satellite trails and asteroid trails are largely eliminated before our code
  runs. The residual artifact problem is dominated by *static* artifacts — diffraction
  spikes, detector-frame scattered light, edges — which have deterministic geometric
  signatures and are far more tractable.
- We inherit the archive's processing decisions, including any drizzle kernel smoothing.
  Correlated noise in drizzled products means the effective noise is not the naive
  per-pixel sigma; **this must be calibrated empirically by injection–recovery, not
  assumed**.
- Fields with a single usable exposure get no CR rejection at all. These must be flagged
  from the weight map and either excluded or heavily deprioritised.
- Theoretical risk: could drizzle CR-rejection clip a *real* thin feature? No — real
  features are fixed in sky coordinates across dithers, which is exactly the condition CR
  rejection tests for. Worth asserting once via injection into pre-drizzle exposures, then
  never worrying about again.
- Astrometry is Gaia-aligned, so candidate positions are good to well under 0.1″ and are
  directly usable in follow-up proposals.

## Alternatives considered

- **Individual `flc`/`cal` exposures.** Maximum information and full control over
  rejection. Rejected: it means re-solving a problem the archive has already solved well,
  and it multiplies the data volume and the contaminant rate.
- **Both planes.** Run on drizzled products, then re-examine candidates in the individual
  exposures. Rejected for v1 as unnecessary complexity — but this is the right *escalation*
  path for a small number of high-value candidates, and is recorded as a Phase 5 tool.
