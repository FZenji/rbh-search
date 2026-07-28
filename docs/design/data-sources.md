# Data sources

## What we search

| Corpus | Instrument | Pixel scale | Approx. usable extragalactic area | Notes |
|---|---|---|---|---|
| HST archive | ACS/WFC | 0.05″ | ~7 deg² measured in 2012; ~10–12 deg² today | The RBH-1 discovery instrument |
| HST archive | WFC3/UVIS | 0.04″ | few deg² | Bluer coverage, useful for rest-UV |
| HST archive | WFC3/IR | 0.13″ | few deg² | **Rest-NIR discriminant band** |
| JWST | NIRCam | 0.031″/0.063″ | ~2–4 deg² and growing | COSMOS-Web 0.54 deg², PRIMER 378 arcmin², JADES ~42+167 arcmin², PANORAMIC, CEERS, NGDEEP |
| **Total v1 survey** | | | **~15–20 deg²** | The denominator of every limit we publish |

For context, HST has imaged roughly **0.1% of the sky** (~41 deg²) in total across all
instruments and all programmes; the extragalactic, multi-filter, uncrowded subset is the
number above.

### Why not deep fields only

The deep fields total ~1–2 deg². Since RBH-1 was a high-S/N detection in a **one-orbit**
image, restricting to them would discard ~90% of the searchable area in exchange for
depth we do not need. ([ADR-0001](../adr/0001-search-the-full-archive.md))

### Product level

We consume **archive-grade drizzled products**, not raw exposures:

- **HAP Single-Visit Mosaics (SVM)** and **Multi-Visit Mosaics (MVM)** — HST-wide,
  uniformly reprocessed, aligned to **Gaia DR3**, on a PS1-like tessellation (4.2°
  projection cells subdivided into 0.2° sky cells). These give us the entire archive in a
  consistent, astrometrically trustworthy form.
- **JWST calibrated level-3 mosaics** from the archive, plus survey **HLSPs** where the
  team's mosaic is better than the pipeline default.

Rationale and the artifact-rejection dividend:
[ADR-0003](../adr/0003-search-plane-drizzled-mosaics.md).

## Where it lives

MAST hosts a copy on AWS in bucket **`s3://stpubdata`**, freely and anonymously
accessible with no AWS account required. URIs look like
`s3://stpubdata/hst/public/<folder>/<file>`. Cloud-hosted collections include `hst`,
`jwst`, `gaia`, `galex`, `panstarrs`, `roman`, and several HLSPs including JADES.

Access patterns:

```python
# Discovery
from astropy.io import fits
from astroquery.mast import Observations

Observations.enable_cloud_dataset(provider="AWS")

# Streaming reads — only the requested byte ranges cross the wire
with fits.open(uri, use_fsspec=True, fsspec_kwargs={"anon": True}, lazy_load_hdus=True) as hdul:
    tile = hdul[1].section[y0:y1, x0:x1]
```

## Where we compute

**NASA Fornax Science Console.** Free JupyterLab in AWS `us-east-1`, sitting next to the
MAST, IRSA and HEASARC cloud holdings, with scalable CPU allocation and cloud credits at
no charge to the user. It already carries Euclid, SPHEREx and JWST, which makes the
phase-2 handover a configuration change rather than a migration.

Secondary environments:

| Environment | Role |
|---|---|
| **Local workstation** | Development, RBH-1 litmus test, CI fixtures, injection–recovery prototyping on a small cached corpus |
| **MAST TIKE** | Free, zero-setup JupyterHub next to `stpubdata`; ~4 cores. Good for interactive candidate inspection, too small for the sweep |
| **Own AWS (Batch / EC2 spot, us-east-1)** | Fallback if Fornax allocation is insufficient. Must carry a hard cost cap |

Non-negotiable: **compute runs in `us-east-1`**. In-region S3 reads are free; egress is
not, and the corpus is tens of TB.
([ADR-0002](../adr/0002-compute-next-to-the-data.md))

## Auxiliary catalogues

Used for masking and cross-matching, never as the primary detection input — catalogue
segmentation shreds thin low-surface-brightness filaments.

| Catalogue | Use |
|---|---|
| **Gaia DR3** | Bright-star positions for diffraction-spike geometry and masking |
| **Hubble Source Catalog** | Bright-source masking; sanity-checking astrometry |
| Survey photo-z catalogues (COSMOS2020, JADES, CEERS) | Host-galaxy anchor redshifts |
| VLASS / LOFAR | Radio counterpart check to reject AGN jets |
| Existing morphology catalogues | Real edge-on disk galaxies as **labelled negatives** for the discriminator |

## Phase 2 corpora

Not in v1 scope, but the I/O layer is abstracted for them
([ADR-0013](../adr/0013-survey-agnostic-io.md)):

| Survey | Availability | Area | Why it matters |
|---|---|---|---|
| **Euclid Q1** | public since 23 Mar 2025 | 63.1 deg² | ~4× the whole HST+JWST archive; already available |
| **Euclid DR1** | **21 Oct 2026** | ~1900 deg² | ~100× the v1 survey. VIS at 0.1″/pix easily resolves and detects an RBH-1 analogue |
| **Roman** | launched 30 Aug 2026 | eventually thousands of deg² | The end state for this kind of search |

Van Dokkum et al. themselves name Euclid and Roman as "the obvious datasets to look for
these features in a systematic way". The HST/JWST sweep exists to calibrate the method
against the one known positive and to produce a space-density prior that predicts what
those surveys should find.

## Acknowledgements required

All data searched is public. Any publication must acknowledge STScI/MAST, cite the
originating HST and JWST programme IDs of every contributing observation (the manifest
records them for exactly this reason), and cite the relevant HLSP teams.
