# Roadmap

Each phase ends with a gate that must pass before the next begins. The gates are the
point; the phases are just what fits between them.

---

## Phase 0 — Foundation ✅

Repository, tooling, and the documentation you are reading. Decisions recorded as ADRs
before any science code exists.

**Gate:** lint, types, tests and docs build green in CI.

---

## Phase 1 — Litmus

Prove the concept on the one object we know about, entirely offline.

- Fetch and cache the RBH-1 discovery cutout (GO-16912, ACS F606W + F814W) as a committed
  CI fixture with recorded provenance.
- Implement the ridge-filter detector and morphology measurement (stages 2–3).
- Recover RBH-1 with measured length, width, axis ratio, PA and colour-gradient sign
  matching the published values.

**Gate:** `pytest -m litmus` passes offline and deterministically. Without this, nothing
downstream means anything.

---

## Phase 2 — Measurement

Build the thing that makes the project scientific rather than anecdotal.

- Synthetic wake generator, PSF-convolved, multi-band, parameterised.
- Injection into real tiles, upstream of stage 2.
- Completeness grid over (μ, L, W, inclination, depth, background).
- Negative controls: noise, rotated tiles, known-artifact fields, labelled edge-on disks.

**Gate:** a completeness surface that reproduces the *actual* recovery of the real RBH-1
when an analogue is injected into the same field — the round-trip realism check.

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
