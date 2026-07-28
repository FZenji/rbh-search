"""Shared test fixtures.

The synthetic-line helper here is deliberately minimal: it exists to test the detector
and morphology code against known truth. The realistic, parameterised wake generator that
injection-recovery needs (ADR-0009) is Phase 2 work and will supersede it.
"""

from __future__ import annotations

import numpy as np
import pytest
from astropy.wcs import WCS
from numpy.typing import NDArray

from rbh.tile import BandImage, Tile

PIXEL_SCALE = 0.05
SHAPE = (256, 256)


def make_wcs(pixel_scale_arcsec: float = PIXEL_SCALE, shape: tuple[int, int] = SHAPE) -> WCS:
    """A plain tangent-plane WCS with north up and east left."""
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crpix = [shape[1] / 2, shape[0] / 2]
    wcs.wcs.crval = [40.0, -8.0]
    degrees = pixel_scale_arcsec / 3600.0
    wcs.wcs.cdelt = [-degrees, degrees]
    return wcs


def draw_line(
    shape: tuple[int, int],
    *,
    length_pixels: float,
    width_pixels: float,
    angle_deg: float,
    amplitude: float,
    centre: tuple[float, float] | None = None,
    gap_fraction: float = 0.0,
) -> NDArray[np.float32]:
    """Render a straight Gaussian-profile line into an empty array.

    ``gap_fraction`` blanks a band across the middle of the line, which is how a knotty
    feature looks once a threshold has cut its faint bridges.
    """
    cy, cx = centre if centre is not None else (shape[0] / 2, shape[1] / 2)
    ys, xs = np.mgrid[0 : shape[0], 0 : shape[1]].astype(np.float64)
    theta = np.radians(angle_deg)
    direction = np.array([np.cos(theta), np.sin(theta)])
    normal = np.array([-np.sin(theta), np.cos(theta)])

    dx, dy = xs - cx, ys - cy
    along = dx * direction[0] + dy * direction[1]
    across = dx * normal[0] + dy * normal[1]

    sigma = width_pixels / 2.3548200450309493
    profile = amplitude * np.exp(-0.5 * (across / sigma) ** 2)
    inside = np.abs(along) <= length_pixels / 2
    if gap_fraction > 0:
        inside &= np.abs(along) > (gap_fraction * length_pixels / 2)
    line: NDArray[np.float32] = np.asarray(profile * inside, dtype=np.float32)
    return line


def make_tile(
    science_by_filter: dict[str, NDArray[np.float32]],
    *,
    pixel_scale_arcsec: float = PIXEL_SCALE,
    weight_value: float = 2000.0,
    zeropoints: dict[str, float] | None = None,
) -> Tile:
    """Wrap synthetic arrays in a :class:`~rbh.tile.Tile`."""
    zeropoints = zeropoints or {}
    shape = next(iter(science_by_filter.values())).shape
    bands = tuple(
        BandImage(
            filter_name=name,
            science=data,
            weight=np.full(shape, weight_value, dtype=np.float32),
            zeropoint_ab=zeropoints.get(name, 26.0),
        )
        for name, data in sorted(science_by_filter.items())
    )
    return Tile(
        bands=bands,
        wcs=make_wcs(pixel_scale_arcsec, (shape[0], shape[1])),
        pixel_scale_arcsec=pixel_scale_arcsec,
        provenance={"fetched_from": "synthetic"},
    )


@pytest.fixture
def rng() -> np.random.Generator:
    """A seeded generator, so every synthetic test is reproducible (ADR-0012)."""
    return np.random.default_rng(20230208)


@pytest.fixture
def noise_field(rng: np.random.Generator) -> NDArray[np.float32]:
    """Pure Gaussian noise with no sources in it."""
    return rng.normal(0.0, 1.0, size=SHAPE).astype(np.float32)
