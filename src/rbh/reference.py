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
