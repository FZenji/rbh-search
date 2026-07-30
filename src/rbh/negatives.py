"""Harvest real elongated galaxies to serve as the discriminator's negative class.

ADR-0008 requires the wake-versus-disc score be fitted against real edge-on discs, not
against a model of one. External morphology catalogues are no help here: they cover bright,
low-redshift galaxies, whereas our contaminants are faint z ~ 1 sources at HST resolution.
So the negatives are harvested from the same archival tiles the search runs over, which also
guarantees they arrive at the right depth, pixel scale and PSF.

Detection here is deliberately **not** the ridge filter. Using the same detector to build the
negative class would select only the galaxies that already look like ridges, which is the
population we are trying to learn to reject - a circularity that would flatter any score
fitted on it. Standard segmentation photometry is used instead, and elongation is measured
from the segment's second moments.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from astropy.convolution import Gaussian2DKernel, convolve
from photutils.segmentation import SourceCatalog, detect_sources
from photutils.utils.exceptions import NoDetectionsWarning

if TYPE_CHECKING:
    from collections.abc import Sequence

    from numpy.typing import NDArray

    from rbh.tile import Tile


@dataclass(frozen=True)
class ElongatedSource:
    """A real elongated source, for use as a negative example."""

    tile_name: str
    ys: NDArray[np.intp]
    xs: NDArray[np.intp]
    length_arcsec: float
    width_arcsec: float
    axis_ratio: float
    position_angle_deg: float
    peak_snr: float

    @property
    def n_pixels(self) -> int:
        """Number of segment pixels."""
        return int(self.ys.size)


def find_elongated_sources(
    tile: Tile,
    *,
    tile_name: str = "",
    detect_snr: float = 2.0,
    smooth_fwhm_pixels: float = 2.5,
    min_pixels: int = 60,
    min_axis_ratio: float = 3.0,
    min_length_arcsec: float = 1.0,
    max_length_arcsec: float = 25.0,
) -> list[ElongatedSource]:
    """Find elongated extended sources in a tile by segmentation photometry.

    Parameters mirror the selection window loosely rather than exactly: the point is to
    collect the population that *could* be confused with a wake, so the axis-ratio floor is
    lower than the window's and the length range is wider. Filtering them down to the window
    is the discriminator's job, not the harvester's.
    """
    image, noise = tile.detection_image()
    finite = np.isfinite(noise) & (noise > 0)
    threshold = np.where(finite, detect_snr * noise, np.inf)

    kernel = Gaussian2DKernel(smooth_fwhm_pixels / 2.3548200450309493)
    smoothed = convolve(image, kernel, normalize_kernel=True)

    # Finding nothing is a normal outcome - most tiles contain no elongated source - and it
    # is handled explicitly below, so photutils' warning about it is noise to our callers.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NoDetectionsWarning)
        segments = detect_sources(smoothed, threshold, n_pixels=min_pixels)
    if segments is None:
        return []

    catalogue = SourceCatalog(image, segments)
    found: list[ElongatedSource] = []
    for source in catalogue:
        semimajor = float(source.semimajor_axis.value)
        semiminor = float(source.semiminor_axis.value)
        if semiminor <= 0:
            continue
        ratio = semimajor / semiminor
        # Second-moment sigmas: a Gaussian's full extent is roughly 4 sigma.
        length = 4.0 * semimajor * tile.pixel_scale_arcsec
        width = 4.0 * semiminor * tile.pixel_scale_arcsec
        if ratio < min_axis_ratio or not min_length_arcsec <= length <= max_length_arcsec:
            continue

        mask = segments.data == source.label
        ys, xs = np.nonzero(mask)
        with np.errstate(invalid="ignore", divide="ignore"):
            snr = np.where(finite, image / noise, 0.0)
        found.append(
            ElongatedSource(
                tile_name=tile_name,
                ys=ys,
                xs=xs,
                length_arcsec=length,
                width_arcsec=width,
                axis_ratio=ratio,
                position_angle_deg=float(np.degrees(source.orientation.value)) % 180.0,
                peak_snr=float(snr[ys, xs].max()),
            )
        )
    found.sort(key=lambda s: (-s.axis_ratio, int(s.ys[0]), int(s.xs[0])))
    return found


def harvest(
    tiles: Sequence[tuple[str, Tile]],
    **kwargs: object,
) -> list[ElongatedSource]:
    """Collect elongated sources across several named tiles."""
    out: list[ElongatedSource] = []
    for name, tile in tiles:
        out.extend(find_elongated_sources(tile, tile_name=name, **kwargs))  # type: ignore[arg-type]
    return out
