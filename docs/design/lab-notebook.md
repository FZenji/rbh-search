# Lab notebook

Findings, measurements and dead ends, newest first. ADRs record *decisions*; this records
*what we learned*, including the things that turned out to be wrong.

It exists because a lot of hard-won nuance lives nowhere else. An ADR says "score the
discriminants"; it does not say "the flux-weighted second moment reads 7% high and here is
why". That second kind of knowledge is what gets lost, and losing it means re-learning it
the expensive way.

**Rule:** if a session discovers a number, a gotcha, or a wrong assumption, it lands here
before the session ends.

---

## Reproducing the numbers on this page

| Product | Command | Committed output |
|---|---|---|
| Detector diagnostics | `uv run rbh inspect` | — |
| Destination sky | `uv run rbh fetch-destinations` | `data/destinations/` (git-ignored) |
| Generator calibration | `uv run rbh calibrate` | [`docs/data/phase2-calibration.json`](../data/phase2-calibration.json) |
| Completeness grid | `uv run rbh completeness` | [`docs/data/phase2-completeness.json`](../data/phase2-completeness.json) |

Both studies live in `rbh.studies`, not in scratch scripts. They were prototyped as
throwaway files and that was a mistake — they generate the numbers the project's claims rest
on, and a script in a temp directory satisfies nothing in
[ADR-0012](../adr/0012-reproducibility-contract.md).

---

## 2026-07-30 — Phase 2: negative controls

### What fragment linking costs

Over 19 non-overlapping archival tiles (2.11 arcmin², RBH-1's own field excluded), survivors
of the selection window went **1 → 5** when linking was enabled — five-fold, +4. Raw
detections meanwhile *fell*, 261 → 256: five merges happened, and four of them turned
fragments that each failed the window into single objects that passed it. The debt
[ADR-0016](../adr/0016-rejoin-collinear-fragments.md) left open is settled, and the cost is
larger than "assumed small" would have allowed.

Rates: 1700 ± 2400 per deg² unlinked, 8500 ± 4200 linked. The Poisson errors overlap, so the
*rates* are barely constrained; the paired ratio is what carries the result, since both arms
see identical pixels.

**The mechanism is not the one ADR-0016 guessed.** It worried about unrelated collinear
*noise* blobs. Over 33 arcmin² of pure noise, linking added exactly **zero** survivors — the
noise false-positive rate is under ~108/deg² with or without it. What linking joins is
unrelated collinear **real sources**.

Eyeballing every survivor (figure: [`docs/data/phase2-control-candidates.png`](../data/phase2-control-candidates.png)):

| Field | What it is | Linking's role |
|---|---|---|
| `dest_008` | two unrelated compact sources, well separated | spurious join |
| `dest_016` | compact source plus a nearby knot | spurious join |
| `dest_013` | elongated bright object, almost certainly an edge-on galaxy | reassembled one real object |
| `dest_018` | inside a region of visible vertical detector striping | joined fragments inside an artifact |
| `dest_015` | thin streak, passes with and without linking | none |

Two actions fall out, both recorded in the ADR amendment: add a maximum gap-to-length ratio
(both spurious joins bridge a gap comparable to the fragments themselves, which a real wake's
closely-spaced knots never would), and add a data-quality cut, because `dest_018` should
never have been searched at all.

### Other control results

- **The selection window rejects ~99% of raw detections** — of order 150 raw ridges per
  2 arcmin² become 1–5 survivors. That is where purity comes from.
- **The detector is exactly invariant** under all three quadrant rotations and reflection:
  identical counts, verified not to be a no-op. Pinned as a test.
- **Shuffled filters give zero survivors** while producing a comparable number of raw
  detections. Pairing band A of one field with band B of another destroys the real
  cross-filter coincidence, and the survivors vanish with it — [ADR-0006](../adr/0006-two-tier-filter-requirement.md)'s
  assumption behaving as advertised, on small numbers.

### Things that were wrong

**Reported "linking adds zero false positives" on 8 tiles.** With 12 tiles it became 1 → 2,
with 17 it became 1 → 4, and with 19 it became 1 → 5. The first result was not wrong
arithmetic, it was an
under-powered sample being read as a null result. A ratio of 1.00 from one survivor
constrains nothing; it should have been reported as "no constraint" rather than "no cost".
Lesson, generally applicable: quote the power alongside the point estimate, or a null is
indistinguishable from an absence of data.

**Described the rotation control as decoupling sky structure from detector geometry.** It does
not. Rotating the pixels rotates any detector-frame artifact with them, so nothing is
isolated. It tests rotation *invariance*, which is worth having but is a different thing. The
real artifact test is cross-visit — same sky, different roll angle — and needs Phase 3
coverage.

**The control sample contained the target.** `fetch-destinations --layout grid` starts at the
reference position, so `dest_000` is the RBH-1 discovery field: its centre is 4.0 arcsec from
the published coordinate. One of the "false positives" in blank sky was RBH-1 itself. The
`controls` command now takes `--exclude`, and any field with a known object must be dropped.

---

## 2026-07-30 — Phase 2: injection–recovery

### The headline

Completeness is **~100% down to F606W ≈ 23.8** (RBH-1 itself is 23.77), with a **50% limit at
24.61**. Across the full clumpiness range 0.0–0.9 the 50% limit moves only **0.14 mag**
(24.60 / 24.68 / 24.69 / 24.74).

That last number is the important one. Clumpiness is the morphological property we can least
constrain from a single object, and it barely matters — because fragmentation *does* climb
hard with it (68% → 100%) but collinear fragment linking
([ADR-0016](../adr/0016-rejoin-collinear-fragments.md)) absorbs it before the selection
window sees it. A step added to fix a Phase 1 annoyance turns out to be what makes the
Phase 2 measurement robust.

44 injection sites across 11 real archival tiles; binomial uncertainty ±7.5% at p = 0.5.

### Reproduction check (half the sites)

Re-running through the promoted `rbh completeness` command at `--per-tile 2` (22 sites
instead of 44) gives limits of 24.70 / 24.62 / 24.53 / 24.62 / 24.55, spread **0.17 mag**.

Two conclusions, one reassuring and one corrective:

- **The headline survives.** The spread stays ~0.15 mag, and every limit sits within about
  0.1 mag of the 44-site value — consistent with the ±10.7% binomial noise at n = 22.
- **The apparent monotonic rise with clumpiness does not reproduce.** In the 44-site run the
  limits ordered neatly 24.60 < 24.68 < 24.69 < 24.74; at 22 sites the ordering vanishes.
  That trend was flagged as ~1.9σ at the time and it was right to flag it: it was sample
  noise. **Do not read the ordering in the tables as a real effect** — only the smallness of
  the spread is established.

### Calibration outcome

| | length | width | axis ratio | fragmentation |
|---|---|---|---|---|
| Real RBH-1 | 5.50″ | 0.256″ | 21.4 | — |
| Transplanted real pixels | 5.60″ | 0.274″ | 20.6 | 64–72% |
| Generator, **before** calibration | **8.27″** | 0.234″ | **34.5** | 36% |
| Generator, after calibration | 5.87″ | 0.258″ | 23.3 | 79% |

Fitted: `tail_brightness=0.02`, `clumpiness=0.1`, `width_arcsec=0.22`.

### Things that were wrong

**Sequential parameter tuning.** Fitted tail brightness, then clumpiness, then width. The
width step silently undid the length match — 6.4″ → 3.8″ against a 5.6″ target — because
widening a feature at fixed total flux lowers its peak surface brightness, so less clears the
threshold. The parameters interact; the grid must be joint. Costly mistake to repeat, cheap
to avoid.

**Assumed clumpiness 0.6; measured 0.0–0.2.** The reasoning had been "wakes are knotty,
knots cause fragmentation". True but not dominant: a nearly *smooth* feature already
fragments 65–80% at this surface brightness, because the threshold cuts wherever noise dips.

**Tried to measure the PSF from the fixture.** Got 0.39″ from five "compact" sources — but
they are 175–215 pixel *galaxies*, so that measured their sizes, not the telescope's blur.
There are no stars in a 20″ high-latitude extragalactic field. The effective drizzled PSF is
therefore **unmeasured**, assumed 0.11″, and degenerate with the generator's fitted width.

### Open questions

- **Width–PSF degeneracy.** The fit wants 0.22″ intrinsic against a published 0.06–0.15″. An
  effective drizzled PSF near 0.2″ reconciles them exactly. Resolving this needs a field
  containing a star. Until then the generator is calibrated for *detectability* and its width
  is not a physical claim.
- **The colour profile is not monotonic.** The overall gradient has the published sign
  (−0.047 ± 0.021 mag/arcsec, bluer away from the host) but the bin nearest the host bucks
  the trend by ~3σ. Could be contamination from the bright neighbouring galaxy, or a real
  turnover. Unresolved.
- **Fragment linking must raise the false-positive rate** and we still have not measured by
  how much. This is the most valuable outstanding measurement.

### Caveats on the completeness numbers

- One slice: 8.1″ length, one colour, one instrument and depth.
- Injections avoid bright sources, so this is completeness for **uncrowded** sky.
- 44 sites → ±7.5% per point; background realisations are reused across magnitudes, so
  differences *between* curves are more reliable than absolute values. The apparent rise at
  24.8 with clumpiness (27% → 46%) is ~1.9σ: suggestive, not established.
- Transplant noise is conservative by up to √2, so these are lower bounds.

### Bugs found, all by something downstream trying to *use* a value

| Bug | Consequence |
|---|---|
| Provenance card values truncated to 68 chars | Every recorded S3 URI silently became an unusable prefix (`s3://stp`). Found when `fetch-destinations` tried to read one. |
| `fetch_tile` did not check cutout bounds | A negative slice start is not an error in numpy — it counts from the far end — so an out-of-bounds request returned **pixels from the wrong part of the sky** instead of failing. |
| Width from a flux-weighted second moment | Biased high ~7% (0.256 → 0.274″ on RBH-1): clipping negatives leaves background noise contributing weight at large transverse offsets where the lever arm is greatest. |

None would have been caught by a test that merely checked the code ran.

---

## 2026-07-28/29 — Phase 1: the detector

### Recovered geometry

| Quantity | Recovered | Published |
|---|---|---|
| Length (bright section) | 5.50″ | — |
| Host coordinate → far endpoint | **8.10″** | **7.8″** (62 kpc) |
| Width (FWHM) | 0.256″ | 0.06–0.15″ intrinsic |
| Axis ratio | 21.4 | > 50 intrinsic |
| Position angle | 148.3° | — |
| Straightness residual | 0.035″ | slight curvature reported |
| Peak S/N | 13.6 | — |

Applying the [selection window](../adr/0007-target-selection-window.md) to the discovery
field leaves **exactly one** candidate, and it is the right one.

### The published coordinate is the host galaxy, not the feature

It sits 5.5″ from the detection centroid, which looked like a bug for some time. It is
**0.11″ off the feature's own axis** — essentially exactly on it — one feature-length beyond
the end of the section bright enough to detect. Zooming in shows a compact round galaxy
there. So: host at the published coordinate, wake extending ~8.1″ away, terminal knot at the
far end.

### Fragmentation thresholds, measured

| Threshold | Longest recovered |
|---|---|
| 2.5σ | 6.44″ (intact) |
| 3.0σ | 6.43″ (intact) |
| 3.5σ | 6.40″ (intact) |
| **4.0σ** | **3.94″ (fragments)** |

Hysteresis moves this cliff but does not remove it, which is what produced
[ADR-0016](../adr/0016-rejoin-collinear-fragments.md). Linking bridges gaps up to 1.40″ and
cleanly refuses at 1.75″, either side of the 1.5″ tolerance.

### Things that were wrong

**Normalised the ridge response by a median absolute deviation.** The Meijering response is
positive-definite and strongly right-skewed, so its MAD comes out ~35% *larger* than the
sigma-clipped standard deviation — silently making every nominal threshold stricter than it
claimed. Iterative sigma clipping instead.

**Compared fragment axes to each other when linking.** Two parallel lanes offset sideways
have perfectly parallel axes, so the test saw nothing wrong and merged them. Must compare
each fragment to the axis of their **union**, which is noticeably tilted with respect to
either.

---

## Environment gotchas (this machine)

Not science, but each of these cost real time.

- **PowerShell 5.1 corrupts source files.** It reads as ANSI and writes UTF-8-with-BOM, so
  any `Get-Content | Set-Content` round-trip mangles every non-ASCII character. It happened
  once, and the attempted repair made it worse. Python sources are now **pure ASCII**; use
  the editor, never a shell round-trip.
- **MAST's query endpoint is unreliable; its S3 bucket is not.** `find_drizzled_products`
  timed out repeatedly and killed two long jobs. Both fetch commands now resolve URIs from
  the fixture's own provenance, or from explicit `--uri`, and only fall back to MAST.
- **`Select-Object -Last N` on a background command buffers everything** until the process
  exits, so progress cannot be watched. Write to a file inside the script instead.
- **`.ptp()` is gone in numpy 2** — use `np.ptp(...)`.
- **`gh run list --json X --jq '...\(.y)...'`** — PowerShell eats the backslash; keep jq
  expressions to bare field selectors.
