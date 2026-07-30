"""Negative controls: the arithmetic, and the properties each control must have."""

from __future__ import annotations

import numpy as np
import pytest

from conftest import SHAPE, draw_line, make_tile
from rbh.config import SelectionWindow
from rbh.controls import (
    ControlResult,
    count_survivors,
    linking_cost,
    noise_model_scatter,
    noise_tiles,
    run_control,
    shuffled_filter_tiles,
    transformed_tiles,
)
from rbh.tile import Tile


def two_band(noise_field: np.ndarray) -> Tile:
    return make_tile(
        {"F606W": noise_field, "F814W": (noise_field[::-1] * 1.0).astype(np.float32)},
        zeropoints={"F606W": 26.485, "F814W": 25.933},
    )


def test_rates_use_the_searched_area() -> None:
    """A 20 by 20 arcsec tile is 400 arcsec^2, which is 3.086e-5 square degrees."""
    result = ControlResult("t", True, 1, 400.0, 10, 2)
    assert result.area_deg2 == pytest.approx(400.0 / 3600.0**2)
    assert result.survivors_per_deg2 == pytest.approx(2 / result.area_deg2)


def test_zero_survivors_still_gives_a_usable_upper_bound() -> None:
    """sqrt(N+1) so a null result bounds the rate instead of claiming zero uncertainty."""
    result = ControlResult("t", True, 1, 400.0, 10, 0)
    assert result.survivors_per_deg2 == 0.0
    assert result.poisson_error_per_deg2 > 0.0


def test_empty_area_does_not_divide_by_zero() -> None:
    result = ControlResult("t", True, 0, 0.0, 0, 0)
    assert result.survivors_per_deg2 == 0.0
    assert result.poisson_error_per_deg2 == 0.0


def test_noise_tiles_match_the_reference_statistics(noise_field: np.ndarray) -> None:
    reference = two_band(noise_field)
    tiles = noise_tiles(reference, 3, rng=np.random.default_rng(0))
    assert len(tiles) == 3
    for tile in tiles:
        assert tile.shape == reference.shape
        assert tile.filter_names == reference.filter_names
        for band, original in zip(tile.bands, reference.bands, strict=True):
            _, expected = original.background_and_sigma()
            _, got = band.background_and_sigma()
            assert got == pytest.approx(expected, rel=0.15)


def test_noise_tiles_contain_no_injected_source(noise_field: np.ndarray) -> None:
    """Any survivor in these is unambiguously false, which is the point of the control."""
    tiles = noise_tiles(two_band(noise_field), 4, rng=np.random.default_rng(1))
    result = run_control(tiles, "noise", link=True)
    assert result.n_tiles == 4
    assert result.survivors == 0, "default thresholds should find nothing in pure noise"


def test_transformed_tiles_preserve_flux_and_shape(noise_field: np.ndarray) -> None:
    tile = two_band(noise_field)
    for turns, mirror in ((1, False), (2, False), (0, True), (3, True)):
        out = transformed_tiles([tile], quadrant_rotations=turns, mirror=mirror)[0]
        assert out.shape == tile.shape
        for band, original in zip(out.bands, tile.bands, strict=True):
            assert band.science.sum() == pytest.approx(original.science.sum(), rel=1e-5)


def test_transform_really_changes_the_pixels(noise_field: np.ndarray) -> None:
    """Guard against the transform silently becoming a no-op.

    Worth an explicit test: the rotation control returns identical detection counts, and
    without this it would be impossible to tell genuine invariance from a broken transform.
    """
    tile = two_band(noise_field)
    rotated = transformed_tiles([tile], quadrant_rotations=1, mirror=False)[0]
    assert not np.array_equal(tile.bands[0].science, rotated.bands[0].science)
    assert np.array_equal(np.rot90(tile.bands[0].science, 1), rotated.bands[0].science)


@pytest.mark.parametrize(("turns", "mirror"), [(1, False), (2, False), (3, False), (0, True)])
def test_detector_is_invariant_under_quadrant_rotation(
    noise_field: np.ndarray, turns: int, mirror: bool
) -> None:
    """Identical counts before and after, so the detector is not keying on the pixel grid.

    Measured to hold exactly on real archival tiles; pinned here so it stays true. Note this
    is invariance, not artifact rejection - a detector-frame artifact rotates with the
    pixels.
    """
    line = draw_line(SHAPE, length_pixels=140.0, width_pixels=3.0, angle_deg=20.0, amplitude=6.0)
    tile = make_tile({"F606W": (noise_field + line).astype(np.float32)})
    transformed = transformed_tiles([tile], quadrant_rotations=turns, mirror=mirror)[0]

    window = SelectionWindow()
    assert count_survivors(tile, window=window, link=True) == count_survivors(
        transformed, window=window, link=True
    )


def test_shuffled_filters_pairs_bands_from_different_tiles() -> None:
    rng = np.random.default_rng(3)
    tiles = [
        make_tile(
            {
                "F606W": rng.normal(0, 1, SHAPE).astype(np.float32),
                "F814W": rng.normal(0, 1, SHAPE).astype(np.float32),
            }
        )
        for _ in range(3)
    ]
    shuffled = shuffled_filter_tiles(tiles)
    assert len(shuffled) == 3
    for index, tile in enumerate(shuffled):
        assert tile.bands[0] is tiles[index].bands[0]
        assert tile.bands[1] is tiles[(index + 1) % 3].bands[1]


def test_shuffling_needs_at_least_two_multiband_tiles(noise_field: np.ndarray) -> None:
    assert shuffled_filter_tiles([two_band(noise_field)]) == []
    assert shuffled_filter_tiles([make_tile({"F606W": noise_field})]) == []


def test_linking_cost_is_a_paired_comparison() -> None:
    with_link = ControlResult("real", True, 5, 2000.0, 40, 6)
    without = ControlResult("real", False, 5, 2000.0, 44, 4)
    cost = linking_cost(with_link, without)
    assert cost["added_by_linking"] == pytest.approx(2.0)
    assert cost["ratio"] == pytest.approx(1.5)


def test_linking_cost_handles_a_zero_baseline() -> None:
    """Zero survivors without linking is the expected case in pure noise."""
    none_either_way = linking_cost(
        ControlResult("n", True, 1, 400.0, 3, 0), ControlResult("n", False, 1, 400.0, 3, 0)
    )
    assert none_either_way["ratio"] == pytest.approx(1.0)

    linking_added_some = linking_cost(
        ControlResult("n", True, 1, 400.0, 3, 2), ControlResult("n", False, 1, 400.0, 3, 0)
    )
    assert linking_added_some["ratio"] == float("inf")


def test_noise_model_scatter_is_unity_for_a_correct_noise_map(
    rng: np.random.Generator,
) -> None:
    """The S/N image must have unit scatter at every coverage level, by construction.

    The weight distribution is deliberately realistic - a clear majority at full depth plus
    a shallower strip - because that is what makes a median weight meaningful. It also makes
    this a regression test for the reference-weight fix in ``background_and_sigma``: with the
    sigma estimated over the whole band instead, the majority and minority noise levels
    average together and both bins come out near 0.83 rather than 1.0.
    """
    tiles = []
    for _ in range(3):
        weight = np.full(SHAPE, 1000.0, dtype=np.float32)
        weight[:, 200:] = 250.0  # a quarter of the depth over ~22% of the tile
        science = rng.normal(0.0, 1.0, size=SHAPE).astype(np.float32)
        science[:, 200:] *= 2.0  # ...so genuinely twice the noise there
        tile = make_tile({"F606W": science})
        tile.bands[0].weight[:, :] = weight
        tiles.append(tile)

    measured = noise_model_scatter(tiles, weight_bins=((0.0, 0.5), (0.5, 10.0)))
    assert len(measured) == 2, "expected both weight bins to be populated"
    for scatter, count in measured.values():
        assert count > 500
        assert scatter == pytest.approx(1.0, abs=0.12)


def test_noise_model_scatter_detects_a_weight_correlated_error(
    rng: np.random.Generator,
) -> None:
    """The check must notice when the weight map mis-states how depth varies.

    Its leverage comes from binning on weight, so what it detects is error *correlated with*
    weight. A uniform weight map that understates the noise everywhere is invisible to it by
    construction, and that is the honest limit of the test rather than a defect: with no
    variation in the claimed depth there is nothing to compare against.

    Here the weight map claims a 16-fold depth change (so 4x the noise) while the pixels are
    only 2x noisier, and the two bins must disagree.
    """
    weight = np.full(SHAPE, 1000.0, dtype=np.float32)
    weight[:, 128:] = 1000.0 / 16.0
    science = rng.normal(0.0, 1.0, size=SHAPE).astype(np.float32)
    science[:, 128:] *= 2.0
    tile = make_tile({"F606W": science})
    tile.bands[0].weight[:, :] = weight

    measured = noise_model_scatter([tile], weight_bins=((0.0, 0.5), (0.5, 10.0)))
    assert len(measured) == 2
    low = measured[(0.0, 0.5)][0]
    high = measured[(0.5, 10.0)][0]
    assert abs(low - high) > 0.3, f"bins should disagree, got {low:.2f} and {high:.2f}"


def test_linking_never_reduces_survivors_on_the_same_pixels(noise_field: np.ndarray) -> None:
    """Merging fragments can only keep a count the same or shorten it by combining.

    It can also *create* a window-passing object out of two that each failed, which is
    precisely the false-positive channel being measured - so the survivor count may rise.
    What must not happen is a detection vanishing entirely.
    """
    line = draw_line(SHAPE, length_pixels=140.0, width_pixels=3.0, angle_deg=25.0, amplitude=5.0)
    tile = make_tile({"F606W": (noise_field * 0.2 + line).astype(np.float32)})
    raw_unlinked, _ = count_survivors(tile, window=SelectionWindow(), link=False)
    raw_linked, _ = count_survivors(tile, window=SelectionWindow(), link=True)
    assert raw_linked <= raw_unlinked
    assert raw_linked >= 1
