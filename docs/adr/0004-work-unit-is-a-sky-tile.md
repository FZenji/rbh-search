# ADR-0004 — The unit of work is a sky tile, not a file

**Status:** Accepted

**In plain terms:** Rather than processing one image file at a time, we chop the sky into
equal squares and process those. Files overlap each other and vary enormously in size;
squares don't. This also means we never search the same patch of sky twice, and we can say
exactly how much sky we covered — a number we need for everything else.

## Context

The obvious work unit is "one file". It is also wrong, for four reasons:

1. **Files vary enormously in size.** A WFC3/IR visit mosaic and a COSMOS-Web NIRCam
   mosaic differ by orders of magnitude. File-level parallelism gives terrible load
   balance and unbounded per-worker memory.
2. **Files overlap on the sky.** Popular fields have been observed dozens of times. Naive
   file-level processing searches the same sky repeatedly, inflating the apparent survey
   area and producing duplicate detections that corrupt any density estimate.
3. **Discrimination needs multiple filters at the same sky position.** Cross-filter
   coincidence is our primary artifact test and the rest-NIR ratio is our primary
   astrophysical discriminant. Both require *co-located* data from different files.
4. **The survey area must be knowable.** Every limit we publish divides by it.

## Decision

The work unit is a **sky tile** on a fixed tessellation, chosen once per data release and
never changed within it, so that tile IDs are stable and every result is addressable by
position.

- Tiles **overlap by more than the maximum feature length (25″)** so no candidate is split
  at a boundary. Duplicate detections in overlap regions are merged by sky position.
- A tile bundles, for every contributing file: science array, weight/exposure map, DQ,
  WCS, and the list of contributing exposures with their roll angles.
- Tile size is chosen so one worker holds one tile plus filter buffers in a few hundred MB.
- Footprints are tracked as **MOCs** (`mocpy`). The MOC union of processed tiles, not the
  sum of file areas, is the survey area.
- Each tile is assigned a **tier** from its filter coverage
  ([ADR-0006](0006-two-tier-filter-requirement.md)).

Execution follows **claim–process–commit**: a worker claims a tile row, writes
`runs/<run-id>/tiles/<tile-id>.parquet`, and commits. Restart skips tiles with a committed
output. No coordinator; idempotency by construction.

## Consequences

- Memory is bounded by construction and independent of corpus size. This should be
  asserted in code, not merely intended.
- Load balancing is near-perfect because tiles are uniform.
- Interruption is free. A sweep of tens of thousands of tiles will be interrupted; the
  cost of that is one tile's work.
- **The survey area is computed, not estimated.** This is what makes a null result
  publishable.
- Cost: assembling a tile from N overlapping files is more complex than opening one file,
  and reprojection onto the tile grid must be done carefully enough not to smear a
  PSF-width feature. Reprojection fidelity is itself a thing injection–recovery must
  verify.
- Overlap regions are processed twice. At 25″ overlap on arcminute-scale tiles this is a
  small percentage — an acceptable price for never splitting a candidate.

## Amendment, 2026-08-04 (ownership replaces merging, and the order is fixed by measurement)

**Duplicates are resolved by ownership, not by merging.** The Decision says duplicate
detections in overlap regions are "merged by sky position". That works, and it needs a
matching tolerance — which is another number that can be wrong in both directions: too small
and a genuine duplicate survives twice, too large and two distinct features collapse into
one. There is no value that reliably does one without risking the other.

Instead every tile has a non-overlapping **core** and processes a larger region around it. A
detection belongs to exactly the tile whose core contains its centroid. Cores tile the sphere
with no gaps and no overlaps, so the partition is exact, the deduplication takes no
parameter, and **a candidate count cannot be inflated by how the sky happened to be cut up**.
Both properties are asserted in `tests/test_tiling.py`, including that two features half an
arcsecond apart both survive — which a merging tolerance would have to be tuned not to eat.

A useful consequence: ownership by centroid **halves the overlap strictly required**. A
feature whose centroid lies in the core extends at most half its length beyond it, so 12.5″
would do rather than 25″. The Decision's figure is kept anyway — extra pixels are cheap, the
sweep is 86% detect-bound, and a margin that is obviously sufficient beats one that is exactly
sufficient.

**The tessellation is HEALPix at order 10**, chosen from this ADR's own memory bound rather
than by preference. Measured, at 0.05″/pixel for science plus weight in two filters:

| order | cell side | pixels/side | memory per tile |
|---|---|---|---|
| 8 | 825″ | 16,490 | 4.4 GB |
| 9 | 412″ | 8,245 | 1.1 GB |
| **10** | **206″** | **4,123** | **272 MB** |
| 11 | 103″ | 2,061 | 68 MB |

"A few hundred MB" picks order 10 without ambiguity. There is a test asserting the memory
figure, so the order cannot drift away from the constraint that chose it.

## Alternatives considered

- **One file per work unit.** Simple, no reprojection. Rejected on load balance, duplicate
  sky, and the impossibility of cross-filter tests.
- **HEALPix tiles.** Attractive for MOC interoperability. Deferred: the practical choice
  is likely to follow the HAP PS1-like tessellation the products already use, avoiding a
  reprojection step entirely for HST. The tessellation choice is an implementation
  decision to be fixed in Phase 3 and recorded here by amendment.
- **No overlap, stitch candidates afterwards.** Rejected: stitching a partially-detected
  ridge across a boundary is far harder than paying for overlap, and it would put a
  position-dependent hole in the selection function.
