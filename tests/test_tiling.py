"""The tessellation must partition the sky exactly, or candidates are lost or double-counted.

ADR-0004 fixes the scheme; the property that matters is that cores tile the sphere with no
gaps and no overlaps, so every detection has exactly one owner.
"""

from __future__ import annotations

import math

import pytest
from astropy import units as u
from mocpy import MOC

from rbh.footprint import area_arcmin2
from rbh.tiling import (
    MAX_FEATURE_ARCSEC,
    OVERLAP_ARCSEC,
    TILE_ORDER,
    SkyTile,
    at_order,
    cell_area_arcmin2,
    cell_side_arcsec,
    deduplicate,
    owning_tile,
    tiles_covering,
)


def patch(radius_arcmin: float = 8.0) -> MOC:
    return MOC.from_cone(
        lon=40.0 * u.deg, lat=-8.0 * u.deg, radius=radius_arcmin * u.arcmin, max_depth=TILE_ORDER
    )


def test_the_overlap_exceeds_the_longest_feature() -> None:
    """ADR-0004's requirement, asserted rather than trusted to a comment.

    Below this a candidate can be split at a tile boundary and lost from both sides.
    """
    assert OVERLAP_ARCSEC > MAX_FEATURE_ARCSEC


def test_tile_size_matches_the_memory_bound() -> None:
    """ADR-0004 asks for a few hundred MB per tile; the order is chosen from that, not taste."""
    side_pixels = cell_side_arcsec() / 0.05
    megabytes = side_pixels**2 * 4 * 4 / 1e6  # science + weight, two filters, float32
    assert 100 < megabytes < 500, f"a tile costs {megabytes:.0f} MB"


def test_cells_are_equal_area() -> None:
    """Equal area is what makes load balancing free, so it is worth asserting."""
    a = SkyTile(TILE_ORDER, 9417166)
    b = SkyTile(TILE_ORDER, 5000000)
    assert area_arcmin2(a.core()) == pytest.approx(cell_area_arcmin2(), rel=1e-6)
    assert area_arcmin2(a.core()) == pytest.approx(area_arcmin2(b.core()), rel=1e-6)


def test_tile_ids_are_stable_and_encode_the_tessellation() -> None:
    """A re-tiled release must not collide with results from the old one."""
    assert SkyTile(10, 42).tile_id == "hpx10-42"
    assert SkyTile(11, 42).tile_id != SkyTile(10, 42).tile_id


def test_a_tile_owns_its_own_centre() -> None:
    tile = tiles_covering(patch())[0]
    centre = tile.centre()
    assert tile.owns(centre.ra.deg, centre.dec.deg)


def test_cores_do_not_overlap() -> None:
    """The property the whole deduplication rests on: one position, at most one owner."""
    tiles = tiles_covering(patch())
    assert len(tiles) > 3
    for tile in tiles:
        centre = tile.centre()
        owners = [t.tile_id for t in tiles if t.owns(centre.ra.deg, centre.dec.deg)]
        assert owners == [tile.tile_id], f"{centre} is owned by {owners}"


def test_cores_leave_no_gaps() -> None:
    """Summed core area must equal the covered area, or sky falls between the tiles."""
    footprint = patch()
    tiles = tiles_covering(footprint)
    summed = sum(area_arcmin2(t.core()) for t in tiles)
    covered = area_arcmin2(at_order(footprint, TILE_ORDER))
    assert summed == pytest.approx(covered, rel=1e-6)


def test_the_processed_region_contains_the_core_plus_a_margin() -> None:
    """A feature owned by this tile must be fully imaged, or its morphology is wrong."""
    tile = tiles_covering(patch())[0]
    processed, core = tile.processed(), tile.core()
    assert area_arcmin2(processed) > area_arcmin2(core)
    assert area_arcmin2(core.difference(processed)) == pytest.approx(0.0, abs=1e-6)
    assert tile.processed_radius_arcsec() > 0.5 * cell_side_arcsec() + MAX_FEATURE_ARCSEC / 2


def test_tiles_covering_is_deterministic() -> None:
    """ADR-0012: the work list must not depend on what order anything was returned in."""
    first = [t.tile_id for t in tiles_covering(patch())]
    second = [t.tile_id for t in tiles_covering(patch())]
    assert first == second == sorted(first, key=lambda name: int(name.split("-")[1]))


def test_a_position_outside_every_core_has_no_owner() -> None:
    assert owning_tile(tiles_covering(patch()), 200.0, 45.0) is None


def test_deduplicate_keeps_each_candidate_once() -> None:
    """A candidate seen by two tiles is credited to the one that owns it, and only that one.

    Without this the candidate count is inflated by however much the tiles happen to overlap,
    which is a property of the tessellation rather than of the sky.
    """
    tiles = tiles_covering(patch())
    owner, neighbour = tiles[0], tiles[1]
    centre = owner.centre()
    position = {"ra_deg": centre.ra.deg, "dec_deg": centre.dec.deg}

    seen_by_both = [
        {"tile_id": owner.tile_id, **position},
        {"tile_id": neighbour.tile_id, **position},
    ]
    kept = deduplicate(seen_by_both, tiles)
    assert len(kept) == 1
    assert kept[0]["tile_id"] == owner.tile_id


def test_deduplicate_needs_no_tolerance() -> None:
    """Two genuinely distinct features a whisker apart must both survive.

    This is what ownership buys over merging by sky position: a matching radius large enough
    to catch duplicates is also large enough to collapse close neighbours, and there is no
    value that does one without risking the other.
    """
    tiles = tiles_covering(patch())
    owner = tiles[0]
    centre = owner.centre()
    offset = 0.5 / 3600.0  # half an arcsecond apart
    close_pair = [
        {"tile_id": owner.tile_id, "ra_deg": centre.ra.deg, "dec_deg": centre.dec.deg},
        {
            "tile_id": owner.tile_id,
            "ra_deg": centre.ra.deg + offset / math.cos(math.radians(centre.dec.deg)),
            "dec_deg": centre.dec.deg,
        },
    ]
    assert len(deduplicate(close_pair, tiles)) == 2
