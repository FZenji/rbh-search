"""Morphology measured against synthetic lines of known geometry."""

from __future__ import annotations

import numpy as np
import pytest

from conftest import PIXEL_SCALE, SHAPE, draw_line, make_wcs
from rbh.detect import RidgeDetection
from rbh.morphology import measure


def detection_from(image: np.ndarray, threshold: float) -> RidgeDetection:
    ys, xs = np.nonzero(image > threshold)
    return RidgeDetection(ys=ys, xs=xs, peak_snr=float(image.max()), n_pixels=int(ys.size))


@pytest.mark.parametrize("length_pixels", [60.0, 120.0, 180.0])
def test_length_is_recovered(length_pixels: float) -> None:
    image = draw_line(
        SHAPE, length_pixels=length_pixels, width_pixels=3.0, angle_deg=30.0, amplitude=10.0
    )
    morphology = measure(detection_from(image, 1.0), image, make_wcs(), PIXEL_SCALE)
    assert morphology.length_arcsec == pytest.approx(length_pixels * PIXEL_SCALE, rel=0.05)


@pytest.mark.parametrize("width_pixels", [2.0, 4.0, 6.0])
def test_width_is_recovered(width_pixels: float) -> None:
    image = draw_line(
        SHAPE, length_pixels=120.0, width_pixels=width_pixels, angle_deg=0.0, amplitude=10.0
    )
    morphology = measure(detection_from(image, 0.5), image, make_wcs(), PIXEL_SCALE)
    assert morphology.width_arcsec == pytest.approx(width_pixels * PIXEL_SCALE, rel=0.20)


def test_axis_ratio_tracks_length_over_width() -> None:
    image = draw_line(SHAPE, length_pixels=150.0, width_pixels=3.0, angle_deg=45.0, amplitude=10.0)
    morphology = measure(detection_from(image, 1.0), image, make_wcs(), PIXEL_SCALE)
    assert morphology.axis_ratio == pytest.approx(150.0 / 3.0, rel=0.25)


def test_position_angle_uses_sky_convention() -> None:
    """A line drawn along image rows must read as position angle 90 degrees (east-west).

    With north up and east left, a horizontal line runs east-west, and position angle is
    measured north through east, so it should come out at 90 modulo 180.
    """
    image = draw_line(SHAPE, length_pixels=140.0, width_pixels=3.0, angle_deg=0.0, amplitude=10.0)
    morphology = measure(detection_from(image, 1.0), image, make_wcs(), PIXEL_SCALE)
    assert morphology.position_angle_deg == pytest.approx(90.0, abs=1.0)


def test_position_angle_is_independent_of_pixel_scale() -> None:
    image = draw_line(SHAPE, length_pixels=140.0, width_pixels=3.0, angle_deg=25.0, amplitude=10.0)
    coarse = measure(detection_from(image, 1.0), image, make_wcs(0.2), 0.2)
    fine = measure(detection_from(image, 1.0), image, make_wcs(0.01), 0.01)
    assert coarse.position_angle_deg == pytest.approx(fine.position_angle_deg, abs=0.5)


def test_straight_line_has_near_zero_straightness_residual() -> None:
    image = draw_line(SHAPE, length_pixels=160.0, width_pixels=4.0, angle_deg=20.0, amplitude=10.0)
    morphology = measure(detection_from(image, 1.0), image, make_wcs(), PIXEL_SCALE)
    assert morphology.straightness_arcsec < 0.02


def test_straightness_is_not_just_width() -> None:
    """A thick straight line must not be penalised for being thick.

    Measuring perpendicular pixel scatter for both quantities is the obvious
    implementation and is wrong; this guards against regressing to it.
    """
    thin = draw_line(SHAPE, length_pixels=160.0, width_pixels=2.0, angle_deg=20.0, amplitude=10.0)
    thick = draw_line(SHAPE, length_pixels=160.0, width_pixels=10.0, angle_deg=20.0, amplitude=10.0)
    thin_m = measure(detection_from(thin, 1.0), thin, make_wcs(), PIXEL_SCALE)
    thick_m = measure(detection_from(thick, 1.0), thick, make_wcs(), PIXEL_SCALE)

    assert thick_m.width_arcsec > 2 * thin_m.width_arcsec
    assert thick_m.straightness_arcsec < 0.05


def test_curved_feature_has_larger_straightness_residual() -> None:
    """A bent feature must score worse than a straight one."""
    straight = draw_line(
        SHAPE, length_pixels=120.0, width_pixels=3.0, angle_deg=0.0, amplitude=10.0
    )
    bent = np.maximum(
        draw_line(
            SHAPE,
            length_pixels=70.0,
            width_pixels=3.0,
            angle_deg=-12.0,
            amplitude=10.0,
            centre=(128.0, 96.0),
        ),
        draw_line(
            SHAPE,
            length_pixels=70.0,
            width_pixels=3.0,
            angle_deg=12.0,
            amplitude=10.0,
            centre=(128.0, 160.0),
        ),
    )
    straight_m = measure(detection_from(straight, 1.0), straight, make_wcs(), PIXEL_SCALE)
    bent_m = measure(detection_from(bent, 1.0), bent, make_wcs(), PIXEL_SCALE)
    assert bent_m.straightness_arcsec > 5 * straight_m.straightness_arcsec


def test_endpoints_bracket_the_centroid() -> None:
    image = draw_line(SHAPE, length_pixels=140.0, width_pixels=3.0, angle_deg=35.0, amplitude=10.0)
    m = measure(detection_from(image, 1.0), image, make_wcs(), PIXEL_SCALE)
    assert m.endpoint_a_ra_deg != m.endpoint_b_ra_deg
    assert min(m.endpoint_a_dec_deg, m.endpoint_b_dec_deg) <= m.centroid_dec_deg
    assert m.centroid_dec_deg <= max(m.endpoint_a_dec_deg, m.endpoint_b_dec_deg)
