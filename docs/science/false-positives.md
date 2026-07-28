# False positives

Thin straight lines are the most common artifact class in astronomical imaging. This page
enumerates every contaminant we expect and the specific mechanism that rejects it. It is
the reference for the vetting stages in the
[architecture](../design/architecture.md).

The taxonomy splits into two very different problems:

- **Instrumental artifacts** — numerous, but each has a deterministic signature. Largely a
  solved problem, and mostly solved *for free* by our choice of search plane.
- **Astrophysical contaminants** — far fewer, but genuinely hard. One of them fooled the
  entire field about RBH-1 for three years.

---

## Instrumental artifacts

### Solved by the choice of search plane

We search **drizzled, cosmic-ray-rejected, multi-exposure mosaics**
([ADR-0003](../adr/0003-search-plane-drizzled-mosaics.md)). This is not a convenience; it
is the single highest-leverage false-positive decision in the project.

| Contaminant | Why the search plane kills it |
|---|---|
| **Cosmic rays** | Present in one exposure only; removed by AstroDrizzle CR rejection. A real sky feature is fixed in sky coordinates and survives dithering. |
| **Satellite trails** | Same mechanism — a trail appears in one exposure of a dithered stack and is rejected. |
| **Asteroid / NEO trails** | Move between exposures; rejected identically. |
| **Single-exposure detector defects** | Flagged in the DQ arrays, propagated to the weight map as zero weight. |

Residual risk: trails present in *most* exposures of a short visit, or fields with only
one usable exposure. Both are caught by the exposure-count requirement below.

### Requires explicit vetting

| Contaminant | Signature | Rejection |
|---|---|---|
| **Diffraction spikes** | Fixed position angles relative to a bright star; ACS at ±45° in detector frame, JWST NIRCam a 6-spike pattern at known PA | Cross-match bright stars (Gaia); reject features whose PA and radial alignment match the instrument's spike geometry |
| **Detector-frame scattered light** — ACS "dragon's breath", WFC3/IR blobs, NIRCam wisps and claws | Occur at **fixed detector pixel coordinates** | Build a per-instrument detector-frame mask; map candidate sky positions back through the WCS of every contributing exposure |
| **Chip gaps, mosaic seams, image edges** | Straight, aligned with the drizzle grid, coincident with weight-map discontinuities | Reject features touching low-weight boundaries or aligned with grid axes |
| **Detector-axis alignment** | PA within a few degrees of 0°/90° in the drizzle frame | Deprioritise; the `findsat_mrt` literature does the same, excluding ~0°/90°/180° as a high-false-positive region |
| **Persistence** (WFC3/IR) | Latent image of a bright source from a prior exposure | Requires cross-visit checking; in practice caught by the multi-filter coincidence test |
| **Charge-transfer-inefficiency trails** | Always parallel to the readout direction, always trailing bright sources | Detector-axis rejection covers this |
| **Amplifier glow / bias structure** | Broad, low-frequency, detector-frame | Background modelling and detector-frame masking |
| **Crosstalk ghosts** | Mirror-symmetric counterpart of a bright source across an amplifier boundary | Geometric test against bright sources |

### The three universal artifact tests

Independent of contaminant type, three cheap tests carry most of the weight:

1. **Exposure-count requirement.** Require ≥ 2 (ideally ≥ 3) contributing exposures over
   the feature's whole footprint, read from the weight or context map. Nearly every
   transient artifact dies here.
2. **Cross-filter coincidence.** A real object appears in every filter with the right SED;
   an artifact almost never does. **This is exactly how RBH-1 was distinguished from a
   cosmic ray on day one** — and it is why Tier A fields are prioritised
   ([ADR-0006](../adr/0006-two-tier-filter-requirement.md)).
3. **Cross-visit coincidence.** Where a field was observed on separate dates with
   different roll angles, the feature must survive. Detector-frame artifacts rotate on the
   sky; real objects do not. This is the strongest artifact test available and the reason
   multi-visit mosaics are preferred where they exist.

---

## Astrophysical contaminants

### 1. Bulgeless edge-on disk galaxies — the dominant problem

Not a corner case. This interpretation was published against RBH-1, was supported by deep
HST imaging in 2024, and was only overturned by JWST spectroscopy in 2026. Edge-on disks
are common, thin, straight, and blue in the outer parts.

| Discriminant | Wake | Edge-on disk | Power |
|---|---|---|---|
| **Rest-NIR counterpart** | absent (no old population) | present (old disk) | ★★★ |
| Longitudinal profile | monotonic, brightest at one end | symmetric, centrally peaked | ★★★ |
| Colour gradient | monotonic along the axis | symmetric about centre | ★★☆ |
| Transverse structure | uniform, knotty | central dust lane | ★★☆ |
| Terminal knot | present at the leading end | absent (or a bulge in the middle) | ★★☆ |
| Vertical profile | filamentary, near-PSF | exponential scale height, constant along the length | ★★☆ |
| Host anchoring | attached to a separate galaxy at one end | free-standing | ★☆☆ |
| Position–velocity curve | **not** a rotation curve; discontinuity at tip | rotation curve; lands on Tully–Fisher | ★★★ (spectroscopy only) |

No single test is decisive from imaging alone, which is the entire argument for scoring
rather than cutting ([ADR-0008](../adr/0008-scored-discriminants-not-cuts.md)).

### 2. Other astrophysical look-alikes

| Contaminant | Discriminant |
|---|---|
| **Tidal tails and stellar streams** | Curved, wider, no terminal knot, and connected to an *interacting pair*; look for a companion |
| **Gravitational lens arcs** | Curved on a consistent centre, tangentially oriented around a massive foreground deflector, and typically red-ish; RBH-1 was cleared because the feature shares the host's redshift |
| **AGN jets** | Power-law continuum, no emission lines, usually a radio counterpart, and emerge from a bright nucleus. Cross-match VLASS/LOFAR |
| **Chance alignments of unrelated sources** | The Median Radon Transform is designed to be robust to this (median rather than sum along paths); also fails the filling-factor and width-uniformity tests |
| **Edge-on low-surface-brightness / "superthin" galaxies** | Same treatment as case 1, but harder — flagged for follow-up rather than dismissed |
| **Star-forming filaments in nearby galaxies** | Wrong physical scale; rejected by requiring no bright low-z galaxy overlapping the feature |
| **Galactic cirrus and diffuse ISM filaments** | Restrict the sweep to Galactic latitude \|b\| > 20°; cirrus is extremely red and has no compact knots |

---

## The false-positive budget

The pipeline is not tuned to a target purity in the abstract; it is tuned to a **human
inspection budget** ([ADR-0011](../adr/0011-human-vetting-protocol.md)).

- Measure the raw false-positive rate per deg² directly, on rotated/flipped tiles and on
  noise realisations with no injected sources.
- Set the score threshold so that the expected number of survivors across the whole
  archive is of order **10³ stamps** — a few evenings of visual inspection.
- Report the threshold, the resulting purity estimate, and the completeness it costs.
  Every one of those numbers is part of the published selection function.
