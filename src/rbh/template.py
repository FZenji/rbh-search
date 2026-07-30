"""Extract a real source's pixels so they can be transplanted elsewhere.

ADR-0017 makes the transplanted real object, not a model, the reference standard for
injection-recovery. This module cuts it out.

Two choices here matter more than they look:

* **Only the source's own pixels travel.** Pasting the whole rectangular stamp would paste
  a square of the original tile's noise, which both doubles the noise over a large area and
  leaves a detectable straight edge. Restricting to a dilated footprint keeps the added
  noise where the signal is.
* **Neighbours are masked by a rule, not by hand.** Significant pixels that are not
  connected to the source are zeroed. The template is then committed and inspected, because
  an error here propagates into every completeness number we publish.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from scipy import ndimage

from rbh.geometry import principal_axis, project

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from rbh.detect import RidgeDetection
    from rbh.tile import Tile


@dataclass(frozen=True)
class SourceTemplate:
    """Background-subtracted pixels of a real source, ready to transplant.

    ``stamps`` are in the same flux units as the tile they came from, already restricted
    to ``footprint``. ``noise_rms`` records the noise that unavoidably travels with those
    pixels, which the injection step needs in order to keep the noise penalty constant
    across the brightness axis.
    """

    name: str
    stamps: dict[str, NDArray[np.float32]]
    footprint: NDArray[np.bool_]
    noise_rms: dict[str, float]
    pixel_scale_arcsec: float
    source_pixels: int
    #: Along-axis extent of the source, needed downstream to scale the truth-matching radius
    #: when the template is injected.
    length_arcsec: float = 0.0

    @property
    def shape(self) -> tuple[int, ...]:
        """Stamp dimensions."""
        return self.footprint.shape

    @property
    def filter_names(self) -> tuple[str, ...]:
        """Bands present in the template."""
        return tuple(self.stamps)

    def total_flux(self, filter_name: str) -> float:
        """Return the summed flux of the template in one band."""
        return float(self.stamps[filter_name].sum())


def extract_template(
    tile: Tile,
    detection: RidgeDetection,
    *,
    name: str,
    pad_arcsec: float = 1.2,
    grow_pixels: int = 4,
    neighbour_snr: float = 6.0,
) -> SourceTemplate:
    """Cut a detected source out of a tile as a transplantable template.

    Parameters
    ----------
    tile
        Tile the source was found in.
    detection
        The source's pixels, from stage 2.
    name
        Label carried into provenance.
    pad_arcsec
        Margin added around the detection's bounding box.
    grow_pixels
        The detection footprint is dilated by this much before extraction, so the source's
        faint wings travel with it rather than being clipped at the threshold.
    neighbour_snr
        Pixels above this significance that are *not* connected to the grown footprint are
        treated as neighbours and zeroed.
    """
    pad = max(round(pad_arcsec / tile.pixel_scale_arcsec), grow_pixels + 2)
    y0 = max(int(detection.ys.min()) - pad, 0)
    y1 = min(int(detection.ys.max()) + pad + 1, tile.shape[0])
    x0 = max(int(detection.xs.min()) - pad, 0)
    x1 = min(int(detection.xs.max()) + pad + 1, tile.shape[1])

    source = np.zeros(tile.shape, dtype=bool)
    source[detection.ys, detection.xs] = True
    grown = ndimage.binary_dilation(source, iterations=grow_pixels)

    image, noise = tile.detection_image()
    with np.errstate(invalid="ignore", divide="ignore"):
        significance = np.where(np.isfinite(noise) & (noise > 0), image / noise, 0.0)
    neighbours = _neighbour_mask(significance > neighbour_snr, grown)

    footprint = (grown & ~neighbours)[y0:y1, x0:x1]
    stamps: dict[str, NDArray[np.float32]] = {}
    noise_rms: dict[str, float] = {}
    for band in tile.bands:
        background, sigma = band.background_and_sigma()
        cut = band.science[y0:y1, x0:x1].astype(np.float32) - np.float32(background)
        stamps[band.filter_name] = np.where(footprint, cut, np.float32(0.0)).astype(np.float32)
        noise_rms[band.filter_name] = sigma

    points = np.column_stack([detection.xs, detection.ys]).astype(np.float64)
    axis, _ = principal_axis(points)
    along = project(points, points.mean(axis=0), axis)

    return SourceTemplate(
        name=name,
        stamps=stamps,
        footprint=footprint,
        noise_rms=noise_rms,
        pixel_scale_arcsec=tile.pixel_scale_arcsec,
        source_pixels=int(footprint.sum()),
        length_arcsec=float(np.ptp(along)) * tile.pixel_scale_arcsec,
    )


def _neighbour_mask(significant: NDArray[np.bool_], source: NDArray[np.bool_]) -> NDArray[np.bool_]:
    """Return significant pixels belonging to objects that are not the source."""
    labels, count = ndimage.label(significant)
    if count == 0:
        return np.zeros(significant.shape, dtype=bool)
    touching = set(np.unique(labels[source & significant])) - {0}
    keep = np.isin(labels, list(touching)) if touching else np.zeros(labels.shape, dtype=bool)
    grown_neighbours = np.asarray(significant & ~keep)
    # Grow slightly so a neighbour's faint halo goes too.
    return np.asarray(ndimage.binary_dilation(grown_neighbours, iterations=2), dtype=bool)


def transform_template(
    template: SourceTemplate,
    *,
    quadrant_rotations: int = 0,
    mirror: bool = False,
) -> SourceTemplate:
    """Rotate by multiples of 90 degrees and optionally mirror, without interpolating.

    Restricting to quadrant rotations is deliberate: an arbitrary rotation resamples the
    pixels, which smooths the knots and would make transplants artificially easier to
    detect - the exact bias ADR-0017 exists to avoid.
    """
    turns = quadrant_rotations % 4

    def apply(array: NDArray[np.float32] | NDArray[np.bool_]) -> NDArray[np.float32]:
        out = np.rot90(array, turns)
        if mirror:
            out = np.fliplr(out)
        return np.ascontiguousarray(out)

    return SourceTemplate(
        name=template.name,
        stamps={k: apply(v).astype(np.float32) for k, v in template.stamps.items()},
        footprint=apply(template.footprint).astype(bool),
        noise_rms=dict(template.noise_rms),
        pixel_scale_arcsec=template.pixel_scale_arcsec,
        source_pixels=template.source_pixels,
        length_arcsec=template.length_arcsec,
    )
