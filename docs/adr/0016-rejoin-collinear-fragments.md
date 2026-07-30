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
| `dest_018` | an unremarkable field; see the correction below | joined fragments of something faint |
| `dest_015` | a thin streak; passes with **and** without linking | none |

Of the four objects linking adds, two are unambiguously spurious joins of unrelated sources
and one is a real galaxy whose fragments were reassembled — the
[ADR-0008](0008-scored-discriminants-not-cuts.md) contaminant rather than a linking failure.

### Correction, and two follow-ups that the data rejected

An earlier version of this amendment described `dest_018` as sitting "in a region of visible
vertical detector striping". **That was wrong.** Its column and row striping significances are
2.2 and 2.1, statistically indistinguishable from clean control tiles, and with a stretch
matched across tiles the field looks unremarkable. The apparent striping was an artefact of
per-panel zscale in the inspection figure, which stretches a low-contrast crop hard and
amplifies ordinary noise into visible banding. A lesson about eyeballing stamps at
independent stretches, recorded in the lab notebook.

That correction removed the motivation for one proposed follow-up, and measurement removed the
other:

- **A maximum gap-to-length ratio does not separate the classes.** Measured gap over
  union-span: `dest_016` 0.30 and `dest_008` 0.39 (both spurious) against `dest_013` 0.40 (a
  real galaxy) and `dest_018` 0.18. Any cut that removes the spurious joins removes the real
  object too. Not implemented.
- **No coverage-based data-quality cut is warranted.** `dest_013` does sit in genuinely poor
  coverage — 30% of its pixels below 0.8x the median weight, against 5-12% for a typical tile
  — but the noise model already handles it. Measured over 20 tiles, the scatter of the
  signal-to-noise image is 0.93-0.99 across a hundred-fold range in weight: within 7% of
  unity and biased slightly conservative. There is nothing for a cut to fix. That check is now
  :func:`rbh.controls.noise_model_scatter`.

So the spurious joins stand unmitigated for now. The right lever is not a geometric cut but
the wake-versus-disc scoring of [ADR-0008](0008-scored-discriminants-not-cuts.md): two
unrelated compact blobs bridged by nothing should fail on longitudinal asymmetry, terminal-knot
contrast and colour gradient, none of which is implemented yet. Deferred to Phase 4 rather
than patched with a cut that does not work.

**The Decision stands.** Completeness measured in Phase 2 is robust to clumpiness precisely
*because* linking absorbs fragmentation ([ADR-0017](0017-synthetic-realism.md) amendment),
and a five-fold rise in a candidate rate of order 10³–10⁴ per deg² is still affordable
against a human vetting budget. But the trade is now quantified rather than hoped about.

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
