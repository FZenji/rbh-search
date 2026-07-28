"""Stage 3 - turn a ridge detection into measured geometry.

Every quantity carries its unit in its name, and angles on the sky use the astronomical
convention (position angle measured north through east) rather than pixel-grid angles, so
that measurements are independent of how a mosaic happens to be rotated or flipped.

Width and straightness are deliberately measured as *different* things. A naive
implementation reports the perpendicular scatter of the thresholded pixels for both,
which conflates "how thick is it" with "how bendy is it" and makes the straightness cut
meaningless.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from astropy import units as u
from scipy import ndimage

from rbh.geometry import principal_axis, project

if TYPE_CHECKING:
    from astropy.wcs import WCS
    from numpy.typing import NDArray

    from rbh.detect import RidgeDetection

#: Conversion from a Gaussian standard deviation to full width at half maximum.
_FWHM_PER_SIGMA = 2.3548200450309493


@dataclass(frozen=True)
class Morphology:
    """Measured geometry of a candidate linear feature."""

    length_arcsec: float
    width_arcsec: float
    axis_ratio: float
    position_angle_deg: float
    straightness_arcsec: float
    n_pixels: int
    peak_snr: float
    centroid_ra_deg: float
    centroid_dec_deg: float
    endpoint_a_ra_deg: float
    endpoint_a_dec_deg: float
    endpoint_b_ra_deg: float
    endpoint_b_dec_deg: float

    @property
    def is_linear(self) -> bool:
        """Whether the feature is elongated enough to be worth measuring further."""
        return self.axis_ratio >= 1.0


def measure(
    detection: RidgeDetection,
    image: NDArray[np.float32],
    wcs: WCS,
    pixel_scale_arcsec: float,
    *,
    width_grow_pixels: int = 3,
    straightness_bins: int = 8,
) -> Morphology:
    """Measure the geometry of one ridge detection.

    Parameters
    ----------
    detection
        The connected component from stage 2.
    image
        The background-subtracted image the detection was found in. Used for
        flux-weighted moments, which need the wings the threshold cut off.
    wcs
        World coordinate system of the tile.
    pixel_scale_arcsec
        Tile pixel scale.
    width_grow_pixels
        The mask is dilated by this much before measuring the transverse profile, so the
        width is not biased low by the detection threshold clipping the wings.
    straightness_bins
        Number of bins along the feature used to trace its spine.
    """
    points = np.column_stack([detection.xs, detection.ys]).astype(np.float64)
    centre = points.mean(axis=0)
    major, minor = principal_axis(points)

    along = project(points, centre, major)
    length_arcsec = float(along.max() - along.min()) * pixel_scale_arcsec

    width_arcsec = _measure_width(
        detection, image, centre, minor, pixel_scale_arcsec, width_grow_pixels
    )
    straightness_arcsec = _measure_straightness(
        points, centre, major, minor, pixel_scale_arcsec, straightness_bins
    )

    end_a = centre + major * float(along.min())
    end_b = centre + major * float(along.max())
    sky_a = wcs.pixel_to_world(end_a[0], end_a[1])
    sky_b = wcs.pixel_to_world(end_b[0], end_b[1])
    sky_c = wcs.pixel_to_world(centre[0], centre[1])
    position_angle = float(sky_a.position_angle(sky_b).to(u.deg).value) % 180.0

    return Morphology(
        length_arcsec=length_arcsec,
        width_arcsec=width_arcsec,
        axis_ratio=length_arcsec / width_arcsec if width_arcsec > 0 else float("inf"),
        position_angle_deg=position_angle,
        straightness_arcsec=straightness_arcsec,
        n_pixels=detection.n_pixels,
        peak_snr=detection.peak_snr,
        centroid_ra_deg=float(sky_c.ra.deg),
        centroid_dec_deg=float(sky_c.dec.deg),
        endpoint_a_ra_deg=float(sky_a.ra.deg),
        endpoint_a_dec_deg=float(sky_a.dec.deg),
        endpoint_b_ra_deg=float(sky_b.ra.deg),
        endpoint_b_dec_deg=float(sky_b.dec.deg),
    )


def _measure_width(
    detection: RidgeDetection,
    image: NDArray[np.float32],
    centre: NDArray[np.float64],
    minor: NDArray[np.float64],
    pixel_scale_arcsec: float,
    grow_pixels: int,
) -> float:
    """Return the FWHM of the flux-weighted transverse profile, in arcsec."""
    mask = np.zeros(image.shape, dtype=bool)
    mask[detection.ys, detection.xs] = True
    if grow_pixels > 0:
        mask = ndimage.binary_dilation(mask, iterations=grow_pixels)

    ys, xs = np.nonzero(mask)
    offsets = (np.column_stack([xs, ys]).astype(np.float64) - centre) @ minor
    flux = np.clip(image[ys, xs].astype(np.float64), 0.0, None)
    total = flux.sum()
    if total <= 0:
        return float(offsets.std()) * _FWHM_PER_SIGMA * pixel_scale_arcsec
    mean = float((flux * offsets).sum() / total)
    variance = float((flux * (offsets - mean) ** 2).sum() / total)
    return float(np.sqrt(max(variance, 0.0))) * _FWHM_PER_SIGMA * pixel_scale_arcsec


def _measure_straightness(
    points: NDArray[np.float64],
    centre: NDArray[np.float64],
    major: NDArray[np.float64],
    minor: NDArray[np.float64],
    pixel_scale_arcsec: float,
    n_bins: int,
) -> float:
    """Return the RMS deviation of the feature's spine from a straight line, in arcsec.

    The spine is the sequence of transverse centroids in bins along the feature. Using
    the spine rather than the raw pixel scatter separates curvature from width: a thick
    but perfectly straight feature scores zero here, as it should.
    """
    along = project(points, centre, major)
    across = project(points, centre, minor)
    edges = np.linspace(along.min(), along.max(), n_bins + 1)
    spine: list[float] = []
    for i in range(n_bins):
        upper = along <= edges[i + 1] if i == n_bins - 1 else along < edges[i + 1]
        selection = (along >= edges[i]) & upper
        if selection.sum() >= 3:
            spine.append(float(across[selection].mean()))
    if len(spine) < 3:
        return 0.0
    values = np.asarray(spine)
    # Remove any residual linear trend: a tilt means the principal axis was slightly off,
    # which is not curvature.
    x = np.arange(values.size, dtype=np.float64)
    slope, intercept = np.polyfit(x, values, 1)
    residual = values - (slope * x + intercept)
    return float(np.sqrt(np.mean(residual**2))) * pixel_scale_arcsec
