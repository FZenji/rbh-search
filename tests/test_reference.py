"""Guard the published RBH-1 values against accidental edits.

These are literature measurements, not tunables. The litmus regression test (ADR-0010)
is only meaningful if the truth it compares against cannot drift.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from rbh.reference import (
    RBH1,
    WAKE_LIMIT_BELOW_POINT_SOURCE_MAG,
    WAKE_LIMIT_OFFSET_SCATTER_MAG,
)


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


def test_the_depth_relation_predicts_the_measured_limits() -> None:
    """The offset must reproduce what the depth study actually measured.

    Phase 3 predicts per-tile completeness from a weight map using this one number, so it is
    worth pinning against the data it came from rather than leaving it as a constant somebody
    can drift. Pairs are (5-sigma point-source limit, measured wake 50% limit) for the
    transplant, at exposure fractions 1, 1/2, 1/4, 1/8, 1/16.
    """
    measured = [
        (27.80, 24.64),
        (27.41, 24.43),
        (27.03, 23.98),
        (26.67, 23.66),
        (26.29, 23.36),
    ]
    for point_source, wake in measured:
        predicted = point_source - WAKE_LIMIT_BELOW_POINT_SOURCE_MAG
        assert abs(predicted - wake) <= 2 * WAKE_LIMIT_OFFSET_SCATTER_MAG, (
            f"prediction {predicted:.2f} misses the measured {wake:.2f} at depth {point_source}"
        )


def test_the_depth_relation_is_a_lower_bound_on_the_offset() -> None:
    """Stated as a bound, so nothing downstream treats it as an estimate.

    Degrading simulates photon noise only. Every neglected effect makes real data harder,
    which pushes the true offset larger, never smaller.
    """
    assert WAKE_LIMIT_BELOW_POINT_SOURCE_MAG > 0
    assert WAKE_LIMIT_OFFSET_SCATTER_MAG < 0.5 * WAKE_LIMIT_BELOW_POINT_SOURCE_MAG
