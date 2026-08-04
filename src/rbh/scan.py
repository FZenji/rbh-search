"""Search sky we have never looked at.

Everything before this was machinery: a detector that finds RBH-1, a selection function that
says what we would have found, a resumable sweep and an area accounting. All of it was
exercised on 2.3 arcmin^2 of sky, every tile of it in RBH-1's own field. This module is the
part that points the pipeline somewhere new.

**Read whole products, not cutouts.** Measured on the real archive, the cost of a fetch is
dominated by opening a 4300x4200 mosaic and parsing its headers, not by the bytes:

============ ============ ========= ==============
cutout       area         seconds   throughput
============ ============ ========= ==============
200x200      0.03 arcmin^2 68       1.5 arcmin^2/hr
800x800      0.44          57       28 arcmin^2/hr
2000x2000    2.78          61       165 arcmin^2/hr
============ ============ ========= ==============

A 20-arcsec cutout spends 60 seconds of network time to deliver a thirtieth of an arcminute.
Reading the whole product amortises that same open across a hundred times the sky, which is
the difference between a scan that finishes and one that does not.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from rbh.tile import Tile

#: Largest section read in one go, per side. An ACS/WFC mosaic is about 4200 pixels square,
#: so this takes most products whole. The cap exists because a tile is held in memory
#: uncompressed (ADR-0004): 4096 square, two bands, science plus weight at float32 is 268 MB,
#: which is the "few hundred MB" that ADR sets as the bound.
MAX_SECTION_PIXELS = 4096


@dataclass(frozen=True)
class ScanTarget:
    """One product pair to search, and where it points.

    Two filters because ADR-0006 makes cross-filter agreement the artifact defence, and a
    single-filter pointing is tier B - searchable, but yielding a weaker candidate.
    """

    name: str
    ra_deg: float
    dec_deg: float
    uris: tuple[str, ...]

    @property
    def tier(self) -> str:
        """ADR-0006 tier from the number of filters available."""
        return "A" if len(self.uris) >= 2 else "B"


def separation_deg(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Angular separation between two sky positions, in degrees."""
    ra1, dec1 = math.radians(a[0]), math.radians(a[1])
    ra2, dec2 = math.radians(b[0]), math.radians(b[1])
    cos_sep = math.sin(dec1) * math.sin(dec2) + math.cos(dec1) * math.cos(dec2) * math.cos(
        ra1 - ra2
    )
    return math.degrees(math.acos(max(-1.0, min(1.0, cos_sep))))


def spread_over_sky(
    candidates: Sequence[tuple[str, float, float]],
    count: int,
    *,
    min_separation_deg: float = 1.0,
    avoid: Sequence[tuple[float, float]] = (),
) -> list[tuple[str, float, float]]:
    """Pick pointings that are far apart, and away from anything to avoid.

    Two reasons the selection is not simply the first N rows. The archive is ordered by
    observation id, which clusters by proposal and therefore by field, so the first N would
    be many visits of the same sky - inflating the products searched while barely moving the
    unique area. And **RBH-1's own field must be excluded**: finding the object we calibrated
    on is not a discovery, and counting it as one would be the most embarrassing possible
    version of this project's central mistake (ADR-0015).

    Deterministic: candidates are consumed in the order given, which callers sort.
    """
    chosen: list[tuple[str, float, float]] = []
    for name, ra, dec in candidates:
        if len(chosen) >= count:
            break
        here = (ra, dec)
        if any(separation_deg(here, bad) < min_separation_deg for bad in avoid):
            continue
        if any(separation_deg(here, (r, d)) < min_separation_deg for _, r, d in chosen):
            continue
        chosen.append((name, ra, dec))
    return chosen


def tile_area_arcmin2(tile: Tile) -> float:
    """Sky area of a fetched tile, for reporting what was actually searched."""
    height, width = tile.shape
    return height * width * (tile.pixel_scale_arcsec / 60.0) ** 2
