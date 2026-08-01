"""Shared geometric primitives.

Kept in its own module so that :mod:`rbh.morphology`, :mod:`rbh.linking` and
:mod:`rbh.colour` can all describe a feature's axis the same way without importing one
another.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray


def principal_axis(
    points: NDArray[np.float64],
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Return the unit major and minor axes of a point cloud.

    The sign of the major axis is pinned to a fixed convention rather than left to the
    SVD, whose output sign is arbitrary. Without this, the same feature could be reported
    with its endpoints swapped between runs, and the colour gradient's sign would flip
    with it (ADR-0012).
    """
    _, _, vt = np.linalg.svd(points - points.mean(axis=0), full_matrices=False)
    major = vt[0]
    if major[0] < 0 or (major[0] == 0 and major[1] < 0):
        major = -major
    minor = np.array([-major[1], major[0]])
    return major, minor


def project(
    points: NDArray[np.float64],
    centre: NDArray[np.float64],
    axis: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Project points onto an axis through a centre."""
    return (points - centre) @ axis


#: Conversion from a Gaussian standard deviation to full width at half maximum.
FWHM_PER_SIGMA = 2.3548200450309493

#: Segments along a feature used to measure how its width changes. Twelve rather than a
#: handful: the first version of :func:`transverse_variation` used four, and averaging over
#: a quarter of the length at a time smoothed away most of the structure it was meant to
#: detect - it saw a real-to-synthetic ratio of 1.11 where the same stamps measured with
#: twelve gave 1.31. Finer than this and each segment is measuring noise.
WIDTH_SEGMENTS = 12

#: Transverse half-width, in pixels, of the band :func:`transverse_variation` measures in.
#:
#: Fixed, after an adaptive band was tried and measured to be worse. The motivation for
#: adapting was sound - a fixed band clips the wings of a wide feature and not a narrow
#: one, so the statistic is not purely a measure of shape - but every implementation of it
#: cost more discriminating power than the bias was worth. Scored on one set of stamps:
#:
#: =========================================  ====  =========  ===
#: band                                       real  synthetic  AUC
#: =========================================  ====  =========  ===
#: fixed, 6 px                                0.19  0.15       0.86
#: fixed, 10 px                               0.24  0.22       0.66
#: adaptive from a second moment (= 14 px)    0.25  0.26       0.49
#: adaptive from a half-max crossing (11 px)  0.24  0.21       0.65
#: =========================================  ====  =========  ===
#:
#: The tell lives in the core; widening the band buries it in background. **A statistic
#: that cannot separate the classes is useless whatever its theoretical properties**, and
#: the adaptive versions were on their way to declaring the generator correct by going
#: blind - the most dangerous way for a check to fail.
#:
#: The cost is a real limitation, stated rather than hidden: this measures shape only for
#: features of roughly RBH-1's width. The calibration pins the width to within a few per
#: cent, so within this project the confound is small, but a survey covering a wide range
#: of intrinsic widths would need to revisit it.
WIDTH_BAND_PIXELS = 6.0


def transverse_variation(
    along: NDArray[np.float64],
    across: NDArray[np.float64],
    weight: NDArray[np.float64],
    *,
    n_segments: int = WIDTH_SEGMENTS,
) -> float:
    """Coefficient of variation of a feature's width along its own axis.

    **There is deliberately only one of these.** The calibration objective fits it and the
    blind-test pre-flight scores it, and for a while those were two different estimators -
    a four-segment half-max fit against a twelve-segment second moment. The generator was
    therefore fitted to one quantity and tested against another, so a calibration could
    report the width variation as matched while the pre-flight separated the classes at an
    AUC of 0.88. A cost function that does not measure the thing being tested is not a weak
    cost function, it is the wrong one.

    Each segment's width is a flux-weighted second moment of the transverse offset. That is
    biased high in an absolute sense, because clipped background noise contributes weight at
    large offsets where the lever arm is greatest - the same 7% effect that made
    :func:`~rbh.morphology._measure_width` use a half-max crossing instead. Here the bias
    is acceptable and the half-max is not: this is a *ratio* of widths within one feature,
    so a common multiplicative bias cancels, while a half-max crossing needs a
    well-sampled peak that a twelfth of a faint feature does not provide.

    Callers must pass **only the feature's own neighbourhood** along its axis. Handing in a
    whole stamp lets the segment edges span mostly empty sky, so the segments land in the
    wrong places and the profile is diluted by background; that alone cost about a third of
    the separation between the classes when the two callers disagreed about it.

    Returns NaN when fewer than four segments carry usable flux, rather than a number
    computed from two points.
    """
    band = np.abs(across) < WIDTH_BAND_PIXELS
    if band.sum() < n_segments * 4:
        return float("nan")

    edges = np.linspace(along[band].min(), along[band].max(), n_segments + 1)
    which = np.digitize(along[band], edges) - 1

    widths = []
    for segment in range(n_segments):
        selected = band.copy()
        selected[band] = which == segment
        w = weight[selected]
        if w.sum() <= 0:
            continue
        a = across[selected]
        centre = np.average(a, weights=w)
        widths.append(float(np.sqrt(np.average((a - centre) ** 2, weights=w))))

    if len(widths) < 4:
        return float("nan")
    values = np.array(widths)
    mean = values.mean()
    return float(values.std() / mean) if mean > 0 else float("nan")


def profile_fwhm_pixels(
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
    return fwhm_from_profile(offsets, profile, peak)


def fwhm_from_profile(
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
        return float(np.sqrt(max(variance, 0.0))) * FWHM_PER_SIGMA
    return abs(right - left)
