"""Detector behaviour on synthetic data with known truth."""

from __future__ import annotations

import numpy as np
import pytest

from conftest import SHAPE, draw_line, make_tile
from rbh.detect import bright_source_mask, detect_ridges, ridge_response
from rbh.pipeline import detect_in_tile
from rbh.tile import Tile


def test_pure_noise_yields_no_detections(noise_field: np.ndarray) -> None:
    """The false-positive rate on empty sky must be zero at the default thresholds."""
    noise = np.ones(SHAPE, dtype=np.float32)
    assert detect_ridges(noise_field, noise, low_snr=3.0, high_snr=5.0, min_pixels=40) == []


def test_injected_line_is_detected(noise_field: np.ndarray) -> None:
    line = draw_line(SHAPE, length_pixels=120.0, width_pixels=3.0, angle_deg=30.0, amplitude=4.0)
    image = (noise_field + line).astype(np.float32)
    detections = detect_ridges(image, np.ones(SHAPE, dtype=np.float32))
    assert len(detections) >= 1
    assert max(d.n_pixels for d in detections) > 200


def test_detection_scales_with_source_brightness(noise_field: np.ndarray) -> None:
    noise = np.ones(SHAPE, dtype=np.float32)
    found = []
    for amplitude in (0.5, 2.0, 8.0):
        line = draw_line(
            SHAPE, length_pixels=120.0, width_pixels=3.0, angle_deg=30.0, amplitude=amplitude
        )
        detections = detect_ridges((noise_field + line).astype(np.float32), noise)
        found.append(max((d.peak_snr for d in detections), default=0.0))
    assert found[0] < found[1] < found[2]


def test_ridge_response_is_normalised_by_the_noise_map(noise_field: np.ndarray) -> None:
    """Doubling the noise in half the image must not double the detections there.

    Archival mosaics have wildly uneven depth; a global threshold would put nearly every
    detection in the shallow half (ADR-0005).
    """
    image = noise_field.copy()
    image[:, 128:] *= 4.0
    noise = np.ones(SHAPE, dtype=np.float32)
    noise[:, 128:] = 4.0

    response = ridge_response(image, noise)
    left = float(np.percentile(response[:, :128], 99))
    right = float(np.percentile(response[:, 128:], 99))
    assert right == pytest.approx(left, rel=0.35)


def test_uncovered_pixels_are_never_detected(noise_field: np.ndarray) -> None:
    """Zero-weight regions carry infinite noise and must produce nothing."""
    line = draw_line(SHAPE, length_pixels=120.0, width_pixels=3.0, angle_deg=0.0, amplitude=20.0)
    tile = make_tile({"F606W": (noise_field + line).astype(np.float32)})
    band = tile.bands[0]
    band.weight[:, :] = 0.0
    with pytest.raises(ValueError, match="no covered pixels"):
        band.noise_map()


def test_bright_source_mask_grows_around_bright_pixels() -> None:
    image = np.zeros(SHAPE, dtype=np.float32)
    image[128, 128] = 1000.0
    mask = bright_source_mask(image, np.ones(SHAPE, dtype=np.float32), grow_pixels=4)
    assert mask[128, 128]
    assert mask[128, 131]
    assert not mask[128, 160]


def test_high_threshold_must_not_be_below_low() -> None:
    with pytest.raises(ValueError, match="must not be below"):
        detect_ridges(
            np.zeros(SHAPE, dtype=np.float32),
            np.ones(SHAPE, dtype=np.float32),
            low_snr=5.0,
            high_snr=3.0,
        )


def _gapped_tile(noise_field: np.ndarray, gap_fraction: float) -> Tile:
    line = draw_line(
        SHAPE,
        length_pixels=140.0,
        width_pixels=3.0,
        angle_deg=25.0,
        amplitude=5.0,
        gap_fraction=gap_fraction,
    )
    return make_tile({"F606W": (noise_field * 0.2 + line).astype(np.float32)})


@pytest.mark.parametrize("gap_fraction", [0.05, 0.10, 0.15, 0.20])
def test_linking_rejoins_a_knotty_feature(noise_field: np.ndarray, gap_fraction: float) -> None:
    """A gapped line must come back as one object, not two.

    This is the RBH-1 failure mode reproduced synthetically: the threshold cuts the faint
    bridges between knots. The gaps here span 0.35 to 1.40 arcsec, all inside the 1.5
    arcsec linking tolerance.
    """
    tile = _gapped_tile(noise_field, gap_fraction)
    linked = detect_in_tile(tile, link=True)
    unlinked = detect_in_tile(tile, link=False)

    assert len(unlinked) == 2, "expected the gap to fragment the feature"
    assert len(linked) == 1
    assert linked[0].n_pixels > max(d.n_pixels for d in unlinked)


@pytest.mark.parametrize("gap_fraction", [0.25, 0.35, 0.50])
def test_linking_refuses_gaps_beyond_its_tolerance(
    noise_field: np.ndarray, gap_fraction: float
) -> None:
    """Beyond 1.5 arcsec the fragments stay separate, rather than linking indefinitely.

    Without this boundary, linking would happily chain unrelated collinear blobs across a
    whole tile and manufacture false positives.
    """
    tile = _gapped_tile(noise_field, gap_fraction)
    assert len(detect_in_tile(tile, link=True)) == 2


def test_detections_are_sorted_deterministically(noise_field: np.ndarray) -> None:
    line = draw_line(SHAPE, length_pixels=120.0, width_pixels=3.0, angle_deg=30.0, amplitude=5.0)
    image = (noise_field + line).astype(np.float32)
    noise = np.ones(SHAPE, dtype=np.float32)
    first = detect_ridges(image, noise)
    second = detect_ridges(image, noise)
    assert [d.n_pixels for d in first] == [d.n_pixels for d in second]
    assert first[0].n_pixels >= first[-1].n_pixels
