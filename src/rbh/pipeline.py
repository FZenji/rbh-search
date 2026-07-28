"""Composition of the per-tile detection stages.

:mod:`rbh.detect` and :mod:`rbh.linking` are independent primitives; this is where they
are wired together into stage 2 as described in ``docs/design/architecture.md``. Keeping
the composition separate is what lets each primitive stay importable on its own.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rbh.detect import DEFAULT_SCALES, RidgeDetection, bright_source_mask, detect_ridges
from rbh.linking import link_collinear

if TYPE_CHECKING:
    from rbh.tile import Tile


def detect_in_tile(
    tile: Tile,
    *,
    scales: tuple[float, ...] = DEFAULT_SCALES,
    low_snr: float = 3.0,
    high_snr: float = 5.0,
    min_pixels: int = 40,
    link: bool = True,
) -> list[RidgeDetection]:
    """Run stage 2 over a tile: combine bands, filter, threshold, and relink fragments.

    With ``link`` set, collinear fragments are rejoined afterwards, which is what keeps a
    knotty feature from being reported as several short ones. See :mod:`rbh.linking`.
    """
    image, noise = tile.detection_image()
    exclude = bright_source_mask(image, noise)
    detections = detect_ridges(
        image,
        noise,
        scales=scales,
        low_snr=low_snr,
        high_snr=high_snr,
        min_pixels=min_pixels,
        exclude=exclude,
    )
    if link:
        detections = link_collinear(detections, tile.pixel_scale_arcsec)
    return detections
