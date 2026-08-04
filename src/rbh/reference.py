"""Reference objects the pipeline is calibrated against.

Currently there is exactly one confirmed runaway supermassive black hole wake, RBH-1.
Every number here is sourced from the published literature and is treated as immutable
ground truth by the litmus regression test described in ADR-0010. Provenance for each
value is recorded in ``docs/science/rbh-1-dossier.md``.
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict, Field


class ReferenceObject(BaseModel):
    """A published object used to calibrate or regression-test the pipeline."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Common name of the object.")
    ra_deg: float = Field(ge=0.0, lt=360.0, description="ICRS right ascension in degrees.")
    dec_deg: float = Field(ge=-90.0, le=90.0, description="ICRS declination in degrees.")
    redshift: float = Field(gt=0.0, description="Spectroscopic redshift.")
    length_arcsec: float = Field(gt=0.0, description="Projected angular length of the feature.")
    width_arcsec: float = Field(gt=0.0, description="Approximate intrinsic (pre-PSF) width.")
    discovery_proposal_id: str = Field(description="Archive proposal that took the discovery data.")
    discovery_filters: tuple[str, ...] = Field(description="Filters the feature was detected in.")
    total_mag_ab: float = Field(description="Integrated AB magnitude in `total_mag_filter`.")
    total_mag_filter: str = Field(description="Filter for `total_mag_ab`.")
    colour_ab: float = Field(description="Integrated colour across `discovery_filters`.")


class LitmusExpectation(BaseModel):
    """What this pipeline measures when it recovers RBH-1 from the committed fixture.

    These are **our** numbers, not the literature's - they describe pipeline output and
    are expected to move when the detector legitimately improves. :data:`RBH1` holds the
    published values and must not move at all. The two are kept apart deliberately so a
    change to one can never be mistaken for a change to the other.

    Tolerances are wide enough to survive library version drift and tight enough that a
    real regression in the detector fails the build (ADR-0010).
    """

    model_config = ConfigDict(frozen=True)

    length_arcsec: float = Field(description="Recovered length of the bright section.")
    length_tolerance: float = Field(gt=0.0)
    width_arcsec: float = Field(description="Recovered FWHM transverse width.")
    width_tolerance: float = Field(gt=0.0)
    position_angle_deg: float = Field(description="Recovered position angle, N through E.")
    position_angle_tolerance: float = Field(gt=0.0)
    min_axis_ratio: float = Field(gt=1.0)
    max_straightness_arcsec: float = Field(gt=0.0)
    min_peak_snr: float = Field(gt=0.0)
    max_axis_offset_arcsec: float = Field(
        gt=0.0,
        description="How far the published coordinate may sit off the recovered axis. "
        "It marks the host galaxy at one end, so it lies along the feature's line "
        "rather than at its centre.",
    )
    full_extent_arcsec: float = Field(
        description="Published coordinate to far endpoint; compare with RBH1.length_arcsec."
    )
    full_extent_tolerance: float = Field(gt=0.0)
    min_colour_gradient_significance: float = Field(
        gt=0.0, description="Required significance of the colour gradient along the axis."
    )


class FixtureSpec(BaseModel):
    """How the committed litmus fixture is cut out of the archive.

    Pinned so that regenerating the fixture reproduces byte-comparable pixels
    (ADR-0012). The centre is the midpoint of the feature's full extent rather than the
    published coordinate, which sits at one end of it, so the cutout has even margin.
    """

    model_config = ConfigDict(frozen=True)

    observation_ids: tuple[str, ...] = Field(description="MAST observation IDs to draw from.")
    centre_ra_deg: float = Field(ge=0.0, lt=360.0)
    centre_dec_deg: float = Field(ge=-90.0, le=90.0)
    half_size_pixels: int = Field(gt=0, description="Half-width of the square cutout.")


#: The one confirmed runaway SMBH wake. van Dokkum et al. 2023 (ApJL 946, L50) for the
#: photometry and geometry; van Dokkum et al. 2026 (ApJL) for the JWST bow-shock
#: confirmation. Coordinates are J2000 02h41m45.43s -08d20m55.4s.
RBH1: Final[ReferenceObject] = ReferenceObject(
    name="RBH-1",
    ra_deg=40.439292,
    dec_deg=-8.348722,
    redshift=0.964,
    length_arcsec=7.8,
    width_arcsec=0.12,
    discovery_proposal_id="GO-16912",
    discovery_filters=("F606W", "F814W"),
    total_mag_ab=22.87,
    total_mag_filter="F814W",
    colour_ab=0.83,
)

#: Cutout specification for the committed litmus fixture. The centre is the midpoint
#: between the feature's far endpoint and the published coordinate, which measurement
#: showed lies on the feature's own axis (perpendicular offset 0.12 arcsec) at one end
#: rather than at its centre.
RBH1_FIXTURE: Final[FixtureSpec] = FixtureSpec(
    observation_ids=(
        "hst_16912_02_acs_wfc_f606w_jety02",
        "hst_16912_02_acs_wfc_f814w_jety02",
    ),
    centre_ra_deg=40.439896,
    centre_dec_deg=-8.349665,
    half_size_pixels=200,
)

#: Pipeline recovery of RBH-1 from :data:`RBH1_FIXTURE`, first measured 2026-07-28.
#: The detector reaches the bright inner 5.5 arcsec of the feature; extending from the
#: published host-galaxy coordinate to the far endpoint gives 8.1 arcsec, against the
#: published 7.8 arcsec. The colour gradient is negative from endpoint A (host side)
#: toward endpoint B, i.e. the feature is bluest at the far tip and reddens toward the
#: host -- the sense reported by van Dokkum et al.
RBH1_LITMUS: Final[LitmusExpectation] = LitmusExpectation(
    length_arcsec=5.50,
    length_tolerance=0.60,
    # 0.256 with the collapsed-transverse-profile estimator introduced in Phase 2. The
    # earlier flux-weighted second moment read 0.274, biased high by background noise at
    # large transverse offsets.
    width_arcsec=0.256,
    width_tolerance=0.080,
    position_angle_deg=148.3,
    position_angle_tolerance=5.0,
    min_axis_ratio=12.0,
    max_straightness_arcsec=0.12,
    min_peak_snr=8.0,
    max_axis_offset_arcsec=0.50,
    full_extent_arcsec=8.10,
    full_extent_tolerance=1.00,
    min_colour_gradient_significance=1.5,
)


#: How the wake detection limit relates to a tile's own point-source depth (ADR-0018).
#:
#: Measured by degrading the discovery visit over a sixteen-fold range in exposure: the 50%
#: completeness limit for a transplanted RBH-1 sits this many magnitudes brighter than the
#: tile's 5-sigma point-source limiting magnitude, with r^2 = 0.990.
#:
#: This is what lets Phase 3 predict completeness per tile from a weight map instead of
#: running injection-recovery everywhere.
#:
#: **It is an upper bound on completeness**, so a lower bound on this offset. Degrading adds
#: photon noise only; real shallow data also carries cosmic-ray residual, poorer sky
#: subtraction and a worse effective PSF, all of which push the true offset larger. Validate
#: against genuinely shallow real tiles before quoting it as anything but a bound.
WAKE_LIMIT_BELOW_POINT_SOURCE_MAG = 3.03

#: Scatter on the offset above, across the measured depth range.
WAKE_LIMIT_OFFSET_SCATTER_MAG = 0.09
