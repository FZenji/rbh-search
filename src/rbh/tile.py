"""The normalised image unit every downstream stage consumes.

Nothing past this module knows which telescope produced the pixels. Adding a survey means
producing a :class:`Tile` from its native products and nothing else (ADR-0013).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from astropy.stats import sigma_clipped_stats

if TYPE_CHECKING:
    from astropy.wcs import WCS
    from numpy.typing import NDArray

#: AB magnitude system offset used with the HST ``PHOTFLAM``/``PHOTPLAM`` convention.
_AB_OFFSET = 2.408


def ab_zeropoint(photflam: float, photplam: float) -> float:
    """Return the AB magnitude zero point for an HST-style photometric calibration.

    Parameters
    ----------
    photflam
        Inverse sensitivity in erg cm^-2 Angstrom^-1 electron^-1.
    photplam
        Pivot wavelength in Angstroms.
    """
    return -2.5 * math.log10(photflam) - 5.0 * math.log10(photplam) - _AB_OFFSET


@dataclass(frozen=True)
class BandImage:
    """One filter's science and weight arrays on the tile grid.

    ``weight`` follows the drizzle convention: proportional to effective exposure time,
    so pixel noise scales as ``1 / sqrt(weight)``. Zero weight means no coverage.
    """

    filter_name: str
    science: NDArray[np.float32]
    weight: NDArray[np.float32]
    zeropoint_ab: float

    def __post_init__(self) -> None:
        if self.science.shape != self.weight.shape:
            msg = (
                f"science {self.science.shape} and weight {self.weight.shape} "
                f"shapes differ for band {self.filter_name}"
            )
            raise ValueError(msg)

    @property
    def covered(self) -> NDArray[np.bool_]:
        """Boolean mask of pixels with any exposure."""
        return self.weight > 0

    def background_and_sigma(self) -> tuple[float, float]:
        """Return the sigma-clipped background level and its noise at full weight.

        The noise is measured where the weight is at its median, so it is the reference
        the per-pixel noise map is scaled from.
        """
        good = self.covered
        if not good.any():
            msg = f"band {self.filter_name} has no covered pixels"
            raise ValueError(msg)
        _, median, std = sigma_clipped_stats(self.science[good], sigma=3.0, maxiters=5)
        return float(median), float(std)

    def noise_map(self) -> NDArray[np.float32]:
        """Return the per-pixel 1-sigma noise, scaled by the weight map.

        Archival depth is wildly non-uniform, so a single global sigma would put nearly
        every detection in the shallow edges of a mosaic (ADR-0005). Uncovered pixels get
        infinite noise, which gives them zero weight everywhere downstream.
        """
        _, sigma = self.background_and_sigma()
        weight = self.weight
        reference = float(np.median(weight[weight > 0]))
        noise = np.full(weight.shape, np.inf, dtype=np.float32)
        good = weight > 0
        noise[good] = sigma * np.sqrt(reference / weight[good], dtype=np.float32)
        return noise


@dataclass(frozen=True)
class Tile:
    """A square of sky with one or more filters on a common pixel grid."""

    bands: tuple[BandImage, ...]
    wcs: WCS
    pixel_scale_arcsec: float
    provenance: dict[str, str]

    def __post_init__(self) -> None:
        if not self.bands:
            msg = "a tile needs at least one band"
            raise ValueError(msg)
        shapes = {b.science.shape for b in self.bands}
        if len(shapes) != 1:
            msg = f"bands are not on a common grid: {shapes}"
            raise ValueError(msg)

    @property
    def shape(self) -> tuple[int, ...]:
        """Pixel dimensions of the tile."""
        return self.bands[0].science.shape

    @property
    def filter_names(self) -> tuple[str, ...]:
        """Names of the filters present, in tile order."""
        return tuple(b.filter_name for b in self.bands)

    @property
    def tier(self) -> str:
        """Filter-coverage tier: ``"A"`` for two or more filters, ``"B"`` for one.

        See ADR-0006 - Tier A supports cross-filter vetting, Tier B does not.
        """
        return "A" if len(self.bands) >= 2 else "B"

    def band(self, filter_name: str) -> BandImage:
        """Return the named band."""
        for b in self.bands:
            if b.filter_name == filter_name:
                return b
        msg = f"tile has no band {filter_name!r}; available: {self.filter_names}"
        raise KeyError(msg)

    def detection_image(self) -> tuple[NDArray[np.float32], NDArray[np.float32]]:
        """Combine the bands into a background-subtracted image and its noise map.

        Returns the inverse-variance weighted mean of the background-subtracted bands,
        which is the minimum-variance combination for a source of equal flux in each
        band, together with the noise map of that combination.
        """
        stack_num = np.zeros(self.shape, dtype=np.float64)
        stack_wgt = np.zeros(self.shape, dtype=np.float64)
        for b in self.bands:
            background, _ = b.background_and_sigma()
            inv_var = 1.0 / np.square(b.noise_map(), dtype=np.float64)
            stack_num += (b.science - background) * inv_var
            stack_wgt += inv_var
        good = stack_wgt > 0
        image = np.zeros(self.shape, dtype=np.float32)
        noise = np.full(self.shape, np.inf, dtype=np.float32)
        image[good] = (stack_num[good] / stack_wgt[good]).astype(np.float32)
        noise[good] = (1.0 / np.sqrt(stack_wgt[good])).astype(np.float32)
        return image, noise
