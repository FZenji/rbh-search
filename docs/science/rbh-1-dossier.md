# RBH-1 dossier

Everything the literature records about the one confirmed runaway supermassive black hole
wake. This page is the ground truth for the litmus regression test
([ADR-0010](../adr/0010-rbh1-regression-test.md)) and the template for the synthetic
wakes used in injection–recovery ([ADR-0009](../adr/0009-injection-recovery.md)).

!!! warning "Naming"
    RBH-1 is *not* in or near the dwarf galaxy RCP 28. RCP 28 was the **target** of the
    HST programme; the linear feature is an unrelated background object at z = 0.964 that
    happened to fall in the same field. The wake emerges from a compact star-forming
    galaxy, not from RCP 28. This matters for the search: the host is a faint compact
    galaxy, not a bright nearby one, so "look near big galaxies" is the wrong prior.

## Discovery

| | |
|---|---|
| Discovered | September 2022, serendipitously, by visual inspection |
| Programme | **HST GO-16912** (mid-cycle), target RCP 28 |
| Instrument | ACS/WFC, 0.05″ pix⁻¹ drizzled |
| Filters | F606W and F814W |
| Exposure | ~1 orbit (~2400 s) per filter |
| Position | α = 02ʰ41ᵐ45.43ˢ, δ = −08°20′55.4″ (J2000) → 40.439292°, −8.348722° |
| First reported | van Dokkum et al. 2023, ApJL 946, L50 |

The feature was initially mistaken for a poorly-removed cosmic ray. **Its presence in
both filters ruled that out immediately** — this single fact is the origin of the
project's Tier A cross-filter vetting requirement
([ADR-0006](../adr/0006-two-tier-filter-requirement.md)).

## Measured properties

| Quantity | Value | Source |
|---|---|---|
| Redshift | z = 0.964 (spectroscopic, Keck/LRIS) | vD+23 |
| Angular scale at z | ≈ 8.0 kpc arcsec⁻¹ | Planck-like cosmology |
| Projected length | 62 kpc ≈ **7.8″** | vD+23 |
| Width | ~0.5–1.2 kpc ≈ **0.06–0.15″** | vD+23; Sánchez Almeida+23 |
| Axis ratio | **> 50:1** | derived |
| Integrated magnitude | F814W = 22.87 ± 0.10 AB | vD+23 |
| Integrated colour | F606W − F814W = 0.83 ± 0.05 | vD+23 |
| Mean surface brightness | μ_F814W ≈ **23.5–24 mag arcsec⁻²** | derived from the above |
| Colour gradient | monotonic; **bluest at the tip**, reddening toward the host | vD+23 |
| Brightness profile | rises toward the tip, terminating in a compact knot | vD+23 |
| [O III] λ5007 knot luminosity | 1.9 × 10⁴¹ erg s⁻¹ (at the tip) | vD+23 |
| [O III]/Hβ along the feature | varies from ~1 to ~10 | vD+23 |
| Counter-feature | present, ~5× fainter, opposite side of the host | vD+23 |
| Curvature | slight, but detectable | vD+23 |

### The crucial number

μ ≈ 23.5–24 mag arcsec⁻² in a **one-orbit** ACS image is a detection at high
signal-to-noise, not a marginal one. This is why
[ADR-0001](../adr/0001-search-the-full-archive.md) rejects a deep-fields-only search:
depth is not the binding constraint, area is.

## JWST confirmation (2026)

van Dokkum et al. 2026 (ApJL, doi:10.3847/2041-8213/ae3d0e) used **NIRSpec IFU**
observations of the tip:

- A sharp kinematic discontinuity: **Δv ≈ 600 km s⁻¹ across 0.1″ (1 kpc)**.
- Line ratios ([O III]/Hα, [N II]/Hα, [S II]/Hα, [S III]/[S II]) consistent with **fast
  radiative shocks with rapid cooling**.
- A gradual velocity decrease from tip toward the host, interpreted as downstream mixing
  of shocked gas with the CGM.
- Derived: v_BH = 954 (+110/−126) km s⁻¹, inclination i = 29° (+6/−3),
  **M_BH ≥ 10⁷ M☉** from energy conservation over the wake lifetime.

The authors describe the bow-shock evidence as "very strong, bordering on overwhelming".

## The three-year controversy — and why it is a design input

This is the most important part of the dossier for pipeline design.

| Year | Claim | Basis |
|---|---|---|
| 2023 | Runaway SMBH wake (van Dokkum et al.) | morphology, colour gradient, shock line ratios |
| 2023 | **Bulgeless edge-on disk galaxy** (Sánchez Almeida et al.) | position–velocity curve looks like a rotation curve; sits on Tully–Fisher; v_max ≈ 110 km s⁻¹, z₀ ≈ 1.2 kpc, SB profile all closely match IC 5249 |
| 2023 | Partially shredded galaxy with an SMBH at one end (Chen et al.) | tidal disruption morphology |
| 2023 | Order-of-magnitude objection (Sánchez Almeida et al. II) | hard to build a 40 kpc massive stellar trace in only 39 Myr from small CGM perturbations |
| 2024 | Deep HST imaging **favours the edge-on galaxy** | neither the predicted bow shock nor the counter-wake was recovered |
| 2026 | JWST kinematics **confirm the wake** | 600 km s⁻¹ discontinuity at the tip |

Two hard lessons encoded into this project:

1. **Deep broadband imaging alone did not settle it — and briefly pointed the wrong way.**
   No purely photometric pipeline can confirm a wake. Our output is candidates for
   spectroscopic follow-up, never discoveries
   ([ADR-0015](../adr/0015-no-discovery-claims.md)).
2. **The edge-on bulgeless disk is the contaminant that matters.** It is not a corner
   case; it is the thing that fooled the field about the prototype for three years. See
   [False positives](false-positives.md) and
   [ADR-0008](../adr/0008-scored-discriminants-not-cuts.md).

## An alternative formation channel

Bellovary et al. 2023 (ApJL 953, L21, "Flyby Galaxy Encounters with Multiple Black Holes
Produce Star-forming Linear Features") show that flyby encounters involving multiple black
holes can produce morphologically similar star-forming linear features **without** a
gravitational-wave recoil.

Consequence: even a morphologically perfect candidate does not uniquely imply a recoiling
SMBH. The project searches for *the morphology*; interpretation is downstream of
follow-up. The candidate catalogue schema reflects this — objects are labelled
"linear star-forming feature", not "runaway black hole".

## Sources

- van Dokkum et al. 2023, ApJL 946, L50 — [arXiv:2302.04888](https://arxiv.org/abs/2302.04888) · [doi:10.3847/2041-8213/acba86](https://iopscience.iop.org/article/10.3847/2041-8213/acba86)
- van Dokkum et al. 2023b — [arXiv:2305.00240](https://arxiv.org/abs/2305.00240) (wake–host connection)
- van Dokkum et al. 2026, ApJL — [arXiv:2512.04166](https://arxiv.org/abs/2512.04166) · [doi:10.3847/2041-8213/ae3d0e](https://iopscience.iop.org/article/10.3847/2041-8213/ae3d0e) (JWST confirmation)
- Sánchez Almeida et al. 2023 — [arXiv:2304.12344](https://arxiv.org/abs/2304.12344) (edge-on galaxy)
- Sánchez Almeida et al. 2023b, A&A — [order-of-magnitude analysis](https://www.aanda.org/articles/aa/full_html/2023/10/aa47098-23/aa47098-23.html)
- Deep HST imaging follow-up — [doi:10.3847/2515-5172/ad530b](https://iopscience.iop.org/article/10.3847/2515-5172/ad530b)
- Bellovary et al. 2023 — [doi:10.3847/2041-8213/aced45](https://iopscience.iop.org/article/10.3847/2041-8213/aced45)
