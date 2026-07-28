"""The RBH-1 litmus test - a hard CI gate (ADR-0010).

Runs the full stage 2-3 cascade over the committed discovery-data fixture and requires
that RBH-1 comes back with the right geometry. Offline, deterministic, no network.

If a change breaks this, the change is wrong until argued otherwise in writing. There is
no `xfail` and no `skip` here on purpose.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from astropy.coordinates import SkyCoord

from rbh.colour import colour_profile
from rbh.config import SelectionWindow
from rbh.detect import RidgeDetection
from rbh.morphology import Morphology, measure
from rbh.pipeline import detect_in_tile
from rbh.reference import RBH1, RBH1_LITMUS
from rbh.tile import Tile
from rbh.tileio import read_tile

FIXTURE = Path(__file__).parent / "data" / "rbh1_acs_f606w_f814w.fits"

pytestmark = pytest.mark.litmus


@pytest.fixture(scope="module")
def tile() -> Tile:
    return read_tile(FIXTURE)


@pytest.fixture(scope="module")
def detections(tile: Tile) -> list[RidgeDetection]:
    return detect_in_tile(tile)


@pytest.fixture(scope="module")
def recovered(tile: Tile, detections: list[RidgeDetection]) -> Morphology:
    """The longest detection in the fixture, which should be RBH-1 itself."""
    image, _ = tile.detection_image()
    best = max(detections, key=lambda d: d.n_pixels)
    return measure(best, image, tile.wcs, tile.pixel_scale_arcsec)


def test_fixture_is_two_filter_tier_a(tile: Tile) -> None:
    assert tile.filter_names == ("F606W", "F814W")
    assert tile.tier == "A"
    assert tile.pixel_scale_arcsec == pytest.approx(0.05, abs=1e-3)


def test_rbh1_is_recovered_as_a_single_feature(recovered: Morphology) -> None:
    """The wake must come back whole, not as a handful of knots.

    This is the assertion that fragment linking exists to satisfy: without it the
    feature breaks into three pieces of roughly 2 arcsec each.
    """
    assert recovered.length_arcsec == pytest.approx(
        RBH1_LITMUS.length_arcsec, abs=RBH1_LITMUS.length_tolerance
    )
    assert recovered.axis_ratio >= RBH1_LITMUS.min_axis_ratio
    assert recovered.peak_snr >= RBH1_LITMUS.min_peak_snr


def test_recovered_width_is_psf_scale(recovered: Morphology) -> None:
    """RBH-1 is intrinsically narrower than the ACS PSF, so we should measure ~PSF width."""
    assert recovered.width_arcsec == pytest.approx(
        RBH1_LITMUS.width_arcsec, abs=RBH1_LITMUS.width_tolerance
    )
    assert recovered.width_arcsec > RBH1.width_arcsec  # PSF broadens the intrinsic width


def test_recovered_position_angle(recovered: Morphology) -> None:
    assert recovered.position_angle_deg == pytest.approx(
        RBH1_LITMUS.position_angle_deg, abs=RBH1_LITMUS.position_angle_tolerance
    )


def test_feature_is_straight(recovered: Morphology) -> None:
    """Straight enough to pass the selection window, and not suspiciously perfect."""
    assert recovered.straightness_arcsec <= RBH1_LITMUS.max_straightness_arcsec
    assert recovered.straightness_arcsec <= SelectionWindow().max_straightness_residual_arcsec


def test_published_coordinate_lies_on_the_recovered_axis(recovered: Morphology) -> None:
    """The published coordinate marks the host galaxy at one end of the feature.

    It is about 5.5 arcsec from the centroid, which is not an error: it sits essentially
    exactly on the feature's own axis, just beyond the end of the section bright enough
    to detect.
    """
    published = SkyCoord(RBH1.ra_deg, RBH1.dec_deg, unit="deg")
    end_a = SkyCoord(recovered.endpoint_a_ra_deg, recovered.endpoint_a_dec_deg, unit="deg")
    end_b = SkyCoord(recovered.endpoint_b_ra_deg, recovered.endpoint_b_dec_deg, unit="deg")

    separation = published.separation(end_b).arcsec
    bearing = published.position_angle(end_b).deg
    axis = end_a.position_angle(end_b).deg
    offset = abs(separation * np.sin(np.radians(bearing - axis)))
    assert offset <= RBH1_LITMUS.max_axis_offset_arcsec

    # Host coordinate to far endpoint should reproduce the published 62 kpc length.
    assert separation == pytest.approx(
        RBH1_LITMUS.full_extent_arcsec, abs=RBH1_LITMUS.full_extent_tolerance
    )
    assert separation == pytest.approx(RBH1.length_arcsec, abs=1.0)


def test_colour_reddens_toward_the_host(tile: Tile, detections: list[RidgeDetection]) -> None:
    """Stars laid down earliest sit nearest the host and have had longest to redden."""
    best = max(detections, key=lambda d: d.n_pixels)
    profile = colour_profile(tile, best, "F606W", "F814W")

    assert profile.gradient_significance >= RBH1_LITMUS.min_colour_gradient_significance
    # Endpoint A is the host side, so colour must decrease from A toward B.
    assert not profile.reddens_toward_b
    assert np.all(np.isfinite(profile.colour_ab))


def test_rbh1_is_the_only_thing_passing_the_selection_window(
    tile: Tile, detections: list[RidgeDetection]
) -> None:
    """Applying ADR-0007's window to this field should leave exactly one candidate."""
    window = SelectionWindow()
    image, _ = tile.detection_image()
    survivors = [
        m
        for m in (measure(d, image, tile.wcs, tile.pixel_scale_arcsec) for d in detections)
        if window.min_length_arcsec <= m.length_arcsec <= window.max_length_arcsec
        and m.width_arcsec <= window.max_width_arcsec
        and m.axis_ratio >= window.min_axis_ratio
        and m.straightness_arcsec <= window.max_straightness_residual_arcsec
    ]
    assert len(survivors) == 1


def test_detection_is_deterministic(tile: Tile) -> None:
    """Same tile in, byte-identical detections out (ADR-0012)."""
    first = detect_in_tile(tile)
    second = detect_in_tile(tile)
    assert len(first) == len(second)
    for a, b in zip(first, second, strict=True):
        assert np.array_equal(a.ys, b.ys)
        assert np.array_equal(a.xs, b.xs)
        assert a.peak_snr == b.peak_snr
