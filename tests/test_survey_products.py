"""The survey's published numbers must come from what was actually searched.

Everything here is derived from committed per-tile outputs and nothing else - no manifest, no
archive query - so the published area is exactly as reproducible as the sweep (ADR-0020) and
cannot drift from the sky the detector actually saw.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from astropy.wcs import WCS

from rbh.footprint import area_arcmin2, region_footprint, tile_region
from rbh.sweep import local_sources, run, survey_products
from rbh.tileio import read_tile
from rbh.workqueue import commit

FIXTURE = Path(__file__).parent / "data" / "rbh1_acs_f606w_f814w.fits"

pytestmark = pytest.mark.slow


@pytest.fixture
def swept(tmp_path: Path) -> Path:
    """Three tiles searched, results committed."""
    tiles = tmp_path / "tiles"
    tiles.mkdir()
    for i in range(3):
        shutil.copy(FIXTURE, tiles / f"tile_{i:03d}.fits")
    out = tmp_path / "out"
    run(local_sources(tiles), out, config_fingerprint="cfg")
    return out


def test_a_tile_region_is_exact_not_a_disc() -> None:
    """A tile is a rectangle on a known projection, so its corners are not an approximation."""
    tile = read_tile(FIXTURE)
    region = tile_region(tile.wcs, tile.shape)
    assert region.startswith("POLYGON ")

    moc = region_footprint(region)
    assert moc is not None
    height, width = tile.shape
    expected = (height * width) * (tile.pixel_scale_arcsec / 60.0) ** 2
    assert area_arcmin2(moc) == pytest.approx(expected, rel=0.05)


def test_a_rotated_tile_stays_a_rectangle() -> None:
    """Corners traced in order, not a bounding box, or a rotated tile inflates its own area."""
    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [200.0, 200.0]
    wcs.wcs.cdelt = [-0.05 / 3600, 0.05 / 3600]
    wcs.wcs.crval = [40.0, -8.0]
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crota = [45.0, 45.0]

    moc = region_footprint(tile_region(wcs, (400, 400)))
    assert moc is not None
    unrotated = 400 * 400 * (0.05 / 60.0) ** 2
    assert area_arcmin2(moc) == pytest.approx(unrotated, rel=0.1), (
        "a 45-degree rotation must not change the area; a bounding box would double it"
    )


def test_the_products_come_only_from_committed_results(swept: Path) -> None:
    products = survey_products(swept)
    assert products.n_tiles == 3
    assert products.unique_arcmin2 > 0.0
    assert products.median_depth_mag > 20.0


def test_identical_tiles_overlap_almost_completely(swept: Path) -> None:
    """Three copies of one field cover one field's worth of sky, not three."""
    products = survey_products(swept)
    summed = products.summed_arcmin2
    unique = products.unique_arcmin2
    assert unique < summed
    assert unique == pytest.approx(summed / 3, rel=0.1)
    assert products.overlap_fraction == pytest.approx(2 / 3, abs=0.1)


def test_effective_area_falls_with_faintness_and_never_exceeds_unique(swept: Path) -> None:
    """The gap between unique and effective area is the selection function, made visible."""
    products = survey_products(swept)
    unique = products.unique_arcmin2
    areas = [area for _, area in products.effective_area_arcmin2]
    assert areas == sorted(areas, reverse=True)
    assert all(area <= unique + 1e-9 for area in areas)
    assert areas[0] > areas[-1], "a bright wake must be constrained better than a faint one"


def test_a_tile_that_found_nothing_still_contributes_area(tmp_path: Path) -> None:
    """The half of the denominator a catalogue of survivors cannot supply.

    Empty sky is still searched sky. If it dropped out of the area, every density limit would
    be computed against only the sky that happened to contain something.
    """
    tile = read_tile(FIXTURE)
    commit(
        tmp_path,
        "empty-0000.json",
        {
            "tile_id": "empty",
            "n_detections": 0,
            "n_survivors": 0,
            "depth_mag": {"F606W": 27.5},
            "filters": ["F606W"],
            "s_region": tile_region(tile.wcs, tile.shape),
            "survivors": [],
        },
    )
    products = survey_products(tmp_path)
    assert products.n_candidates == 0
    assert products.unique_arcmin2 > 0.0


def test_candidates_carry_their_tile(swept: Path) -> None:
    """A candidate without provenance cannot be re-inspected, which Phase 5 requires."""
    products = survey_products(swept)
    for candidate in products.candidates:
        assert candidate["tile_id"]
        assert "ra_deg" in candidate


def test_products_are_identical_across_runs(tmp_path: Path) -> None:
    """Same searched sky, same published numbers - however the sweep was scheduled."""
    tiles = tmp_path / "tiles"
    tiles.mkdir()
    for i in range(3):
        shutil.copy(FIXTURE, tiles / f"tile_{i:03d}.fits")
    sources = local_sources(tiles)

    forwards, backwards = tmp_path / "fwd", tmp_path / "bwd"
    run(sources, forwards, config_fingerprint="cfg")
    run(list(reversed(sources)), backwards, config_fingerprint="cfg")
    assert survey_products(forwards) == survey_products(backwards)
