"""Harvesting the discriminator's negative class from real tiles."""

from __future__ import annotations

import numpy as np
import pytest

from conftest import PIXEL_SCALE, SHAPE, draw_line, make_tile
from rbh.negatives import find_elongated_sources, harvest


def test_finds_an_elongated_source(noise_field: np.ndarray) -> None:
    line = draw_line(SHAPE, length_pixels=120.0, width_pixels=10.0, angle_deg=30.0, amplitude=6.0)
    tile = make_tile({"F606W": (noise_field + line).astype(np.float32)})
    found = find_elongated_sources(tile, tile_name="t", min_axis_ratio=2.0)
    assert found
    best = found[0]
    assert best.axis_ratio >= 2.0
    assert best.tile_name == "t"
    assert best.n_pixels > 100


def test_ignores_round_sources(noise_field: np.ndarray) -> None:
    """A circular blob must not enter the negative class; it is not a contaminant."""
    ys, xs = np.mgrid[0 : SHAPE[0], 0 : SHAPE[1]]
    blob = 40.0 * np.exp(-(((ys - 128) ** 2 + (xs - 128) ** 2) / (2 * 8.0**2)))
    tile = make_tile({"F606W": (noise_field + blob).astype(np.float32)})
    assert find_elongated_sources(tile, min_axis_ratio=3.0) == []


def test_finds_nothing_in_pure_noise(noise_field: np.ndarray) -> None:
    tile = make_tile({"F606W": noise_field})
    assert find_elongated_sources(tile) == []


@pytest.mark.parametrize("length_pixels", [60.0, 140.0])
def test_reported_length_tracks_the_source(noise_field: np.ndarray, length_pixels: float) -> None:
    line = draw_line(
        SHAPE, length_pixels=length_pixels, width_pixels=8.0, angle_deg=0.0, amplitude=8.0
    )
    tile = make_tile({"F606W": (noise_field + line).astype(np.float32)})
    found = find_elongated_sources(tile, min_axis_ratio=2.0)
    assert found
    assert found[0].length_arcsec == pytest.approx(length_pixels * PIXEL_SCALE, rel=0.5)


def test_length_bounds_are_applied(noise_field: np.ndarray) -> None:
    line = draw_line(SHAPE, length_pixels=140.0, width_pixels=8.0, angle_deg=0.0, amplitude=8.0)
    tile = make_tile({"F606W": (noise_field + line).astype(np.float32)})
    assert find_elongated_sources(tile, min_axis_ratio=2.0, max_length_arcsec=0.5) == []
    assert find_elongated_sources(tile, min_axis_ratio=2.0, min_length_arcsec=50.0) == []


def test_results_are_sorted_and_deterministic(noise_field: np.ndarray) -> None:
    line = draw_line(SHAPE, length_pixels=120.0, width_pixels=10.0, angle_deg=30.0, amplitude=6.0)
    tile = make_tile({"F606W": (noise_field + line).astype(np.float32)})
    first = find_elongated_sources(tile, min_axis_ratio=2.0)
    second = find_elongated_sources(tile, min_axis_ratio=2.0)
    assert [s.axis_ratio for s in first] == [s.axis_ratio for s in second]
    assert [s.axis_ratio for s in first] == sorted((s.axis_ratio for s in first), reverse=True)


def test_harvest_labels_each_source_with_its_tile(noise_field: np.ndarray) -> None:
    line = draw_line(SHAPE, length_pixels=120.0, width_pixels=10.0, angle_deg=30.0, amplitude=6.0)
    tiles = [
        (name, make_tile({"F606W": (noise_field + line).astype(np.float32)})) for name in ("a", "b")
    ]
    found = harvest(tiles, min_axis_ratio=2.0)
    assert {s.tile_name for s in found} == {"a", "b"}
