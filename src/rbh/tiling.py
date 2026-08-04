"""The fixed sky tessellation the sweep works in.

ADR-0004 makes the unit of work a sky tile on a fixed tessellation, chosen once per data
release so tile IDs are stable and every result is addressable by position. HEALPix supplies
that for free: cells are equal-area, hierarchical, and identified by an integer that never
depends on what the archive happened to return.

**Ownership, not merging.** ADR-0004 says duplicate detections in overlap regions are "merged
by sky position". That works, but it needs a matching tolerance, and a tolerance is another
number that can be wrong - too small and a real duplicate survives twice, too large and two
genuinely distinct features collapse into one. This module instead gives every tile a
non-overlapping **core** and processes a larger box around it: a detection belongs to exactly
the tile whose core contains its centroid. The partition is exact, the deduplication needs no
parameter, and a candidate count cannot be inflated by how the sky was cut up. Recorded as an
amendment to ADR-0004.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from mocpy import MOC

if TYPE_CHECKING:
    from collections.abc import Sequence

#: HEALPix order of the tessellation, **chosen from ADR-0004's memory bound rather than by
#: preference**. Measured cell sizes and the memory a tile costs at 0.05 arcsec per pixel,
#: for science plus weight in two filters at float32:
#:
#: ===== ========= =========== =========
#: order cell side pixels/side per tile
#: ===== ========= =========== =========
#: 8     825"      16,490      4.4 GB
#: 9     412"      8,245       1.1 GB
#: 10    206"      4,123       272 MB
#: 11    103"      2,061       68 MB
#: ===== ========= =========== =========
#:
#: ADR-0004 asks for "a few hundred MB", which picks order 10 without ambiguity. Order 11
#: would halve the memory and double the per-tile overheads; order 9 would not fit.
TILE_ORDER = 10

#: Margin processed around each tile's core, in arcseconds.
#:
#: ADR-0004 requires overlap greater than ADR-0007's 25 arcsec maximum feature length, so a
#: candidate is never split at a boundary. Worth noting that **ownership by centroid halves
#: what is strictly needed**: a feature whose centroid lies in the core extends at most half
#: its length beyond it, so 12.5 arcsec would suffice. The ADR's figure is kept because extra
#: pixels are cheap, the sweep is detect-bound rather than read-bound, and a margin that is
#: obviously sufficient is worth more than one that is exactly sufficient.
OVERLAP_ARCSEC = 30.0

#: Longest feature the selection window admits (ADR-0007), which sets the margin above.
MAX_FEATURE_ARCSEC = 25.0

_WHOLE_SKY_ARCMIN2 = 4.0 * math.pi * (180.0 / math.pi) ** 2 * 3600.0


def cell_area_arcmin2(order: int = TILE_ORDER) -> float:
    """Return the area of one HEALPix cell.

    Equal-area is the property that makes load balancing free.
    """
    return float(_WHOLE_SKY_ARCMIN2 / (12 * 4**order))


def cell_side_arcsec(order: int = TILE_ORDER) -> float:
    """Return the nominal side of a cell, for sizing reads and memory."""
    return math.sqrt(cell_area_arcmin2(order)) * 60.0


@dataclass(frozen=True)
class SkyTile:
    """One work unit: a core cell that it owns, and a larger region it processes."""

    order: int
    ipix: int

    @property
    def tile_id(self) -> str:
        """Stable identifier. Encodes the tessellation, so a re-tiled release cannot collide."""
        return f"hpx{self.order}-{self.ipix}"

    def core(self) -> MOC:
        """Return the sky this tile owns. Cores tile the sphere exactly - no gaps, no overlaps."""
        return MOC.from_healpix_cells(
            np.array([self.ipix], dtype=np.uint64),
            np.array([self.order], dtype=np.uint8),
            self.order,
        )

    def centre(self) -> SkyCoord:
        """Barycentre of the core cell."""
        return self.core().barycenter()

    def processed_radius_arcsec(self) -> float:
        """Radius of the region read and searched: the core, plus the overlap margin.

        A cone rather than a padded rectangle because a HEALPix cell is not a rectangle, and
        a cone that contains it is far simpler than one that traces it. It reads about twice
        the core's area, which costs nothing worth optimising while the sweep is 86%
        detect-bound.
        """
        return 0.5 * math.sqrt(2.0) * cell_side_arcsec(self.order) + OVERLAP_ARCSEC

    def processed(self) -> MOC:
        """Return the region this tile reads and searches, as a MOC."""
        centre = self.centre()
        return MOC.from_cone(
            lon=centre.ra,
            lat=centre.dec,
            radius=self.processed_radius_arcsec() * u.arcsec,
            max_depth=self.order + 4,
        )

    def owns(self, ra_deg: float, dec_deg: float) -> bool:
        """Whether a detection at this position belongs to this tile.

        The whole deduplication story, in one containment test. No tolerance, no matching
        radius, and no way for a candidate to be counted twice or dropped between tiles.
        """
        return bool(self.core().contains_skycoords(SkyCoord(ra_deg, dec_deg, unit="deg"))[0])


def at_order(footprint: MOC, order: int) -> MOC:
    """Coarsen a MOC to ``order``, or return it unchanged if it is already that coarse.

    mocpy warns when asked to degrade to an order finer than the MOC already has, and this
    project treats warnings as errors, so the guard has to live somewhere rather than at
    every call site.
    """
    return footprint.degrade_to_order(order) if footprint.max_order > order else footprint


def tiles_covering(footprint: MOC, order: int = TILE_ORDER) -> list[SkyTile]:
    """Every tile whose core intersects a survey footprint, in sorted order.

    Sorted by pixel index so the work list is deterministic (ADR-0012) and so neighbouring
    tiles are adjacent in it - HEALPix nested indices are spatially coherent, which keeps a
    worker's reads near each other in the archive.
    """
    cells = np.asarray(at_order(footprint, order).flatten(), dtype=np.uint64)
    return [SkyTile(order=order, ipix=int(ipix)) for ipix in sorted(cells)]


def owning_tile(tiles: Sequence[SkyTile], ra_deg: float, dec_deg: float) -> SkyTile | None:
    """Return the one tile whose core contains a position, or None if there is none."""
    for tile in tiles:
        if tile.owns(ra_deg, dec_deg):
            return tile
    return None


def deduplicate(
    candidates: Sequence[dict[str, object]], tiles: Sequence[SkyTile]
) -> list[dict[str, object]]:
    """Keep each candidate once, credited to the tile whose core contains it.

    Candidates found in a tile's overlap margin but owned by a neighbour are dropped here -
    the neighbour will report them from its own search, and reporting both would inflate the
    count by however much the tiles happen to overlap.
    """
    kept: list[dict[str, object]] = []
    for candidate in candidates:
        tile_id = str(candidate.get("tile_id", ""))
        owner = owning_tile(tiles, float(candidate["ra_deg"]), float(candidate["dec_deg"]))  # type: ignore[arg-type]
        if owner is not None and owner.tile_id == tile_id:
            kept.append(candidate)
    return kept
