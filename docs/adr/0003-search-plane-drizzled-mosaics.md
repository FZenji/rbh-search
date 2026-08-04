# ADR-0003 — Search drizzled, CR-rejected, Gaia-aligned mosaics

**Status:** Accepted

**In plain terms:** Telescopes take several photos of the same spot and combine them. Real
things in space appear in every photo; cosmic rays and satellites appear in only one, so
the combining software already throws them out. By searching the combined images instead of
the raw ones, we get most of our glitch-removal for free. Best value decision in the
project.

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

## Amendment, 2026-07-28 (Phase 1)

The Context above assumes HAP Single-Visit Mosaics are available from the cloud copy.
**They are not, or at least not universally.** Resolving cloud URIs for the RBH-1
discovery visit returned "unable to locate file" for every
`hap/public/.../hst_16912_02_acs_wfc_f606w_jety02_drc.fits` path, while the standard
association products `s3://stpubdata/hst/public/jety/jety02010/jety02010_drc.fits` were
present and readable.

The Decision is unchanged, because the association products are drizzled, cosmic-ray
rejected, and carry the weight and context arrays we need — everything the decision
actually relies on. What we lose is HAP's uniform Gaia DR3 re-registration, so astrometric
provenance now varies with each programme's original solution. The manifest must therefore
record which product type each tile came from, and Phase 3 should re-check HAP cloud
coverage across the archive rather than generalising from one visit.

## Amendment, 2026-08-04 (drizzling removes cosmic rays, not every artifact)

The first scan of sky outside RBH-1's own field found the limit of what this decision buys.

Drizzled, cosmic-ray-rejected products do exactly what the name says: they remove features
that appear in one exposure and not the others. **They do nothing about artifacts present in
every exposure** — saturation bleed trails and diffraction spikes around bright sources
combine straight through, arriving in the search plane as perfectly linear, high-contrast,
high-axis-ratio features. Which is to say: as the thing this pipeline is looking for.

Measured on the first two products searched. One bright elliptical galaxy produced **76 of
84 candidates**, piled within about 23″ of it, with a median nearest-neighbour separation of
3.08″. The best-scoring feature in the field measured 39.01″ long at axis ratio 109 and peak
S/N 202; RBH-1 measures 5.5″ at axis ratio 21. Candidate position angles cluster in the
streak direction, 18 of 76 in one 15° bin against 6.3 expected.

Nothing here overturns the Decision — drizzled products remain the right search plane, and
searching individual exposures would be far worse. What changes is the **claim made about it
downstream**: that artifacts were "largely handled" by this choice. That was true of the
artifact class this ADR names and was generalised to all of them, including in `CLAUDE.md`'s
list of things most likely to be got wrong, which asserted the opposite of what the data
show. Corrected there.

The consequence for Phase 4 is an ordering one. Artifact rejection around bright sources has
to come **before** wake-versus-disc scoring ([ADR-0008](0008-scored-discriminants-not-cuts.md)),
because a candidate list that is three-quarters one galaxy's diffraction spikes cannot be
usefully vetted and no amount of morphological scoring addresses it. `bright_source_mask`
already exists and fires on the saturated core; it does not reach the spikes radiating beyond
it.

## Alternatives considered

- **Individual `flc`/`cal` exposures.** Maximum information and full control over
  rejection. Rejected: it means re-solving a problem the archive has already solved well,
  and it multiplies the data volume and the contaminant rate.
- **Both planes.** Run on drizzled products, then re-examine candidates in the individual
  exposures. Rejected for v1 as unnecessary complexity — but this is the right *escalation*
  path for a small number of high-value candidates, and is recorded as a Phase 5 tool.
