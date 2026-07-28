# ADR-0002 — Compute runs next to the data, with a local corpus for dev and CI

**Status:** Accepted

## Context

The v1 corpus ([ADR-0001](0001-search-the-full-archive.md)) is tens of terabytes and every
pixel must be touched at least once. MAST hosts a free, anonymous copy on AWS in
`s3://stpubdata`, in **us-east-1**. Reads from within that region are free and fast; egress
is neither.

However, "cloud-only" is the wrong conclusion. Development needs sub-second iteration,
CI must be hermetic and offline, and the RBH-1 litmus test
([ADR-0010](0010-rbh1-regression-test.md)) has to run on every commit without depending on
MAST being up. Those requirements are best served by a small local cache, and individual
tiles are small enough that this is trivially affordable.

Platform options evaluated:

| Platform | Verdict |
|---|---|
| **NASA Fornax Science Console** | Free JupyterLab in AWS us-east-1, adjacent to MAST/IRSA/HEASARC cloud data, scalable CPUs, no user charge, already carries Euclid. **Chosen.** |
| MAST TIKE | Free and zero-setup, but ~4 cores. Good for interactive inspection, too small for a sweep. |
| Own AWS (Batch / EC2 spot) | Best throughput and control, but costs money and needs a cost cap. Fallback. |
| Local-only | Impossible for the sweep; egress alone is prohibitive. |

## Decision

**Production sweeps run on the NASA Fornax Science Console**, in AWS `us-east-1`, reading
`s3://stpubdata` via anonymous streamed byte-range requests:

```python
fits.open(uri, use_fsspec=True, fsspec_kwargs={"anon": True}, lazy_load_hdus=True)
# ... and read through .section[...], never .data
```

**Development, testing and CI run locally** against a small cached corpus of cutouts under
`data/` (git-ignored) plus committed sub-2 MB fixtures under `tests/data/`.

Any production execution environment must be in `us-east-1`. If Fornax capacity proves
insufficient, the fallback is AWS Batch array jobs in the same region, with a hard cost
cap wired in before the first job is submitted.

## Consequences

- The pipeline must never assume a POSIX filesystem for science data. All reads go through
  an abstraction that resolves to `s3://`, `file://`, or a local cache identically.
- `.section[...]` reads are mandatory; a stray `.data` access on a full mosaic will pull
  hundreds of MB per tile and destroy throughput. This deserves a lint rule or a wrapper
  that makes the wrong thing hard to write.
- Cost and throughput must be measured explicitly, in **deg² per core-hour** and
  **$ per deg²**, from Phase 3 onward.
- Fornax is a beta programme requiring an account application — a scheduling dependency,
  and the application should go in during Phase 1 rather than Phase 3.
- CI can never be red because MAST is down. Network-dependent tests are marked `network`
  and excluded from CI runs.

## Alternatives considered

- **Download a curated subset locally.** Feasible for deep fields only; incompatible with
  ADR-0001.
- **Requester-pays / cross-region reads.** Rejected on cost; egress on tens of TB is the
  dominant expense and buys nothing.
- **GPU acceleration.** The bottleneck is expected to be S3 I/O, not filter arithmetic.
  Revisit only if profiling contradicts that.
