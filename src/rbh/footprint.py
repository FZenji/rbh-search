"""Sky coverage as a MOC, so overlapping products are counted once.

ADR-0001 publishes the unique sky area as a first-class product; ADR-0014 fixes the format
as a MOC. The reason it cannot be a sum of product areas is that the corpus overlaps itself
heavily - the same sky is observed repeatedly across thirty years - and summing would inflate
the denominator of every density limit.

ADR-0019 goes further: the denominator is *effective* area, sky weighted by completeness at
its depth. That needs the overlap resolved cell by cell rather than product by product,
because two products can overlap partially, and the deeper one should claim the shared sky
without the shallower one losing the rest of its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from astropy import units as u
from mocpy import MOC

from rbh.area import SkyPatch, completeness_at
from rbh.reference import WAKE_LIMIT_BELOW_POINT_SOURCE_MAG

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from rbh.manifest import Product

#: HEALPix order for footprints, **chosen by measuring the bias rather than by reasoning
#: about cell sizes**. A MOC covers a shape with whole cells, so the boundary is always
#: over-covered, and for an 11 arcmin^2 product that boundary is a large fraction of the
#: shape. Measured over-count for a disc of that size:
#:
#: ===== ========== ========
#: order cell size  over-count
#: ===== ========== ========
#: 12    51.5"      +88%
#: 14    12.9"      +13.7%
#: 16    3.2"       +3.9%
#: 17    1.6"       +2.0%
#: 18    0.8"       +1.0%
#: ===== ========== ========
#:
#: The first draft of this module used 14 on the reasoning that 13 arcsec cells are "much
#: finer than an 11 arcmin^2 product", which sounds right and inflates every survey area by
#: a seventh. Order 18 costs a millisecond per footprint and leaves a **+1% one-sided
#: systematic**, which is small enough to state and carry rather than chase further, since
#: the circular-footprint approximation below is a larger error than that.
DEFAULT_ORDER = 18

#: Measured over-count at :data:`DEFAULT_ORDER`, for reporting alongside any area.
QUANTISATION_BIAS = 0.01

#: Square arcminutes in a square degree, for reporting.
ARCMIN2_PER_DEG2 = 3600.0


def circular_footprint(
    ra_deg: float, dec_deg: float, area_arcmin2: float, order: int = DEFAULT_ORDER
) -> MOC:
    """Approximate a product's footprint as a disc of the right area.

    **A real detector footprint is a rectangle, sometimes a chip-gapped one**, and this is a
    disc. It is used because the manifest currently carries a centre and an area rather than
    corners, and a disc of the correct area is the least-wrong thing that can be built from
    those two numbers.

    The approximation is fine for *total* area and wrong at the edges, which matters when two
    products partially overlap: a disc and a rectangle of equal area disagree about which sky
    is shared. Replace this with real corner polygons as soon as the manifest carries them -
    ``MOC.from_polygon_skycoord`` takes them directly - and treat any overlap number computed
    before then as indicative.
    """
    radius = np.sqrt(max(area_arcmin2, 0.0) / np.pi) * u.arcmin
    return MOC.from_cone(lon=ra_deg * u.deg, lat=dec_deg * u.deg, radius=radius, max_depth=order)


def union(mocs: Iterable[MOC]) -> MOC:
    """Combine any number of footprints. Empty input gives an empty MOC, not an error."""
    result: MOC | None = None
    for moc in mocs:
        result = moc if result is None else result.union(moc)
    return result if result is not None else MOC.new_empty(max_depth=DEFAULT_ORDER)


def area_arcmin2(moc: MOC) -> float:
    """Return the sky area of a MOC in square arcminutes."""
    return float(moc.sky_fraction * 4.0 * np.pi * (180.0 / np.pi) ** 2 * ARCMIN2_PER_DEG2)


def survey_footprint(products: Sequence[Product], order: int = DEFAULT_ORDER) -> MOC:
    """Return the union footprint of a manifest: every product's sky, counted once."""
    return union(circular_footprint(p.ra_deg, p.dec_deg, p.area_arcmin2, order) for p in products)


@dataclass(frozen=True)
class AreaAccounting:
    """The two areas, and the overlap between them, reported together on purpose.

    Quoting the unique area alone hides how much the corpus repeats itself, which is both a
    measure of wasted compute and - since repeat visits are what make the cross-visit
    artifact control possible (ADR-0019) - a measure of an asset.
    """

    summed_arcmin2: float
    unique_arcmin2: float

    @property
    def overlap_fraction(self) -> float:
        """Return the fraction of summed area that repeats sky already counted."""
        if self.summed_arcmin2 <= 0:
            return 0.0
        return 1.0 - self.unique_arcmin2 / self.summed_arcmin2

    @property
    def unique_deg2(self) -> float:
        """Return the unique area in square degrees, the unit a density limit uses."""
        return self.unique_arcmin2 / ARCMIN2_PER_DEG2


def account(products: Sequence[Product], order: int = DEFAULT_ORDER) -> AreaAccounting:
    """Compute summed and unique area for a manifest."""
    return AreaAccounting(
        summed_arcmin2=sum(p.area_arcmin2 for p in products),
        unique_arcmin2=area_arcmin2(survey_footprint(products, order)),
    )


def deepest_patches(products: Sequence[Product], order: int = DEFAULT_ORDER) -> list[SkyPatch]:
    """Resolve overlaps in favour of the deepest coverage, cell by cell (ADR-0019).

    Products are taken deepest first, and each one claims only the sky no deeper product has
    already claimed. A shallow product overlapping a deep one therefore keeps the part of
    itself that sticks out, rather than being discarded whole or diluting the deep sky it
    overlaps.

    Returns patches of disjoint sky, which is what :func:`rbh.area.effective_area_arcmin2`
    requires and cannot check for itself.
    """
    claimed: MOC | None = None
    patches: list[SkyPatch] = []

    for product in sorted(
        products,
        key=lambda p: (-p.point_source_limit_mag, p.uri),  # uri breaks ties stably
    ):
        footprint = circular_footprint(product.ra_deg, product.dec_deg, product.area_arcmin2, order)
        fresh = footprint if claimed is None else footprint.difference(claimed)
        gained = area_arcmin2(fresh)
        if gained > 0:
            patches.append(
                SkyPatch(
                    area_arcmin2=gained,
                    point_source_limit_mag=product.point_source_limit_mag,
                )
            )
        claimed = footprint if claimed is None else claimed.union(footprint)
    return patches


def effective_area_curve(
    products: Sequence[Product],
    magnitudes: Sequence[float],
    order: int = DEFAULT_ORDER,
) -> list[tuple[float, float]]:
    """Return the survey denominator against source magnitude, overlaps resolved (ADR-0019).

    This is the number a space-density limit divides by. It is smaller than the unique area
    at every magnitude, and much smaller near the depth limit, which is the whole point of
    reporting it as a curve.
    """
    patches = deepest_patches(products, order)
    return [
        (
            magnitude,
            sum(
                patch.area_arcmin2
                * completeness_at(
                    magnitude,
                    patch.point_source_limit_mag - WAKE_LIMIT_BELOW_POINT_SOURCE_MAG,
                )
                for patch in patches
            ),
        )
        for magnitude in magnitudes
    ]
