"""Effective area is the denominator of every density limit, so it is pinned to its data.

ADR-0019. The weighting these functions apply is the difference between "we searched 100
square arcminutes" and "we searched the equivalent of 29 at magnitude 24.5", and nothing
downstream would notice if it drifted.
"""

from __future__ import annotations

import pytest

from rbh.area import (
    COMPLETENESS_ROLLOFF_MAG,
    SkyPatch,
    area_curve,
    completeness_at,
    deepest_per_sky,
    effective_area_arcmin2,
    raw_area_arcmin2,
)
from rbh.reference import WAKE_LIMIT_BELOW_POINT_SOURCE_MAG

#: (5-sigma point-source limit, source magnitude, measured completeness) from the ADR-0018
#: depth grid, transplant rows. The roll-off width was fitted to these.
MEASURED = [
    (27.80, 23.0, 0.98),
    (27.80, 24.4, 0.69),
    (27.80, 25.0, 0.21),
    (27.41, 23.8, 0.93),
    (27.41, 24.4, 0.52),
    (27.03, 23.8, 0.67),
    (27.03, 24.4, 0.10),
    (26.67, 23.0, 0.95),
    (26.67, 23.8, 0.40),
    (26.29, 23.0, 0.83),
    (26.29, 23.8, 0.10),
]


def test_the_completeness_model_reproduces_the_depth_grid() -> None:
    """The fitted roll-off must actually describe the trials it was fitted to.

    Pinned against the data rather than left as a constant, because the width is
    load-bearing: across plausible values the effective-area fraction of a mixed-depth survey
    moves by 26% at magnitude 24.5.
    """
    residuals = []
    for point_source, magnitude, measured in MEASURED:
        patch = SkyPatch(area_arcmin2=1.0, point_source_limit_mag=point_source)
        residuals.append(abs(completeness_at(magnitude, patch.wake_limit_mag()) - measured))
    assert max(residuals) < 0.20, f"worst point misses by {max(residuals):.2f}"
    assert sum(residuals) / len(residuals) < 0.06


def test_completeness_is_one_half_at_the_limit() -> None:
    """The 50% point is the quantity ADR-0018 measured; the shape is only interpolation."""
    patch = SkyPatch(area_arcmin2=1.0, point_source_limit_mag=27.0)
    assert completeness_at(patch.wake_limit_mag(), patch.wake_limit_mag()) == pytest.approx(0.5)


def test_completeness_falls_with_faintness() -> None:
    patch = SkyPatch(area_arcmin2=1.0, point_source_limit_mag=27.0)
    limit = patch.wake_limit_mag()
    assert completeness_at(limit - 1.0, limit) > completeness_at(limit + 1.0, limit)


def test_wake_limit_sits_below_the_point_source_limit() -> None:
    patch = SkyPatch(area_arcmin2=1.0, point_source_limit_mag=27.80)
    assert patch.wake_limit_mag() == pytest.approx(27.80 - WAKE_LIMIT_BELOW_POINT_SOURCE_MAG)


def test_effective_area_never_exceeds_raw_area() -> None:
    """The whole point of the weighting: it can only ever remove area, never add it."""
    patches = [
        SkyPatch(10.0, 27.8),
        SkyPatch(10.0, 27.0),
        SkyPatch(10.0, 26.3),
    ]
    for magnitude in (22.0, 23.5, 24.5, 26.0):
        assert effective_area_arcmin2(patches, magnitude) <= raw_area_arcmin2(patches) + 1e-9


def test_deep_sky_contributes_more_than_shallow_sky() -> None:
    """A one-orbit tile and a twenty-orbit tile are not equally searched."""
    deep = [SkyPatch(10.0, 27.8)]
    shallow = [SkyPatch(10.0, 26.3)]
    assert effective_area_arcmin2(deep, 24.0) > effective_area_arcmin2(shallow, 24.0)


def test_effective_area_falls_as_the_source_gets_fainter() -> None:
    patches = [SkyPatch(10.0, 27.8), SkyPatch(10.0, 26.8)]
    curve = area_curve(patches, [23.0, 24.0, 25.0, 26.0])
    values = [area for _, area in curve]
    assert values == sorted(values, reverse=True)


def test_deepest_per_sky_prefers_the_deeper_observation() -> None:
    """Shallower duplicates of the same sky add no area and must not dilute it."""
    ordered = deepest_per_sky([SkyPatch(5.0, 26.3), SkyPatch(5.0, 27.8), SkyPatch(5.0, 27.0)])
    assert [p.point_source_limit_mag for p in ordered] == [27.8, 27.0, 26.3]


def test_the_rolloff_is_the_fitted_value_not_a_round_number() -> None:
    """A guard against someone tidying 0.212 into 0.2 or back into the original guess.

    The value came from a fit to 25 trial points; a rounder number would be someone's
    preference reasserting itself over the measurement.
    """
    assert abs(COMPLETENESS_ROLLOFF_MAG - 0.212) < 1e-3
