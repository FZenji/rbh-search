"""Colour measured along a feature's axis.

A runaway black hole lays down stars as it goes, so the stars nearest the leading tip are
the youngest and bluest and those nearest the host galaxy have had longest to redden. A
monotonic colour gradient along the axis is therefore a positive wake indicator, while an
edge-on disc galaxy is symmetric about its centre and reddest in the middle where its dust
lane is (see ``docs/science/false-positives.md``).

This module measures the gradient. Interpreting it is stage 6's job, and scoring rather
than cutting on it is required by ADR-0008.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from rbh.geometry import principal_axis, project

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from rbh.detect import RidgeDetection
    from rbh.tile import Tile


@dataclass(frozen=True)
class ColourProfile:
    """Colour as a function of position along a feature.

    ``along_arcsec`` runs from endpoint A to endpoint B, matching the endpoint labelling
    in :class:`~rbh.morphology.Morphology`. Positive ``gradient_mag_per_arcsec`` means the
    feature reddens from A toward B.
    """

    blue_filter: str
    red_filter: str
    along_arcsec: NDArray[np.float64]
    colour_ab: NDArray[np.float64]
    colour_error: NDArray[np.float64]
    gradient_mag_per_arcsec: float
    gradient_error: float

    @property
    def gradient_significance(self) -> float:
        """Gradient in units of its own uncertainty."""
        if self.gradient_error <= 0:
            return 0.0
        return abs(self.gradient_mag_per_arcsec) / self.gradient_error

    @property
    def reddens_toward_b(self) -> bool:
        """Whether the feature gets redder from endpoint A toward endpoint B."""
        return self.gradient_mag_per_arcsec > 0


def colour_profile(
    tile: Tile,
    detection: RidgeDetection,
    blue_filter: str,
    red_filter: str,
    *,
    n_bins: int = 8,
    min_pixels_per_bin: int = 8,
) -> ColourProfile:
    """Measure the colour profile along a detection's principal axis.

    Fluxes are summed over the detection's own pixels in each bin and converted to AB
    magnitudes with each band's zero point, so the result is a real colour rather than an
    instrumental ratio.
    """
    blue = tile.band(blue_filter)
    red = tile.band(red_filter)

    points = np.column_stack([detection.xs, detection.ys]).astype(np.float64)
    centre = points.mean(axis=0)
    major, _ = principal_axis(points)
    along = project(points, centre, major)

    blue_bg, _ = blue.background_and_sigma()
    red_bg, _ = red.background_and_sigma()
    blue_noise = blue.noise_map()
    red_noise = red.noise_map()

    edges = np.linspace(along.min(), along.max(), n_bins + 1)
    centres: list[float] = []
    colours: list[float] = []
    errors: list[float] = []

    for i in range(n_bins):
        upper = along <= edges[i + 1] if i == n_bins - 1 else along < edges[i + 1]
        selection = (along >= edges[i]) & upper
        if selection.sum() < min_pixels_per_bin:
            continue
        ys, xs = detection.ys[selection], detection.xs[selection]

        blue_flux = float((blue.science[ys, xs] - blue_bg).sum())
        red_flux = float((red.science[ys, xs] - red_bg).sum())
        if blue_flux <= 0 or red_flux <= 0:
            continue
        blue_err = float(np.sqrt(np.square(blue_noise[ys, xs], dtype=np.float64).sum()))
        red_err = float(np.sqrt(np.square(red_noise[ys, xs], dtype=np.float64).sum()))

        blue_mag = blue.zeropoint_ab - 2.5 * np.log10(blue_flux)
        red_mag = red.zeropoint_ab - 2.5 * np.log10(red_flux)
        sigma = 1.0857 * np.hypot(blue_err / blue_flux, red_err / red_flux)

        centres.append(float(0.5 * (edges[i] + edges[i + 1])) * tile.pixel_scale_arcsec)
        colours.append(float(blue_mag - red_mag))
        errors.append(float(sigma))

    along_arr = np.asarray(centres, dtype=np.float64)
    colour_arr = np.asarray(colours, dtype=np.float64)
    error_arr = np.asarray(errors, dtype=np.float64)

    gradient, gradient_error = _weighted_slope(along_arr, colour_arr, error_arr)
    return ColourProfile(
        blue_filter=blue_filter,
        red_filter=red_filter,
        along_arcsec=along_arr,
        colour_ab=colour_arr,
        colour_error=error_arr,
        gradient_mag_per_arcsec=gradient,
        gradient_error=gradient_error,
    )


def _weighted_slope(
    x: NDArray[np.float64], y: NDArray[np.float64], sigma: NDArray[np.float64]
) -> tuple[float, float]:
    """Return the inverse-variance weighted least-squares slope and its uncertainty."""
    if x.size < 3:
        return 0.0, 0.0
    weights = 1.0 / np.square(np.where(sigma > 0, sigma, np.inf))
    total = weights.sum()
    if total <= 0:
        return 0.0, 0.0
    mean_x = float((weights * x).sum() / total)
    mean_y = float((weights * y).sum() / total)
    sxx = float((weights * (x - mean_x) ** 2).sum())
    if sxx <= 0:
        return 0.0, 0.0
    slope = float((weights * (x - mean_x) * (y - mean_y)).sum() / sxx)
    return slope, float(np.sqrt(1.0 / sxx))
