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
