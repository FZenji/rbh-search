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

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from astropy import units as u

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
    #: Coefficient of variation of the width along the feature, or NaN when too few
    #: segments are measurable. Calibrated against, not merely reported - see
    #: :func:`_measure_width_variation`.
    width_variation: float
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
    width_half_extent_pixels: int = 14,
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
    width_half_extent_pixels
        Half-width of the band used for the transverse profile. Must be wide enough to
        contain the feature's wings and leave outer bins for the background estimate.
    straightness_bins
        Number of bins along the feature used to trace its spine.
    """
    points = np.column_stack([detection.xs, detection.ys]).astype(np.float64)
    centre = points.mean(axis=0)
    major, minor = principal_axis(points)

    along = project(points, centre, major)
    length_arcsec = float(along.max() - along.min()) * pixel_scale_arcsec

    width_arcsec = _measure_width(
        detection, image, centre, major, minor, pixel_scale_arcsec, width_half_extent_pixels
    )
    width_variation = _measure_width_variation(
        detection, image, centre, major, minor, width_half_extent_pixels
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
        width_variation=width_variation,
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
    major: NDArray[np.float64],
    minor: NDArray[np.float64],
    pixel_scale_arcsec: float,
    half_extent_pixels: int = 14,
) -> float:
    """Return the FWHM of the transverse profile, collapsed along the feature.

    The profile is built by summing flux along the whole length in bins of transverse
    offset, which beats the background down by roughly the square root of the length before
    any width is measured. A residual background taken from the outermost bins is then
    subtracted and the FWHM read off by interpolating to half maximum.

    The obvious alternative - a flux-weighted second moment over the detection mask - is
    biased high: clipping negatives to zero leaves the positive half of the background
    noise contributing weight at large transverse offsets, where the squared lever arm is
    greatest. On RBH-1 the effect is about 7%, inflating 0.256 to 0.274 arcsec, which
    propagates into the axis ratio and hence into the selection window.

    Note that 0.256 arcsec is still well above the quadrature sum of the published
    intrinsic width (0.06-0.15) and the nominal ACS PSF (~0.10). Whether the excess is a
    broader effective drizzled PSF or a genuinely wider feature cannot be separated from
    this cutout, which contains no stars to measure a PSF from. See ADR-0017.
    """
    along, across, flux, detection_along = _transverse_frame(
        detection, image, centre, major, minor, half_extent_pixels
    )
    inside = (
        (along >= detection_along.min())
        & (along <= detection_along.max())
        & (np.abs(across) <= half_extent_pixels)
    )
    if inside.sum() < 10:
        return float(np.abs(across[inside]).std() * _FWHM_PER_SIGMA * pixel_scale_arcsec)

    fwhm = _profile_fwhm_pixels(across[inside], flux[inside], half_extent_pixels)
    if math.isnan(fwhm):
        return float(np.abs(across[inside]).std() * _FWHM_PER_SIGMA * pixel_scale_arcsec)
    return fwhm * pixel_scale_arcsec


def _transverse_frame(
    detection: RidgeDetection,
    image: NDArray[np.float32],
    centre: NDArray[np.float64],
    major: NDArray[np.float64],
    minor: NDArray[np.float64],
    half_extent_pixels: int,
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    """Return along-axis and transverse coordinates, and flux, around one detection.

    Shared by the width and the width-variation measurements so that the two cannot drift
    apart in how they define the feature's frame.
    """
    ys_det, xs_det = detection.ys, detection.xs
    pad = half_extent_pixels + 2
    y0 = max(int(ys_det.min()) - pad, 0)
    y1 = min(int(ys_det.max()) + pad + 1, image.shape[0])
    x0 = max(int(xs_det.min()) - pad, 0)
    x1 = min(int(xs_det.max()) + pad + 1, image.shape[1])

    gy, gx = np.mgrid[y0:y1, x0:x1].astype(np.float64)
    points = np.column_stack([gx.ravel(), gy.ravel()])
    flux = image[y0:y1, x0:x1].astype(np.float64).ravel()
    detection_along = (np.column_stack([xs_det, ys_det]).astype(np.float64) - centre) @ major
    return (points - centre) @ major, (points - centre) @ minor, flux, detection_along


def _profile_fwhm_pixels(
    across: NDArray[np.float64], flux: NDArray[np.float64], half_extent_pixels: int
) -> float:
    """FWHM in pixels of the transverse profile of the pixels handed in, or NaN.

    NaN rather than a fallback, because callers differ in what they should do when a
    segment is too faint to measure: the whole-feature width has a second-moment estimate
    to fall back on, while a single segment of the variation measurement should simply be
    dropped.
    """
    edges = np.arange(-half_extent_pixels, half_extent_pixels + 1.0)
    sums, _ = np.histogram(across, bins=edges, weights=flux)
    counts, _ = np.histogram(across, bins=edges)
    valid = counts > 0
    if valid.sum() < 5:
        return float("nan")

    profile = np.zeros(sums.shape)
    profile[valid] = sums[valid] / counts[valid]
    offsets = 0.5 * (edges[:-1] + edges[1:])

    outer = valid & (np.abs(offsets) >= 0.75 * half_extent_pixels)
    background = float(np.median(profile[outer])) if outer.any() else 0.0
    profile = profile - background

    peak = float(profile.max())
    if peak <= 0:
        return float("nan")
    return _fwhm_from_profile(offsets, profile, peak)


def _measure_width_variation(
    detection: RidgeDetection,
    image: NDArray[np.float32],
    centre: NDArray[np.float64],
    major: NDArray[np.float64],
    minor: NDArray[np.float64],
    half_extent_pixels: int = 14,
    n_segments: int = 4,
) -> float:
    """How much the transverse width changes along the feature, as a coefficient of variation.

    A real wake is lumpy in width as well as in brightness; a constant-width ribbon reads
    as "extremely clean and linear", which is how the first blind test was won. That made
    this a property the synthetics have to match, and therefore one the calibration has to
    measure -- setting the generator's ``width_jitter`` by eye instead is the same mistake
    as the terminal knot, where a parameter no statistic constrained sat at a guessed
    value and turned out to be the loudest signal in the image.

    Few segments on purpose. Each one measures a width from a quarter of the length, so it
    has a quarter of the signal to beat the background down with; slicing finer measures
    noise. Segments too faint to yield a half-maximum crossing are dropped, and fewer than
    three surviving segments returns NaN rather than a number built from two points.
    """
    along, across, flux, detection_along = _transverse_frame(
        detection, image, centre, major, minor, half_extent_pixels
    )
    band = np.abs(across) <= half_extent_pixels
    edges = np.linspace(detection_along.min(), detection_along.max(), n_segments + 1)

    widths = []
    for i in range(n_segments):
        segment = band & (along >= edges[i]) & (along <= edges[i + 1])
        if segment.sum() < 10:
            continue
        fwhm = _profile_fwhm_pixels(across[segment], flux[segment], half_extent_pixels)
        if not math.isnan(fwhm) and fwhm > 0:
            widths.append(fwhm)

    if len(widths) < 3:
        return float("nan")
    values = np.array(widths)
    return float(values.std() / values.mean())


def _fwhm_from_profile(
    offsets: NDArray[np.float64], profile: NDArray[np.float64], peak: float
) -> float:
    """Full width at half maximum of a 1-D profile, by linear interpolation."""
    half = peak / 2.0
    apex = int(np.argmax(profile))

    def crossing(indices: range) -> float | None:
        previous = apex
        for i in indices:
            if profile[i] < half:
                span = profile[previous] - profile[i]
                if span <= 0:
                    return float(offsets[i])
                fraction = (profile[previous] - half) / span
                return float(offsets[previous] + fraction * (offsets[i] - offsets[previous]))
            previous = i
        return None

    right = crossing(range(apex + 1, profile.size))
    left = crossing(range(apex - 1, -1, -1))
    if right is None or left is None:
        # Profile never falls to half maximum inside the window; fall back to the
        # second moment of the positive part, which is at least bounded.
        weights = np.clip(profile, 0.0, None)
        total = weights.sum()
        if total <= 0:
            return 0.0
        mean = float((weights * offsets).sum() / total)
        variance = float((weights * (offsets - mean) ** 2).sum() / total)
        return float(np.sqrt(max(variance, 0.0))) * _FWHM_PER_SIGMA
    return abs(right - left)


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
