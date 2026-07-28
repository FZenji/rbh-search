"""Guard the published RBH-1 values against accidental edits.

These are literature measurements, not tunables. The litmus regression test (ADR-0010)
is only meaningful if the truth it compares against cannot drift.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from rbh.reference import RBH1


def test_coordinates_match_published_sexagesimal() -> None:
    # van Dokkum et al. 2023: 02h41m45.43s, -08d20m55.4s (J2000).
    expected_ra = 15.0 * (2 + 41 / 60 + 45.43 / 3600)
    expected_dec = -(8 + 20 / 60 + 55.4 / 3600)
    assert RBH1.ra_deg == pytest.approx(expected_ra, abs=1e-4)
    assert RBH1.dec_deg == pytest.approx(expected_dec, abs=1e-4)


def test_feature_is_extremely_elongated() -> None:
    assert RBH1.length_arcsec / RBH1.width_arcsec > 50.0


def test_reference_object_is_immutable() -> None:
    with pytest.raises(ValidationError):
        RBH1.redshift = 1.5


def test_discovery_used_two_filters() -> None:
    # Cross-filter coincidence is what ruled out a cosmic ray; it is the basis of
    # Tier A vetting (ADR-0006).
    assert len(RBH1.discovery_filters) >= 2
