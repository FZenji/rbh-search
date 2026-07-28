# ADR-0005 — Ridge filter primary, MRT cross-check, classical before ML

**Status:** Accepted

**In plain terms:** We use two completely different streak-finding methods. The fast one
(borrowed from medical imaging, where it finds blood vessels) scans everything. The second,
independent one (NASA's satellite-trail finder) only checks the survivors, so it costs
almost nothing but gives us a genuine second opinion. No machine learning yet — with only
one real example, there's nothing to learn from.

## Context

Candidate detection algorithms, assessed against the actual target — a ~2–25″ long,
≤ 0.6″ wide, slightly curved filament:

| Method | Assessment |
|---|---|
| **Hough / Radon transform** | Global, matched-filter-like, mature. Optimal for long straight edge-to-edge trails. Our target is ~150 ACS pixels — squarely in the *short-trail* regime where sensitivity degrades and chance alignments rise. |
| **Median Radon Transform** (`acstools.findsat_mrt`) | Radon with a median instead of a sum, making it robust to bright sources along the path. ~10× more sensitive than the older `satdet`; detects trails at 0.13× the noise (long) and 0.37× (short); ~10 s per 2×2-binned ACS chip on 24 cores; published false-positive handling. Excellent, but tuned for satellite trails. |
| **Ridge / vesselness filters** (Meijering, Sato, Frangi) | Purpose-built for thin curvilinear structures at a specified width scale. Separable and fast. Handles curvature natively — which matters, because real wakes curve slightly and *perfect* straightness is an artifact signature. |
| **Source segmentation + elongation cut** | Cheap and reuses existing catalogues. But segmentation shreds a low-surface-brightness filament into disconnected knots, which is the failure mode we can least afford. |
| **Matched filter bank** (rotated elongated kernels) | Effectively equivalent to ridge filtering, at higher implementation cost. |
| **CNN / deep learning** | We have exactly **one** real positive. There is no training set until synthetic injection exists, and a model trained only on synthetics inherits every inaccuracy of the generator. |

## Decision

A **cascade of two independent detectors**, cheapest first:

1. **Primary sweep — multi-scale ridge filter.** Meijering/Sato at scales matched to
   0.05–0.6″ widths, with the response **normalised by local noise derived from the weight
   map** (never a global sigma — archival depth is wildly non-uniform, and a global
   threshold puts all its detections at the shallow edges). Threshold, connected
   components, then morphology.
2. **Cross-check — Median Radon Transform**, via `acstools.findsat_mrt`, run **only on
   stage-4 survivors**. Running it on survivors makes its cost irrelevant while giving a
   genuinely independent, externally-validated confirmation of each detection.

Disagreement between the two detectors is **recorded as a feature, not silently
resolved**. A ridge detection the MRT misses is not necessarily wrong; it is information
about the candidate.

**No supervised machine learning in v1.** ML becomes legitimate only once
[injection–recovery](0009-injection-recovery.md) can manufacture thousands of realistic
positives, and even then it must be validated against held-out truth and must not replace
the interpretable cascade — it may only re-rank within it.

## Consequences

- Both detectors are off-the-shelf, tested implementations (`skimage`, `acstools`), so
  most effort goes to the parts that are genuinely ours: noise normalisation, morphology,
  vetting, and discrimination.
- Two detectors means two selection functions. Injection–recovery must measure completeness
  for the *cascade*, not for either component.
- `acstools` pulls the ACS calibration stack, so it is an **optional dependency** — the
  primary sweep must not require it.
- The MRT's published false-positive guidance (reject PAs near 0°/90°/180° as
  diffraction-spike-contaminated, cap trail width, require persistence along the trail)
  transfers directly to our artifact vetting and should be reused rather than rederived.
- Adopting a satellite-trail tool for astrophysical features means its defaults are wrong
  for us. Retuning for short trails is required work, not a configuration afterthought.

## Alternatives considered

- **MRT alone.** Mature and published, but tuned for long trails and blind to curvature.
- **Segmentation alone.** Fast, catalogue-friendly. Rejected on filament shredding.
- **CNN first.** Rejected on N = 1.
- **Single detector, no cross-check.** Cheaper, but throws away the strongest available
  argument that a detection is not a filter artifact.
