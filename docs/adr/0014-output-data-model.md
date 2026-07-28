# ADR-0014 — Output data model and formats

**Status:** Accepted

## Context

Outputs need to serve four consumers with genuinely different needs: a worker writing
results under interruption, an analyst querying tens of millions of rows, a human vetting
stamps, and a future reader reproducing a published limit. A single format serves none of
them well.

Volume matters. Raw ridge detections across ~15–20 deg² will number in the tens of
millions before geometric cuts. Storing every one with a full feature vector is the
difference between a queryable archive and an unmanageable pile.

## Decision

**Formats**

| Product | Format | Why |
|---|---|---|
| Manifest | Parquet | Columnar, queryable, compresses well |
| Survey footprint | **MOC** (FITS) | The standard for sky coverage; unions and areas are exact |
| Per-tile results | Parquet, one file per tile | Enables claim–process–commit atomicity ([ADR-0004](0004-work-unit-is-a-sky-tile.md)) |
| Candidate catalogue | Parquet **and** FITS table | Parquet for analysis, FITS for the astronomical ecosystem |
| Selection function | Parquet (gridded) + plots | A published data product, not a figure ([ADR-0009](0009-injection-recovery.md)) |
| Stamps | FITS (science) + PNG (vetting) | Pixels for measurement, images for eyes |
| Vetting queue | Static HTML + JSON log | No server, works offline, trivially archivable |
| Run record | JSON | Config, environment, code version, timings |

**Retention.** Three tiers, because storing everything is not affordable and storing only
survivors makes "why was this rejected?" unanswerable:

1. **All raw detections** — minimal columns only (position, tile, S/N, length, width, PA,
   plus the reject reason). Enough to reconstruct any rejection.
2. **Stage-4 survivors** — full feature vector, including every discriminant value, so the
   catalogue is re-rankable without re-running the sweep
   ([ADR-0008](0008-scored-discriminants-not-cuts.md)).
3. **Ranked candidates** — everything above plus stamps.

**Schema rules.** Every row carries the provenance fields mandated by
[ADR-0012](0012-reproducibility-contract.md). Positions are ICRS degrees, float64.
Photometry is AB magnitudes with explicit filter names. Angular quantities are arcseconds,
named with the unit in the column name (`length_arcsec`, never `length`). Schemas are
versioned; a breaking change bumps the version and is recorded here.

**Partitioning.** Per-tile outputs partition by tile ID; the merged catalogue partitions by
tier and by sky region, so a reader can pull one field without reading the whole survey.

## Consequences

- Workers never contend for a shared output file, which is what makes interruption cheap.
- The catalogue is directly usable in TOPCAT, Aladin and the wider VO ecosystem via the
  FITS table and MOC.
- Rejected detections remain interrogable, which is the question that gets asked most.
- Cost: per-tile parquet fragments must be merged in a final pass, and unit-suffixed column
  names are verbose. Both are worth it — the second especially, since unit ambiguity in
  astronomical catalogues is a recurring source of real error.
- Publishing the MOC and selection function alongside the catalogue means anyone can derive
  a density limit independently, including one that disagrees with ours.

## Alternatives considered

- **A database (SQLite/Postgres).** Better ad-hoc querying. Rejected: a shared writable
  database breaks the no-coordinator execution model, and Parquet on object storage is the
  natural fit for a cloud sweep.
- **FITS tables throughout.** Maximum ecosystem compatibility. Rejected on performance and
  columnar access at tens of millions of rows; FITS is provided as an export instead.
- **Store only surviving candidates.** Much cheaper. Rejected: it makes rejection
  un-auditable, which is exactly the failure mode a rare-object search cannot afford.
