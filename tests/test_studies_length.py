"""The length axis of the completeness grid, and the surface-brightness bookkeeping."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from rbh.studies import completeness_vs_length, mean_surface_brightness

FIXTURE = Path(__file__).parent / "data" / "rbh1_acs_f606w_f814w.fits"

pytestmark = pytest.mark.slow


def test_surface_brightness_dims_as_a_feature_is_stretched() -> None:
    """At fixed total magnitude a longer feature is spread thinner, so it is fainter per area.

    This is the bookkeeping that stops the length axis being read as "same brightness,
    different shape". Doubling the length costs 0.75 mag of surface brightness.
    """
    short = mean_surface_brightness(24.0, length_arcsec=4.0, width_arcsec=0.22)
    long = mean_surface_brightness(24.0, length_arcsec=8.0, width_arcsec=0.22)
    assert long - short == pytest.approx(2.5 * math.log10(2.0), abs=1e-6)
    assert long > short


def test_surface_brightness_matches_a_hand_calculation() -> None:
    # 1 square arcsec of area means surface brightness equals total magnitude.
    assert mean_surface_brightness(24.0, length_arcsec=1.0, width_arcsec=1.0) == pytest.approx(24.0)


def test_zero_area_does_not_blow_up() -> None:
    assert math.isfinite(mean_surface_brightness(24.0, 0.0, 0.0))


def test_grid_covers_every_requested_cell() -> None:
    rows = completeness_vs_length(
        FIXTURE,
        None,
        lengths_arcsec=(4.0, 8.0),
        magnitudes=(22.0, 24.0),
        per_tile=2,
    )
    assert len(rows) == 4
    assert {(float(r["length_arcsec"]), float(r["mag"])) for r in rows} == {
        (4.0, 22.0),
        (4.0, 24.0),
        (8.0, 22.0),
        (8.0, 24.0),
    }


def test_a_feature_too_long_for_the_tile_is_reported_not_skipped() -> None:
    """Silently omitting impossible cells would read as "not measured" rather than "cannot fit".

    The tiles are 20 arcsec, so the selection window's upper end genuinely cannot be probed
    with this tiling, and the grid has to say so.
    """
    rows = completeness_vs_length(
        FIXTURE,
        None,
        lengths_arcsec=(60.0,),
        magnitudes=(23.0,),
        per_tile=1,
    )
    assert len(rows) == 1
    assert rows[0]["note"] == "does not fit in tile"
    assert math.isnan(float(rows[0]["completeness"]))


def test_brighter_is_never_less_complete_at_fixed_length() -> None:
    rows = completeness_vs_length(
        FIXTURE,
        None,
        lengths_arcsec=(8.0,),
        magnitudes=(22.0, 27.0),
        per_tile=3,
    )
    by_mag = {float(r["mag"]): float(r["completeness"]) for r in rows}
    assert by_mag[22.0] >= by_mag[27.0]
