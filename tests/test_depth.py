"""Depth degradation must obey the noise model the rest of the pipeline assumes.

Every threshold in the detector is denominated in the ``1/sqrt(weight)`` noise map, so a
degradation that got the arithmetic wrong would not fail loudly - it would quietly shift the
whole depth axis of the selection function. These check the produced pixels rather than the
formula.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from conftest import SHAPE, make_tile
from rbh.depth import (
    degrade_band,
    degrade_tile,
    depth_of,
    limiting_magnitude,
    noise_ratio,
)
from rbh.tile import BandImage, Tile


@pytest.fixture
def tile(rng: np.random.Generator) -> Tile:
    """A two-band noise tile with a realistic weight level."""
    noise = rng.normal(0.0, 1.0, size=SHAPE).astype(np.float32)
    other = rng.normal(0.0, 1.0, size=SHAPE).astype(np.float32)
    return make_tile({"F606W": noise, "F814W": other})


@pytest.mark.parametrize("fraction", [0.5, 0.25, 0.1])
def test_noise_grows_as_one_over_root_exposure(
    tile: Tile, fraction: float, rng: np.random.Generator
) -> None:
    """The whole point: a quarter of the exposure must be twice as noisy, not some other number."""
    band = tile.bands[0]
    degraded = degrade_band(band, fraction, rng)
    assert noise_ratio(band, degraded) == pytest.approx(1 / math.sqrt(fraction), rel=0.05)


@pytest.mark.parametrize("fraction", [0.5, 0.25, 0.1])
def test_weight_scales_with_exposure(tile: Tile, fraction: float, rng: np.random.Generator) -> None:
    """Weight must track exposure, or the noise map and the pixels disagree."""
    band = tile.bands[0]
    degraded = degrade_band(band, fraction, rng)
    covered = band.covered
    assert degraded.weight[covered] == pytest.approx(band.weight[covered] * fraction, rel=1e-6)


def test_the_noise_map_stays_consistent_with_the_pixels(
    tile: Tile, rng: np.random.Generator
) -> None:
    """A degraded band's own noise map must describe its own pixels.

    This is the failure that would matter: scaling the weight without adding the matching
    noise, or the reverse, leaves a band whose thresholds are computed from a map that no
    longer describes it, and every downstream signal-to-noise silently shifts.
    """
    band = tile.bands[0]
    degraded = degrade_band(band, 0.25, rng)
    _, measured_sigma = degraded.background_and_sigma()
    predicted = float(np.median(degraded.noise_map()[degraded.covered]))
    assert measured_sigma == pytest.approx(predicted, rel=0.1)


def test_full_exposure_is_a_no_op(tile: Tile, rng: np.random.Generator) -> None:
    band = tile.bands[0]
    assert degrade_band(band, 1.0, rng) is band


@pytest.mark.parametrize("fraction", [0.0, -0.5, 1.5])
def test_impossible_fractions_are_refused(
    tile: Tile, fraction: float, rng: np.random.Generator
) -> None:
    """Deeper cannot be simulated: noise can be added, not removed."""
    with pytest.raises(ValueError, match="exposure_fraction"):
        degrade_band(tile.bands[0], fraction, rng)


def test_uncovered_pixels_stay_uncovered(rng: np.random.Generator) -> None:
    """Zero weight means no data, and no amount of scaling turns that into data."""
    science = rng.normal(0.0, 1.0, size=SHAPE).astype(np.float32)
    tile = make_tile({"F606W": science})
    band = tile.bands[0]
    holed = BandImage(
        filter_name=band.filter_name,
        science=band.science,
        weight=np.where(np.arange(SHAPE[1])[None, :] < 20, 0.0, band.weight).astype(np.float32),
        zeropoint_ab=band.zeropoint_ab,
    )
    degraded = degrade_band(holed, 0.25, rng)
    blank = ~holed.covered
    assert not degraded.covered[blank].any()
    assert degraded.science[blank] == pytest.approx(holed.science[blank])


def test_degrading_a_tile_degrades_every_band(tile: Tile, rng: np.random.Generator) -> None:
    degraded = degrade_tile(tile, 0.25, rng)
    assert len(degraded.bands) == len(tile.bands)
    for before, after in zip(tile.bands, degraded.bands, strict=True):
        assert noise_ratio(before, after) == pytest.approx(2.0, rel=0.05)


def test_limiting_magnitude_falls_with_depth(tile: Tile, rng: np.random.Generator) -> None:
    """Shallower data must reach a brighter limiting magnitude, i.e. a smaller number."""
    deep = depth_of(tile)["F606W"]
    shallow = depth_of(degrade_tile(tile, 0.25, rng))["F606W"]
    assert shallow < deep
    # A quarter of the exposure is twice the noise, so 2.5*log10(2) = 0.75 mag shallower.
    assert deep - shallow == pytest.approx(2.5 * math.log10(2.0), abs=0.1)


def test_limiting_magnitude_scales_with_aperture(tile: Tile) -> None:
    """A larger aperture collects more noise, so the limit is brighter."""
    band = tile.bands[0]
    small = limiting_magnitude(band, 0.2, tile.pixel_scale_arcsec)
    large = limiting_magnitude(band, 0.8, tile.pixel_scale_arcsec)
    assert large < small
