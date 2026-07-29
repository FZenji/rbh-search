# Roadmap

Each phase ends with a gate that must pass before the next begins. The gates are the
point; the phases are just what fits between them.

---

## Phase 0 — Foundation ✅

Repository, tooling, and the documentation you are reading. Decisions recorded as ADRs
before any science code exists.

**Gate:** lint, types, tests and docs build green in CI.

---

## Phase 1 — Litmus ✅

Prove the concept on the one object we know about, entirely offline.

**Gate met:** `pytest -m litmus` passes offline and deterministically, 9 assertions.

What the pipeline recovers from the discovery data:

| Quantity | Recovered | Published |
|---|---|---|
| Length | 5.50″ (bright section) | — |
| Host coordinate → far endpoint | **8.10″** | **7.8″** (62 kpc) |
| Width (FWHM) | 0.27″ | 0.06–0.15″ intrinsic, ACS PSF ≈ 0.1″ |
| Axis ratio | 20 | > 50 intrinsic |
| Position angle | 148.3° | — |
| Straightness residual | 0.035″ | slight curvature reported |
| Colour gradient | −0.047 ± 0.021 mag/arcsec, bluer away from host | bluest at tip, reddening toward host |

Applying the ADR-0007 selection window to the field leaves **exactly one** candidate.

Three things were learned that changed the design:

1. The published coordinate is the **host galaxy at one end** of the wake, not its centre.
   It sits 0.11″ off the recovered axis — essentially exactly on it.
2. HAP single-visit mosaics are **not in the cloud** for this visit; standard association
   products are ([ADR-0003 amendment](../adr/0003-search-plane-drizzled-mosaics.md)).
3. Hysteresis alone does not keep a knotty feature intact, which produced
   [ADR-0016](../adr/0016-rejoin-collinear-fragments.md).

---

## Phase 2 — Measurement

Build the thing that makes the project scientific rather than anecdotal. Order matters
here: the generator cannot be validated before the transplant exists
([ADR-0017](../adr/0017-synthetic-realism.md)).

1. **Transplant machinery.** Cut RBH-1 out — background-subtracted, neighbours masked,
   template committed and inspected — and paste it into other real sky. Flux rescaling with
   the `(1 − f²)σ²` noise compensation; rotation at 90° multiples; resampling for other
   pixel scales.
2. **Parametric generator**, PSF-convolved, multi-band, with **clumpiness as an explicit
   parameter** since it controls fragmentation and therefore survival.
3. **Validate the generator against the transplant**: at RBH-1's parameters it must
   reproduce the transplant's fragmentation rate, measured width, peak S/N and colour
   gradient — not merely its length.
4. **Completeness grid** over (μ, L, W, inclination, depth, background, clumpiness),
   separately per tier.
5. **Negative controls**: noise realisations, rotated and mirrored tiles, known-artifact
   fields, labelled edge-on disks as the discriminator's negative class.
6. **Blind human discrimination check**: can a person tell synthetic cutouts from real
   ones? If yes, the synthetics are not representative yet.

**Gate:** the parametric generator reproduces the transplant's recovery statistics at
RBH-1's parameters, and the completeness grid is reported as a function of clumpiness rather
than at one assumed value.

### Gate met

**The transplant reproduces the real object.** 5.60″ vs 5.50″ recovered length, 0.27″ vs
0.26″ width, axis ratio 20.6 vs 21.4 — the Tier 1 round-trip check in
[ADR-0017](../adr/0017-synthetic-realism.md) passing.

**The generator reproduces the transplant** once calibrated on a joint grid: 5.87″, 0.258″,
axis ratio 23.3. Uncalibrated it gave 8.3″ and axis ratio 35, so the gate caught it.

**Completeness, measured over 44 injection sites in 11 real archival tiles** (binomial
uncertainty ±7.5% at 50%):

| mag F606W | 22.5 | 23.0 | 23.5 | 23.8 | 24.1 | 24.4 | 24.8 | 25.3 |
|---|---|---|---|---|---|---|---|---|
| transplant | 100 | 100 | 100 | 100 | 91 | 75 | 27 | 0 |
| parametric c=0.0 | 100 | 98 | 100 | 100 | 84 | 71 | 30 | 5 |
| parametric c=0.3 | 100 | 98 | 100 | 98 | 91 | 77 | 39 | 0 |
| parametric c=0.6 | 100 | 100 | 100 | 98 | 86 | 75 | 41 | 5 |
| parametric c=0.9 | 100 | 100 | 98 | 96 | 89 | 77 | 46 | 7 |

RBH-1 itself sits at 23.77, comfortably in the flat 100% region. The 50% limit is
**24.61**, and varies by only **0.14 mag** across the full clumpiness range — the headline
robustness result, discussed in the ADR amendment.

Detection rate stays at 77–84% at mag 25.3 where completeness has fallen to 0–7%: at the
faint end sources *are* found, but arrive too fragmented or too short to pass the selection
window. Recording the two separately was therefore necessary, not pedantic.

### Still outstanding for Phase 2

The grid above is one slice, not a selection function. Still to do:

- **Other lengths, inclinations and colours.** Everything above is at 8.1″ and one colour.
- **Negative controls** (step 5): noise realisations, rotated and mirrored tiles,
  known-artifact fields, labelled edge-on disks as the discriminator's negative class.
- **Blind human discrimination** (step 6).
- **Crowded positions.** Injections currently avoid bright sources, so this is completeness
  for uncrowded sky and that restriction is part of the selection function.
- **More sites.** 44 gives ±7.5% per point, and background realisations are reused across
  magnitudes, so differences between curves are more reliable than absolute values.

10 real destination tiles from the discovery visit are cached under `data/destinations/`
(git-ignored, regenerate with `uv run rbh fetch-destinations`).

---

## Phase 3 — Scale

Turn a working detector into a survey.

- Manifest builder over MAST CAOM: every public drizzled extragalactic ACS/WFC, WFC3 and
  NIRCam mosaic, with S3 URIs and ETags.
- MOC footprint union, deduplication, and the **published unique survey area**.
- Tiling, work queue, claim–process–commit, resumability.
- Throughput and cost benchmark, reported in **deg² per core-hour** and **$ per deg²**.
- Deploy on the Fornax Science Console.

**Gate:** a full dry-run over one deep field, restartable from an arbitrary kill, with
bit-identical output on re-run.

---

## Phase 4 — Sweep

- Full Tier A sweep (≥ 2 filters), then Tier B.
- Artifact vetting, MRT cross-check, wake-vs-disk discriminator scoring.
- Ranked candidate catalogue with stamps and a static vetting queue.

**Gate:** measured false-positive rate per deg², a survivor count within the human
inspection budget, and a purity estimate with error bars.

---

## Phase 5 — Vet and publish

- Blind human vetting with injected positives mixed in.
- Spectroscopic follow-up proposals for anything that survives.
- Publish: candidate catalogue **plus selection function plus survey MOC**, so that a
  space-density limit is derivable by anyone. Zenodo DOI on release.

**Gate:** the space-density limit is stated with its assumptions, and the null hypothesis
is genuinely testable from the published products alone.

---

## Phase 6 — Euclid and Roman

The real yield. Van Dokkum et al. name these as the obvious datasets for a systematic
search, and the Phase 5 limit predicts what they should return.

| Milestone | Date |
|---|---|
| Euclid Q1 (63.1 deg²) — already public | available now |
| Roman launch | 30 Aug 2026 |
| **Euclid DR1 (~1900 deg²)** | **21 Oct 2026** |

Because the I/O layer is survey-agnostic
([ADR-0013](../adr/0013-survey-agnostic-io.md)), this phase should be a new survey adapter,
a re-derived PSF and pixel scale, a re-run of injection–recovery, and a re-tuned
discriminator — not a rewrite.

**Note on sequencing:** Euclid Q1 is public *now*. If Phase 3 completes well before
October, running Q1 early is cheap, adds ~4× the v1 area, and de-risks the DR1 adapter
before the data that matters arrives.

---

## Explicit non-goals

- Real-time or transient searching.
- Reprocessing raw exposures.
- Spectroscopic analysis in-pipeline.
- Any public claim of a discovery ([ADR-0015](../adr/0015-no-discovery-claims.md)).
