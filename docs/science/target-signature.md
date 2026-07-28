# Target signature

What the pipeline actually looks for, expressed as numbers a detector can be tuned to.
Derived from the [RBH-1 dossier](rbh-1-dossier.md); the reasoning behind the ranges is in
[ADR-0007](../adr/0007-target-selection-window.md).

## Morphology (the primary detection channel)

| Observable | Target range | RBH-1 | Notes |
|---|---|---|---|
| Angular length | **2″ – 25″** | 7.8″ | 20–150 kpc over 0.4 < z < 2 |
| Intrinsic width | **≤ 0.6″** | ~0.12″ | At ACS/NIRCam resolution this is PSF-dominated |
| Axis ratio | **≥ 8:1** | > 50:1 | Deliberately loose at the detection stage |
| Straightness | RMS deviation from a straight line ≤ **0.35″** | slight curvature | Real wakes curve slightly; hard straightness is an *artifact* signature |
| Surface brightness | μ ≈ **22–27 mag arcsec⁻²** | ~23.5–24 | Upper end only reachable in deep fields |
| Terminal knot | compact source at one end, brighter than the shaft | present | Strong positive indicator |
| Longitudinal symmetry | **asymmetric** — monotonic profile, not centrally peaked | asymmetric | Disks are symmetric; this is discriminant #2 |
| Host anchor | galaxy at the opposite end from the knot | present | Should share the candidate's photo-z |
| Counter-feature | fainter feature on the far side of the host | present, ~5× fainter | Rare bonus; big score boost when present |

## Colour and SED (the primary discrimination channel)

A wake is young stars plus shock-ionised gas with **no old stellar population**. An
edge-on disk galaxy has a mature disk. This is the cheapest and most powerful
discriminant available from imaging alone.

| Observable | Wake | Edge-on disk |
|---|---|---|
| Rest-UV brightness | high | moderate |
| **Rest-NIR brightness** | **very low / absent** | **high (old disk)** |
| Colour gradient along the axis | **monotonic**, bluest at the tip | symmetric about centre |
| Transverse colour | uniform | **red dust lane** bisecting the disk |
| [O III] excess | strong, concentrated at the tip | absent |

Practically: compare a blue band against a red one that samples rest-frame NIR at the
candidate redshift — e.g. HST F606W vs WFC3/IR F160W, or JWST F150W vs F444W. A feature
that is prominent in the blue and **vanishes** in the red is a strong wake candidate. A
feature present in both with a central dust lane is a galaxy.

## Emission-line signature (confirmation channel, not search channel)

The definitive discriminators are spectroscopic and are out of scope for a photometric
sweep, but they define what follow-up must measure:

- [O III]/Hβ varying from ~1 to ~10 along the feature (star formation → fast shocks).
- Line ratios ([O III]/Hα, [N II]/Hα, [S II]/Hα, [S III]/[S II]) on the fast-radiative-shock
  locus rather than the H II-region locus.
- **A velocity discontinuity of several hundred km s⁻¹ across ≲ 1 kpc at the tip.** This
  is what confirmed RBH-1 and what no imaging survey can substitute for.
- A position–velocity curve that is *not* a rotation curve, and a point that does *not*
  land on the Tully–Fisher relation.

Where medium-band or grism data happen to overlap a candidate (JWST NIRCam medium bands,
NIRISS/NIRCam WFSS, archival VLT/MUSE), the pipeline records it as a follow-up asset
rather than trying to use it in the sweep.

## What we are explicitly *not* sensitive to

Stating this honestly is what makes the selection function meaningful.

- **Wakes without star formation.** If the CGM is too tenuous to be shocked into forming
  stars, there is nothing to see in broadband imaging. We measure the space density of
  *star-forming* wakes only.
- **z ≳ 2.** Cosmological surface-brightness dimming goes as (1+z)⁻⁴; an RBH-1 analogue
  at z = 2 is ~5× fainter per unit area than at z = 1.
- **z ≲ 0.3.** A 62 kpc wake subtends > 25″ and is likely to be broken up by tiling,
  masked as a galaxy, or simply too rare per unit volume in the small archival footprint.
- **Wakes seen close to end-on.** Foreshortening drops them below the axis-ratio cut.
  Injection–recovery quantifies this as a function of inclination.
- **Wakes on top of bright extended galaxies**, where local background structure swamps
  the ridge filter.
