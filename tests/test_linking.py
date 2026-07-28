"""Fragment linking: rejoin what a threshold cut, without joining unrelated things."""

from __future__ import annotations

import numpy as np
import pytest

from conftest import PIXEL_SCALE, SHAPE, draw_line
from rbh.detect import RidgeDetection
from rbh.linking import link_collinear


def fragment(
    *,
    length_pixels: float,
    angle_deg: float,
    centre: tuple[float, float],
    width_pixels: float = 3.0,
) -> RidgeDetection:
    image = draw_line(
        SHAPE,
        length_pixels=length_pixels,
        width_pixels=width_pixels,
        angle_deg=angle_deg,
        amplitude=10.0,
        centre=centre,
    )
    ys, xs = np.nonzero(image > 1.0)
    return RidgeDetection(ys=ys, xs=xs, peak_snr=10.0, n_pixels=int(ys.size))


def test_collinear_fragments_are_joined() -> None:
    a = fragment(length_pixels=40.0, angle_deg=0.0, centre=(128.0, 100.0))
    b = fragment(length_pixels=40.0, angle_deg=0.0, centre=(128.0, 150.0))
    merged = link_collinear([a, b], PIXEL_SCALE)
    assert len(merged) == 1
    assert merged[0].n_pixels == a.n_pixels + b.n_pixels


def test_a_chain_of_fragments_links_transitively() -> None:
    parts = [
        fragment(length_pixels=25.0, angle_deg=0.0, centre=(128.0, x))
        for x in (80.0, 110.0, 140.0, 170.0)
    ]
    merged = link_collinear(parts, PIXEL_SCALE)
    assert len(merged) == 1


def test_parallel_but_offset_fragments_are_not_joined() -> None:
    """Two lanes side by side are two objects, however collinear their axes look."""
    a = fragment(length_pixels=40.0, angle_deg=0.0, centre=(120.0, 100.0))
    b = fragment(length_pixels=40.0, angle_deg=0.0, centre=(140.0, 150.0))
    assert len(link_collinear([a, b], PIXEL_SCALE)) == 2


def test_fragments_at_different_angles_are_not_joined() -> None:
    a = fragment(length_pixels=40.0, angle_deg=0.0, centre=(128.0, 100.0))
    b = fragment(length_pixels=40.0, angle_deg=60.0, centre=(128.0, 145.0))
    assert len(link_collinear([a, b], PIXEL_SCALE)) == 2


def test_distant_fragments_are_not_joined() -> None:
    a = fragment(length_pixels=30.0, angle_deg=0.0, centre=(128.0, 40.0))
    b = fragment(length_pixels=30.0, angle_deg=0.0, centre=(128.0, 215.0))
    assert len(link_collinear([a, b], PIXEL_SCALE)) == 2


def test_gap_tolerance_is_expressed_in_arcsec_not_pixels() -> None:
    """The same sky separation must link identically whatever the pixel scale."""
    a = fragment(length_pixels=40.0, angle_deg=0.0, centre=(128.0, 100.0))
    b = fragment(length_pixels=40.0, angle_deg=0.0, centre=(128.0, 150.0))
    assert len(link_collinear([a, b], 0.05, max_gap_arcsec=1.5)) == 1
    # At a coarser scale the same pixel gap is a far bigger sky gap, so it must not link.
    assert len(link_collinear([a, b], 0.5, max_gap_arcsec=1.5)) == 2


def test_single_and_empty_inputs_pass_through() -> None:
    a = fragment(length_pixels=40.0, angle_deg=0.0, centre=(128.0, 128.0))
    assert link_collinear([], PIXEL_SCALE) == []
    assert len(link_collinear([a], PIXEL_SCALE)) == 1


def test_merged_output_is_sorted_by_size() -> None:
    small = fragment(length_pixels=20.0, angle_deg=90.0, centre=(60.0, 60.0))
    a = fragment(length_pixels=40.0, angle_deg=0.0, centre=(180.0, 100.0))
    b = fragment(length_pixels=40.0, angle_deg=0.0, centre=(180.0, 150.0))
    merged = link_collinear([small, a, b], PIXEL_SCALE)
    assert merged[0].n_pixels == pytest.approx(a.n_pixels + b.n_pixels)
    assert merged[0].n_pixels > merged[-1].n_pixels
