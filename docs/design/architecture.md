# Architecture

## Design constraints

1. **Bring the code to the data.** Reading every pixel of the archive is unavoidable;
   moving those pixels out of AWS `us-east-1` is not affordable. Compute runs next to
   `s3://stpubdata`. ([ADR-0002](../adr/0002-compute-next-to-the-data.md))
2. **Bounded memory, regardless of corpus size.** Nothing is ever loaded whole. The unit
   of work is a sky tile that fits comfortably in one worker's RAM.
   ([ADR-0004](../adr/0004-work-unit-is-a-sky-tile.md))
3. **Resumable and idempotent.** A sweep of tens of thousands of tiles *will* be
   interrupted. Re-running must skip completed work and produce identical output.
4. **Cheapest test first.** A cascade that rejects 99.9% of sky with a fast filter, and
   spends expensive analysis only on what survives.
5. **Every stage is measurable.** Anything that changes what survives must be expressible
   in the selection function. ([ADR-0009](../adr/0009-injection-recovery.md))

## Pipeline stages

```
  MAST CAOM query
        │
        ▼
┌───────────────────┐
│ 0. MANIFEST       │  every public drizzled extragalactic mosaic → parquet
│                   │  + footprint MOCs, filters, depth, n_exp, S3 URI + ETag
└─────────┬─────────┘
          │  MOC union / dedup → unique sky area (this number is the survey)
          ▼
┌───────────────────┐
│ 1. TILING         │  sky → deterministic tiles; tiles → contributing files
│                   │  tier assignment (A: ≥2 filters, B: single filter)
└─────────┬─────────┘
          │  work queue: one row per tile, claimed idempotently
          ▼
┌───────────────────┐   ← streamed from S3 via fsspec byte-range reads
│ 2. DETECT         │  background model → bright-star mask → multi-scale ridge
│    (per tile)     │  filter (Meijering/Sato) → noise-normalise by weight map
│                   │  → threshold → connected components
└─────────┬─────────┘
          │  ~10³–10⁴ raw ridges per deg²
          ▼
┌───────────────────┐
│ 3. MORPHOLOGY     │  length, width, axis ratio, straightness residual, PA,
│                   │  filling factor, S/N, terminal-knot test, endpoint flags
└─────────┬─────────┘
          │  geometric window cut (ADR-0007) → ~10¹–10² per deg²
          ▼
┌───────────────────┐
│ 4. ARTIFACT VET   │  n_exp ≥ 2 over footprint · diffraction-spike geometry ·
│                   │  detector-frame artifact masks · grid-axis PA · edges ·
│                   │  cross-filter coincidence · cross-visit coincidence
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐   ← MRT (acstools.findsat_mrt) as an independent
│ 5. CROSS-CHECK    │     second detector on survivors only (ADR-0005)
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ 6. DISCRIMINATE   │  wake-vs-disk feature vector: rest-NIR ratio, longitudinal
│                   │  asymmetry, colour gradient sign, transverse dust lane,
│                   │  host anchor cross-match, counter-feature search → score
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ 7. REPORT         │  ranked parquet + multi-band FITS/PNG stamps +
│                   │  static HTML vetting queue with blind injected positives
└───────────────────┘

  Running alongside, on the same tiles:
┌───────────────────┐
│  INJECTION        │  synthetic wakes injected pre-stage-2 → recovery measured
│                   │  through the identical cascade → selection function
└───────────────────┘
```

## Stage notes

### 0. Manifest

`astroquery.mast` CAOM query for `dataproduct_type="image"`, `calib_level=3`, public,
across ACS/WFC, WFC3/UVIS, WFC3/IR and NIRCam, plus the HLSP mosaics that already exist
for the deep fields. Records the **S3 URI and ETag** of every file so a run can be
replayed against byte-identical inputs.

Footprints are stored as MOCs (`mocpy`). The union of the manifest MOC, restricted to
Galactic latitude \|b\| > 20° and excluding crowded fields, **is the survey**. Its area is
the denominator of every density limit we publish, so it is computed once, versioned, and
shipped with the catalogue.

### 1. Tiling

Fixed tessellation, chosen once and never changed within a data release, so tile IDs are
stable and results are addressable. Tiles overlap by more than the maximum feature length
(25″) so no candidate is split at a boundary; duplicate detections in the overlap are
merged by sky position.

A tile carries: science array, weight/exposure map, DQ, WCS, and the list of contributing
exposures. It is sized so a worker holds one tile plus filter buffers in a few hundred MB.

### 2. Detection

The primary detector is a **multi-scale ridge (vesselness) filter** — Meijering or Sato
from `skimage.filters` — with scales matched to 0.05–0.6″ widths. It is designed for thin
curvilinear structures, is O(N) per scale via separable convolution, and unlike
segmentation it does not shred a low-surface-brightness filament into disconnected knots.

Critically, the response is **normalised by the local noise derived from the weight map**,
not by a global sigma. Archival mosaics have wildly non-uniform depth; a global threshold
would produce all its detections at the shallow edges.

### 3–4. Morphology and artifact vetting

Pure geometry and bookkeeping, no new pixel passes. See
[false positives](../science/false-positives.md) for the full contaminant table. The three
tests carrying most of the weight are exposure count, cross-filter coincidence, and
cross-visit coincidence.

### 5. Cross-check

`acstools.findsat_mrt` runs the Median Radon Transform — an independent, published,
independently-validated linear-feature detector (~10× more sensitive than the older
`satdet`, detects trails down to 0.13× the noise level). Running it only on stage-4
survivors keeps its cost irrelevant while giving a genuinely independent confirmation of
each detection. Disagreement between the two detectors is recorded, not hidden.

### 6. Discrimination

Produces a feature vector, not a verdict. Weights are fitted against synthetic wakes
(positives) and real edge-on galaxies drawn from existing morphological catalogues
(negatives), and the resulting ROC curve is published.
([ADR-0008](../adr/0008-scored-discriminants-not-cuts.md))

## Execution model

- **Embarrassingly parallel over tiles.** No inter-tile communication.
- **Claim–process–commit.** A worker claims a tile row, writes
  `runs/<run-id>/tiles/<tile-id>.parquet`, and commits. Restart skips tiles with a
  committed output. Idempotent by construction; no coordinator needed.
- **Bounded memory per worker**, enforced and asserted, not hoped for.
- **Streamed I/O**: `fits.open(uri, use_fsspec=True, fsspec_kwargs={"anon": True},
  lazy_load_hdus=True)` with `.section[...]` so only the tile's byte ranges cross the
  wire. In-region this is free and fast.
- **Backpressure on S3, not on CPU.** Expect I/O, not filter arithmetic, to be the
  bottleneck; the throughput target is expressed in **deg² per core-hour** and measured
  from day one.

## Non-goals for v1

- Supervised deep learning. One real positive is not a training set; ML only becomes
  legitimate once the injection framework can manufacture thousands of realistic
  positives, and even then it must be validated against the same held-out truth.
- Spectroscopic analysis. Out of scope by design
  ([ADR-0015](../adr/0015-no-discovery-claims.md)).
- Reprocessing raw exposures. We consume archive-grade drizzled products
  ([ADR-0003](../adr/0003-search-plane-drizzled-mosaics.md)).
