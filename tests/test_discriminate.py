"""Stage 6 features, and the rank statistic used to judge them."""

from __future__ import annotations

import numpy as np
import pytest

from conftest import SHAPE, draw_line, make_tile
from rbh.discriminate import measure_features, separation


def detection_of(image: np.ndarray, threshold: float) -> tuple[np.ndarray, np.ndarray]:
    ys, xs = np.nonzero(image > threshold)
    return ys, xs


def test_a_continuous_feature_fills_its_axis(noise_field: np.ndarray) -> None:
    line = draw_line(SHAPE, length_pixels=140.0, width_pixels=3.0, angle_deg=20.0, amplitude=8.0)
    tile = make_tile({"F606W": (noise_field + line).astype(np.float32)})
    features = measure_features(tile, *detection_of(line, 1.0))
    assert features.filling_factor == pytest.approx(1.0)


def test_two_separated_blobs_do_not_fill_their_axis(noise_field: np.ndarray) -> None:
    """The signature that distinguishes a spurious link from a real chain of knots.

    Measured on the real spurious joins found in the control tiles: filling factor 0.80,
    against 1.00 for both transplanted wakes and real elongated galaxies.
    """
    gapped = draw_line(
        SHAPE,
        length_pixels=140.0,
        width_pixels=3.0,
        angle_deg=20.0,
        amplitude=8.0,
        gap_fraction=0.55,
    )
    tile = make_tile({"F606W": (noise_field + gapped).astype(np.float32)})
    features = measure_features(tile, *detection_of(gapped, 1.0))
    assert features.filling_factor < 0.8


def test_a_symmetric_feature_has_low_longitudinal_asymmetry(noise_field: np.ndarray) -> None:
    line = draw_line(
        SHAPE,
        length_pixels=140.0,
        width_pixels=3.0,
        angle_deg=0.0,
        amplitude=8.0,
        gap_fraction=0.0,
    )
    tile = make_tile({"F606W": (noise_field + line).astype(np.float32)})
    features = measure_features(tile, *detection_of(line, 1.0))
    assert features.longitudinal_asymmetry < 0.15


def test_a_one_sided_feature_has_high_longitudinal_asymmetry(noise_field: np.ndarray) -> None:
    line = draw_line(SHAPE, length_pixels=140.0, width_pixels=3.0, angle_deg=0.0, amplitude=4.0)
    # Brighten one half so the flux centroid moves off the geometric centre.
    lopsided = line.copy()
    lopsided[:, 128:] *= 6.0
    tile = make_tile({"F606W": (noise_field + lopsided).astype(np.float32)})
    features = measure_features(tile, *detection_of(lopsided, 1.0))
    assert features.longitudinal_asymmetry > 0.2


def test_a_bright_knot_raises_the_contrast(noise_field: np.ndarray) -> None:
    line = draw_line(SHAPE, length_pixels=140.0, width_pixels=3.0, angle_deg=0.0, amplitude=4.0)
    knotted = line.copy()
    knotted[126:131, 190:200] += 60.0
    tile = make_tile({"F606W": (noise_field + knotted).astype(np.float32)})
    flat = measure_features(tile, *detection_of(line, 1.0))
    tile_knot = make_tile({"F606W": (noise_field + knotted).astype(np.float32)})
    bumpy = measure_features(tile_knot, *detection_of(knotted, 1.0))
    assert bumpy.terminal_knot_contrast > flat.terminal_knot_contrast


def test_colour_dip_is_nan_for_a_single_band_tile(noise_field: np.ndarray) -> None:
    """Tier B tiles carry no colour, and the feature must say so rather than invent one."""
    line = draw_line(SHAPE, length_pixels=120.0, width_pixels=3.0, angle_deg=0.0, amplitude=8.0)
    tile = make_tile({"F606W": (noise_field + line).astype(np.float32)})
    assert np.isnan(measure_features(tile, *detection_of(line, 1.0)).transverse_colour_dip)


def test_colour_dip_is_positive_when_the_spine_is_redder(noise_field: np.ndarray) -> None:
    """A dust lane reddens the midplane, which is the disc-like sign."""
    line = draw_line(SHAPE, length_pixels=140.0, width_pixels=8.0, angle_deg=0.0, amplitude=6.0)
    spine = draw_line(SHAPE, length_pixels=140.0, width_pixels=2.0, angle_deg=0.0, amplitude=6.0)
    tile = make_tile(
        {
            "F606W": (noise_field + line).astype(np.float32),
            "F814W": (noise_field + line + spine).astype(np.float32),
        },
        zeropoints={"F606W": 26.0, "F814W": 26.0},
    )
    features = measure_features(tile, *detection_of(line, 1.0))
    assert features.transverse_colour_dip > 0.05


def test_separation_is_half_for_an_uninformative_feature() -> None:
    values = np.array([1.0, 1.0, 1.0, 1.0])
    assert separation(values, values) == pytest.approx(0.5)


def test_separation_is_one_for_a_perfect_feature() -> None:
    assert separation(np.array([3.0, 4.0, 5.0]), np.array([0.0, 1.0, 2.0])) == pytest.approx(1.0)


def test_separation_below_half_means_reversed_not_useless() -> None:
    """A feature that sorts the classes the other way round still carries information."""
    assert separation(np.array([0.0, 1.0]), np.array([3.0, 4.0])) == pytest.approx(0.0)


def test_separation_handles_empty_and_non_finite_input() -> None:
    assert np.isnan(separation(np.array([]), np.array([1.0])))
    assert np.isnan(separation(np.array([np.nan, np.nan]), np.array([1.0])))
