"""Stage 6 features: how wake-like is a detection, as measurements rather than a verdict.

ADR-0008 fixes the shape of this: produce a feature vector, never a classification. Experts
argued for three years over whether RBH-1 was a wake or an edge-on disc using better data than
we will have, so any threshold we write is a decision made with less information than the
people who got it wrong. Everything here is therefore a measured quantity, stored per
candidate, with weights to be fitted later against real negatives.

**One important absence.** ADR-0008 rates the rest-frame near-infrared counterpart as the
single most powerful discriminant: a wake is young stars with no old population, an edge-on
disc has a mature disc that glows in the near-IR. It is not computable here. Both filters in
the discovery data are optical, and at z ~ 1 even F814W samples the rest-frame near-ultraviolet
around 4100 A. The strongest available discriminant is therefore unavailable in this field, and
the features below are what remains. Fields with WFC3/IR or NIRCam coverage will do better,
which is an argument for the Tier A prioritisation in ADR-0006.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from rbh.geometry import principal_axis, project

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from rbh.tile import Tile


@dataclass(frozen=True)
class WakeFeatures:
    """Measured properties bearing on whether a feature is a wake or a disc galaxy.

    The per-field notes record **measured** discriminating power, not intended power. Three
    of the four behaved differently from the way they were designed, so the comments below
    have been rewritten to match the data rather than the intention. Measured over 29
    transplanted RBH-1 injections against 9 elongated galaxies harvested from the same tiles,
    as area under the ROC curve for "wake scores higher":

    ===========================  =====  ==========================================
    feature                      AUC    reading
    ===========================  =====  ==========================================
    ``transverse_colour_dip``    0.12   strongest; discs higher, as designed
    ``terminal_knot_contrast``   0.26   **reversed**: discs are more concentrated
    ``longitudinal_asymmetry``   0.57   no useful separation
    ``filling_factor``           0.43   no wake/disc separation - but see below
    ===========================  =====  ==========================================

    Caveats that matter more than the numbers: the negative sample is nine objects at axis
    ratio 3.1-4.5, considerably rounder than the ratio >= 8 the selection window demands, so
    it is not yet a representative sample of the contaminants we actually face. And the
    single most powerful discriminant in ADR-0008, the rest-frame near-infrared counterpart,
    is not computable in this field at all. Treat these AUCs as a first look, not a
    calibration.
    """

    #: Fraction of bins along the axis containing detected pixels. Does **not** separate wakes
    #: from discs (both sit at 1.00), but it cleanly separates *spurious linking joins*: the
    #: two found in the control tiles measure 0.80. That is the feature that does what the
    #: geometric gap cut could not (ADR-0016 amendment).
    filling_factor: float
    #: Flux-weighted centroid offset from the geometric centre, as a fraction of half-length.
    #: Designed to catch a wake brightening toward its tip. Measured AUC 0.57 - it does not.
    #: The reason is instructive: only the bright middle of a wake is detected, and that part
    #: is fairly symmetric, so the asymmetry lives in the faint tail the detector never sees.
    #: It does separate spurious joins (0.15-0.18) from both real classes (0.03-0.04).
    longitudinal_asymmetry: float
    #: Brightest along-axis bin over the median bin. Intended as a terminal-knot detector;
    #: measured AUC 0.26, i.e. it discriminates in **reverse**. Discs have bright centres and
    #: so score higher than wakes. Still useful, read as central concentration favouring discs.
    terminal_knot_contrast: float
    #: Whether the brightest bin lies in the outer third. Measured 0.38 of wakes against 0.44
    #: of discs: no separation.
    knot_is_terminal: bool
    #: Colour of the central transverse strip minus the flanking strips, in magnitudes. Discs
    #: come out higher as designed (+0.05 against -0.19 for wakes), the best of the four. But
    #: read it cautiously: for a feature thinner than the strip, the flanks are largely empty
    #: sky, so this may be measuring thinness as much as a dust lane.
    transverse_colour_dip: float
    #: Number of along-axis bins that had enough pixels to measure.
    n_bins_measured: int


def _binned_profile(
    along: NDArray[np.float64],
    weights: NDArray[np.float64],
    n_bins: int,
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.int_]]:
    """Return bin centres, summed weights, and pixel counts along the axis."""
    edges = np.linspace(along.min(), along.max(), n_bins + 1)
    counts, _ = np.histogram(along, bins=edges)
    sums, _ = np.histogram(along, bins=edges, weights=weights)
    return 0.5 * (edges[:-1] + edges[1:]), sums, counts


def measure_features(
    tile: Tile,
    ys: NDArray[np.intp],
    xs: NDArray[np.intp],
    *,
    n_bins: int = 10,
    transverse_width_pixels: float = 2.0,
) -> WakeFeatures:
    """Measure the stage 6 feature vector for one detection.

    Parameters
    ----------
    tile
        Tile the detection was found in; needs two bands for the colour feature.
    ys, xs
        Pixel coordinates of the detection.
    n_bins
        Bins along the feature's axis.
    transverse_width_pixels
        Half-width of the central strip used for the dust-lane test. The flanking strips run
        from one to three times this.
    """
    image, _ = tile.detection_image()
    points = np.column_stack([xs, ys]).astype(np.float64)
    centre = points.mean(axis=0)
    major, minor = principal_axis(points)
    along = project(points, centre, major)
    flux = np.clip(image[ys, xs].astype(np.float64), 0.0, None)

    _, sums, counts = _binned_profile(along, flux, n_bins)
    occupied = counts > 0
    filling = float(occupied.mean())

    half_length = float(max(np.abs(along).max(), 1e-9))
    total = float(flux.sum())
    asymmetry = float(abs((flux * along).sum() / total) / half_length) if total > 0 else 0.0

    lit = sums[occupied]
    median_bin = float(np.median(lit)) if lit.size else 0.0
    knot_contrast = float(lit.max() / median_bin) if median_bin > 0 else 0.0
    brightest = int(np.argmax(np.where(occupied, sums, -np.inf)))
    knot_is_terminal = brightest < n_bins / 3 or brightest >= 2 * n_bins / 3

    return WakeFeatures(
        filling_factor=filling,
        longitudinal_asymmetry=asymmetry,
        terminal_knot_contrast=knot_contrast,
        knot_is_terminal=bool(knot_is_terminal),
        transverse_colour_dip=_transverse_colour_dip(
            tile, ys, xs, centre, minor, transverse_width_pixels
        ),
        n_bins_measured=int(occupied.sum()),
    )


def _transverse_colour_dip(
    tile: Tile,
    ys: NDArray[np.intp],
    xs: NDArray[np.intp],
    centre: NDArray[np.float64],
    minor: NDArray[np.float64],
    width_pixels: float,
) -> float:
    """Colour of the spine minus the colour of the flanks, in magnitudes.

    An edge-on disc seen through its own dust is reddest along its midplane, so the spine
    comes out redder than the flanks and this is positive. A wake has no dust lane and should
    give roughly zero. Returns NaN when the tile has one band, or when either strip has too
    little flux to measure.
    """
    if len(tile.bands) < 2:
        return float("nan")
    blue, red = tile.bands[0], tile.bands[1]
    blue_bg, _ = blue.background_and_sigma()
    red_bg, _ = red.background_and_sigma()

    # Work over a dilated box so the flanks are sampled even where the detection is thin.
    pad = int(np.ceil(3 * width_pixels)) + 2
    y0 = max(int(ys.min()) - pad, 0)
    y1 = min(int(ys.max()) + pad + 1, tile.shape[0])
    x0 = max(int(xs.min()) - pad, 0)
    x1 = min(int(xs.max()) + pad + 1, tile.shape[1])
    gy, gx = np.mgrid[y0:y1, x0:x1].astype(np.float64)
    across = (np.column_stack([gx.ravel(), gy.ravel()]) - centre) @ minor

    blue_pixels = (blue.science[y0:y1, x0:x1].astype(np.float64) - blue_bg).ravel()
    red_pixels = (red.science[y0:y1, x0:x1].astype(np.float64) - red_bg).ravel()

    spine = np.abs(across) <= width_pixels
    flank = (np.abs(across) > width_pixels) & (np.abs(across) <= 3 * width_pixels)

    def colour(selection: NDArray[np.bool_]) -> float:
        blue_flux = float(blue_pixels[selection].sum())
        red_flux = float(red_pixels[selection].sum())
        if blue_flux <= 0 or red_flux <= 0:
            return float("nan")
        blue_mag = blue.zeropoint_ab - 2.5 * float(np.log10(blue_flux))
        red_mag = red.zeropoint_ab - 2.5 * float(np.log10(red_flux))
        return blue_mag - red_mag

    spine_colour = colour(spine)
    flank_colour = colour(flank)
    if not np.isfinite(spine_colour) or not np.isfinite(flank_colour):
        return float("nan")
    return float(spine_colour - flank_colour)


def separation(positives: NDArray[np.float64], negatives: NDArray[np.float64]) -> float:
    """Area under the ROC curve for one feature, computed exactly by rank.

    0.5 means the feature carries no information; 1.0 means it separates the two classes
    perfectly; below 0.5 means it separates them the other way round, which is informative
    rather than useless.
    """
    positives = positives[np.isfinite(positives)]
    negatives = negatives[np.isfinite(negatives)]
    if positives.size == 0 or negatives.size == 0:
        return float("nan")
    combined = np.concatenate([positives, negatives])
    order = combined.argsort()
    ranks = np.empty(combined.size, dtype=np.float64)
    ranks[order] = np.arange(1, combined.size + 1, dtype=np.float64)
    # Average ranks within ties so a constant feature scores exactly 0.5.
    _, inverse, counts = np.unique(combined, return_inverse=True, return_counts=True)
    sums = np.zeros(counts.size)
    np.add.at(sums, inverse, ranks)
    ranks = (sums / counts)[inverse]

    rank_sum = float(ranks[: positives.size].sum())
    n_pos, n_neg = float(positives.size), float(negatives.size)
    return (rank_sum - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)
