# ADR-0016 — Rejoin collinear fragments rather than tuning the threshold

**Status:** Accepted

**In plain terms:** A wake is a chain of bright clumps with faint bridges between them, and
any threshold strict enough to reject noise cuts some of those bridges — so the feature
gets reported as three short streaks instead of one long one. Rather than hunting for a
threshold that happens not to break it, we detect the pieces and then explicitly stitch
back together the ones that line up.

## Context

Measured directly on RBH-1 during Phase 1:

| Detection threshold | Longest recovered feature |
|---|---|
| 2.5 sigma | 6.44 arcsec (intact) |
| 3.0 sigma | 6.43 arcsec (intact) |
| 3.5 sigma | 6.40 arcsec (intact) |
| **4.0 sigma** | **3.94 arcsec (fragments)** |
| 4.0 sigma, first implementation | 2.02 + 1.83 + 1.30 arcsec (three pieces) |

The feature is intact up to roughly 3.5 sigma and breaks by 4. Hysteresis thresholding
(grow at a low threshold, keep only components seeded by a high one) helps, but it only
moves the cliff — it does not remove it.

Operating just below a cliff is precisely the failure ADR-0010 exists to catch. It also
would not generalise: the cliff position depends on surface brightness, depth and how
knotty a particular wake is, so a value tuned on our single example would silently
fragment fainter ones. Since a fragmented feature fails the length and axis-ratio cuts in
ADR-0007, fragmentation is not a cosmetic problem — it is a completeness loss that varies
with brightness in a way we could not model.

## Decision

Detect fragments at a threshold chosen for sensitivity, then **explicitly rejoin
fragments that are consistent with lying on one straight feature**. Two fragments merge
when all three hold:

| Test | Default | Purpose |
|---|---|---|
| Gap between nearest endpoints | ≤ 1.5 arcsec | Adjacency |
| Each fragment's axis vs the axis of their **union** | ≤ 15° | Collinearity |
| RMS scatter of the union about that axis | ≤ 0.35 arcsec | One line describes both |

Merging is transitive, so a chain of knots links into a single feature.

The angle test compares each fragment against the **joint** axis, not against the other
fragment. This is not a detail: two parallel lanes offset sideways have perfectly parallel
axes, so a fragment-to-fragment comparison sees nothing wrong and merges them, while the
line through both is noticeably tilted with respect to either. The first implementation
had this bug and merged two parallel synthetic lines.

## Consequences

- RBH-1 is recovered as a single 5.50 arcsec feature with axis ratio 20, instead of three
  pieces that would each fail the selection window.
- The detector no longer sits on a threshold cliff, so the selection function should vary
  smoothly with surface brightness rather than stepping.
- **Linking can join unrelated collinear noise blobs, raising the false-positive rate.**
  This is a real cost and the amount is currently unknown. It must be *measured* in
  injection-recovery ([ADR-0009](0009-injection-recovery.md)) rather than assumed small,
  and the three tolerances above are the knobs that trade recovered length against
  spurious links.
- The gap tolerance is expressed in arcsec, not pixels, so it means the same thing on
  every survey ([ADR-0013](0013-survey-agnostic-io.md)).
- Linking is O(N²) in fragments per tile. At the fragment counts seen so far this is
  irrelevant; if a crowded tile ever produces thousands, it will need spatial indexing.

## Amendment, 2026-07-30 (the false-positive cost, measured)

The Consequences section above promised that linking's false-positive cost "must be
*measured*, not assumed small". It has been. It is not small.

Over 19 non-overlapping archival tiles (2.11 arcmin², the RBH-1 discovery field excluded):

| | Raw ridge detections | Survivors of the selection window | Per deg² |
|---|---|---|---|
| Without linking | 261 | **1** | 1700 ± 2400 |
| With linking | 256 | **5** | 8500 ± 4200 |

A **five-fold increase**, +4 objects. Coarsely measured — the area is small and the Poisson
errors overlap — but the paired design makes the direction solid. Note the raw count *falls*
(261 → 256, i.e. five merges) while the survivor count *rises*: merging turns fragments that
each failed the window into single objects that pass it. That is exactly the mechanism, seen
working.

**The mechanism is not the one this ADR anticipated.** The Consequences text worried about
"unrelated collinear *noise* blobs". Noise is not the problem: over 33 arcmin² of pure-noise
realisations linking added exactly **zero** survivors, and the noise false-positive rate is
below about 108 per deg² with or without it. What linking actually joins is unrelated
collinear **real sources**.

Inspecting each survivor by eye:

| Field | What it is | Linking's role |
|---|---|---|
| `dest_008` | two unrelated compact sources, well separated | **spurious join** |
| `dest_016` | a compact source plus a nearby knot | **spurious join** |
| `dest_013` | an elongated bright object, almost certainly an edge-on galaxy | joined fragments of one real object |
| `dest_018` | sits in a region of visible vertical detector striping | joined fragments inside an artifact |
| `dest_015` | a thin streak; passes with **and** without linking | none |

Of the four objects linking adds: two are unambiguously spurious joins of unrelated sources,
one is a real galaxy whose fragments were reassembled — the
[ADR-0008](0008-scored-discriminants-not-cuts.md) contaminant rather than a linking failure —
and one is inside an artifact region that should never have been searched at all.

**The Decision stands.** Completeness measured in Phase 2 is robust to clumpiness precisely
*because* linking absorbs fragmentation ([ADR-0017](0017-synthetic-realism.md) amendment),
and a five-fold rise in a candidate rate of order 10³–10⁴ per deg² is still affordable
against a human vetting budget. But the trade is now quantified rather than hoped about, and two
follow-ups are implied:

- **Add a maximum-gap-to-length ratio.** Both spurious joins bridge a gap comparable to the
  fragments themselves. A wake's knots are closely spaced relative to its length; two blobs
  1.5 arcsec apart with nothing between them are not one object.
- **Mask low-quality regions.** `dest_018` should never have been searched. There is no
  data-quality cut beyond the weight map, and the visible striping says one is needed.

## Alternatives considered

- **Tune the threshold to just below the fragmentation cliff.** Simplest, and what the
  first implementation effectively did. Rejected: brittle, does not generalise to fainter
  features, and is exactly the knife-edge tuning ADR-0010 forbids.
- **Morphological closing / dilation before labelling.** Cheap and would bridge small
  gaps, but it also fattens every noise blob, degrades the measured width, and has no
  collinearity test at all, so it would merge anything that happens to be nearby.
- **Detect at a very low threshold and rely on morphology cuts.** Admits far too much of
  the noise field; the component count per tile becomes unmanageable.
- **Accept fragments and merge at the catalogue stage.** Defers the problem to a place
  with less information — by then the pixels are gone and the fragments have already
  failed the selection window.
