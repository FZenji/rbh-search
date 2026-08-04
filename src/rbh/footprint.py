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

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from astropy import units as u
from mocpy import MOC

from rbh.area import SkyPatch, completeness_at
from rbh.manifest import Product
from rbh.reference import WAKE_LIMIT_BELOW_POINT_SOURCE_MAG

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from astropy.wcs import WCS

#: Order used for the first, throwaway parse of a region - just fine enough to measure how
#: big the footprint is, so :func:`order_for` can choose the real one. Measured over-count on
#: an 11 arcmin^2 disc, which is where the fixed-order approach came from and why it was
#: wrong:
#:
#: ===== ========== ==========
#: order cell size  over-count
#: ===== ========== ==========
#: 12    51.5"      +88%
#: 14    12.9"      +13.7%
#: 16    3.2"       +3.9%
#: 17    1.6"       +2.0%
#: 18    0.8"       +1.0%
#: ===== ========== ==========
#:
#: Every row of that table is true only for an 11 arcmin^2 footprint. See :func:`order_for`.
DEFAULT_ORDER = 18

#: Target relative over-count. The order is chosen per footprint to stay under this.
TARGET_BIAS = 0.02

#: Finest order mocpy accepts. Reaching it means the footprint is smaller than the
#: quantisation can resolve at the requested accuracy, which is worth knowing rather than
#: silently accepting.
MAX_ORDER = 29


def order_for(area_arcmin2_: float, target_bias: float = TARGET_BIAS) -> int:
    """Choose a HEALPix order so a footprint of this size quantises to within ``target_bias``.

    **The bias is not a constant, and treating it as one is how this went wrong.** A MOC
    over-covers a shape's boundary, so the error scales as perimeter over area - which means
    it depends on the footprint's *size*, not just on the cell size. Measured on a disc:

    * 11 arcmin^2 at order 18 -> +1.0%
    * 0.11 arcmin^2 at order 18 -> **+12%**

    Both were "0.8 arcsec cells", and the first was measured, documented as the bias, and
    used to justify a fixed order. The second is a 20 arcsec tile, which is exactly the size
    the sweep works in. A test using only the large footprint passed throughout.

    For a roughly square footprint of side ``s`` and cell size ``c`` the fractional
    over-count is about ``2c/s``, so the order needed grows as the footprint shrinks. This
    solves for it and clamps to :data:`MAX_ORDER`.
    """
    side_arcsec = math.sqrt(max(area_arcmin2_, 1e-9)) * 60.0
    wanted_cell_arcsec = 0.5 * max(target_bias, 1e-6) * side_arcsec
    whole_sky_arcsec2 = 4.0 * math.pi * (180.0 * 3600.0 / math.pi) ** 2

    for order in range(4, MAX_ORDER + 1):
        cell_arcsec = math.sqrt(whole_sky_arcsec2 / (12 * 4**order))
        if cell_arcsec <= wanted_cell_arcsec:
            return order
    return MAX_ORDER


#: Square arcminutes in a square degree, for reporting.
ARCMIN2_PER_DEG2 = 3600.0


def circular_footprint(
    ra_deg: float, dec_deg: float, area_arcmin2: float, order: int | None = None
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
    depth = order_for(area_arcmin2) if order is None else order
    radius = np.sqrt(max(area_arcmin2, 0.0) / np.pi) * u.arcmin
    return MOC.from_cone(lon=ra_deg * u.deg, lat=dec_deg * u.deg, radius=radius, max_depth=depth)


def region_footprint(s_region: str, order: int | None = None) -> MOC | None:
    """Parse a CAOM ``s_region`` STC-S string into a MOC, or None if it cannot be used.

    This is the footprint the archive actually recorded - usually a polygon tracing the
    detector outline, chip gaps and all - and it is strictly better than the disc below.
    Measured over-count at :data:`DEFAULT_ORDER` for a 3.4 arcmin ACS-sized square is +1.1%,
    the same quantisation bias a disc of similar size carries.

    Returns None rather than raising on anything unparseable. Thirty years of archive
    metadata contains malformed and missing regions, and one bad row must not take out a
    manifest build; the caller falls back to a disc and the degradation is visible in the
    count of products lacking a region.
    """
    if not s_region or not s_region.strip():
        return None
    try:
        coarse = MOC.from_stcs(s_region.strip(), max_depth=DEFAULT_ORDER)
    except (ValueError, TypeError, RuntimeError):
        return None
    if order is not None:
        return _reparse(s_region, order) or coarse
    # Re-parse at an order chosen from the footprint's own size. One coarse pass is needed
    # first because the size is not known until the region has been read once, and the bias
    # at DEFAULT_ORDER is small enough that it does not mislead the choice.
    refined = _reparse(s_region, order_for(area_arcmin2(coarse)))
    return refined or coarse


def _reparse(s_region: str, order: int) -> MOC | None:
    try:
        return MOC.from_stcs(s_region.strip(), max_depth=order)
    except (ValueError, TypeError, RuntimeError):
        return None


def product_footprint(product: Product, order: int | None = None) -> MOC:
    """Best available footprint for a product: its real region if it has one, else a disc."""
    return region_footprint(product.s_region, order) or circular_footprint(
        product.ra_deg, product.dec_deg, product.area_arcmin2, order
    )


def region_coverage(products: Sequence[Product]) -> float:
    """Fraction of products carrying a real footprint rather than falling back to a disc.

    Reported alongside any overlap number, because the disc fallback is wrong precisely at
    the edges where partial overlaps are decided. An overlap fraction computed over products
    that are mostly discs is indicative, not measured.
    """
    if not products:
        return 1.0
    with_region = sum(1 for p in products if region_footprint(p.s_region) is not None)
    return with_region / len(products)


def tile_region(wcs: WCS, shape: Sequence[int]) -> str:
    """Exact STC-S footprint of a tile, from its own WCS corners.

    Unlike everything else in this module this is not an approximation: a tile is a rectangle
    on a known projection, so its corners are exactly where the WCS says they are. Recording
    it in the sweep's per-tile result makes the survey footprint computable from committed
    outputs alone, with no manifest and no archive query - which is what lets the published
    area be as resumable and deterministic as the sweep itself (ADR-0020).

    Corners are traced in order rather than as a bounding box, so a rotated tile stays a
    rotated rectangle instead of growing to the box that contains it.
    """
    height, width = int(shape[0]), int(shape[1])
    corners = [(0, 0), (width, 0), (width, height), (0, height)]
    sky = [wcs.pixel_to_world(float(x), float(y)) for x, y in corners]
    return "POLYGON " + " ".join(f"{p.ra.deg:.8f} {p.dec.deg:.8f}" for p in sky)


def union(mocs: Iterable[MOC]) -> MOC:
    """Combine any number of footprints. Empty input gives an empty MOC, not an error."""
    result: MOC | None = None
    for moc in mocs:
        result = moc if result is None else result.union(moc)
    return result if result is not None else MOC.new_empty(max_depth=DEFAULT_ORDER)


def area_arcmin2(moc: MOC) -> float:
    """Return the sky area of a MOC in square arcminutes."""
    return float(moc.sky_fraction * 4.0 * np.pi * (180.0 / np.pi) ** 2 * ARCMIN2_PER_DEG2)


def survey_footprint(products: Sequence[Product], order: int | None = None) -> MOC:
    """Return the union footprint of a manifest: every product's sky, counted once."""
    return union(product_footprint(p, order) for p in products)


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


def account(products: Sequence[Product], order: int | None = None) -> AreaAccounting:
    """Compute summed and unique area for a manifest."""
    return AreaAccounting(
        summed_arcmin2=sum(p.area_arcmin2 for p in products),
        unique_arcmin2=area_arcmin2(survey_footprint(products, order)),
    )


def deepest_patches(products: Sequence[Product], order: int | None = None) -> list[SkyPatch]:
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
        footprint = product_footprint(product, order)
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
    order: int | None = None,
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
