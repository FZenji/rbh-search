"""The manifest decides what the survey is, so its accounting has to be right.

Its area is the denominator of every density limit (ADR-0019) and its depth column is what
makes the selection function applicable off a single visit (ADR-0018). A quiet error here
would propagate into every published number without failing anything.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rbh.manifest import (
    MIN_GALACTIC_LATITUDE_DEG,
    Manifest,
    Product,
    filters_by_position,
    is_extragalactic,
    tier_of,
)


def product(
    uri: str = "s3://stpubdata/hst/a_drz.fits",
    *,
    etag: str = "etag-1",
    instrument: str = "ACS/WFC",
    filter_name: str = "F606W",
    ra: float = 40.0,
    dec: float = -8.0,
    latitude: float = -60.0,
    depth: float = 27.5,
    area: float = 11.0,
    exposure: float = 2400.0,
) -> Product:
    return Product(
        uri=uri,
        etag=etag,
        instrument=instrument,
        filter_name=filter_name,
        exposure_seconds=exposure,
        ra_deg=ra,
        dec_deg=dec,
        galactic_latitude_deg=latitude,
        point_source_limit_mag=depth,
        area_arcmin2=area,
    )


def test_the_galactic_plane_is_excluded() -> None:
    """ADR-0001: below this latitude the sky is crowded and manufactures linear artifacts."""
    assert is_extragalactic(product(latitude=MIN_GALACTIC_LATITUDE_DEG + 1))
    assert is_extragalactic(product(latitude=-(MIN_GALACTIC_LATITUDE_DEG + 1)))
    assert not is_extragalactic(product(latitude=MIN_GALACTIC_LATITUDE_DEG - 1))
    assert not is_extragalactic(product(latitude=0.0))


def test_build_filters_the_plane_out() -> None:
    manifest = Manifest.build(
        [product(uri="a.fits", latitude=-70.0), product(uri="b.fits", latitude=3.0)]
    )
    assert [p.uri for p in manifest.products] == ["a.fits"]


def test_build_deduplicates_by_uri() -> None:
    """An archive query can return the same product twice; counting it twice inflates area."""
    manifest = Manifest.build([product(uri="a.fits"), product(uri="a.fits"), product(uri="b.fits")])
    assert len(manifest) == 2
    assert manifest.raw_area_arcmin2() == pytest.approx(22.0)


def test_ordering_is_stable_regardless_of_input_order() -> None:
    """Determinism (ADR-0012): the archive's response order must not reach the output."""
    items = [
        product(uri="c.fits", filter_name="F814W"),
        product(uri="a.fits", instrument="WFC3/UVIS"),
        product(uri="b.fits"),
    ]
    forwards = Manifest.build(items)
    backwards = Manifest.build(list(reversed(items)))
    assert [p.uri for p in forwards.products] == [p.uri for p in backwards.products]


def test_two_filters_on_a_pointing_is_tier_a() -> None:
    """ADR-0006: the cross-filter check needs two filters, and the tier must be explicit."""
    assert tier_of(2) == "A"
    assert tier_of(3) == "A"
    assert tier_of(1) == "B"


def test_nearly_identical_coordinates_count_as_one_pointing() -> None:
    """Products of one field differ in the last decimals; splitting them would fake tier B.

    This is the failure that would matter: every genuinely two-filter field would be reported
    as two single-filter pointings, and the whole corpus would look like tier B.
    """
    grouped = filters_by_position(
        [
            product(uri="a.fits", filter_name="F606W", ra=40.00001, dec=-8.00002),
            product(uri="b.fits", filter_name="F814W", ra=40.00003, dec=-8.00001),
        ]
    )
    assert len(grouped) == 1
    assert next(iter(grouped.values())) == {"F606W", "F814W"}


def test_tiers_counts_pointings_not_products() -> None:
    manifest = Manifest.build(
        [
            product(uri="a.fits", filter_name="F606W", ra=10.0, dec=10.0),
            product(uri="b.fits", filter_name="F814W", ra=10.0, dec=10.0),
            product(uri="c.fits", filter_name="F606W", ra=50.0, dec=20.0),
        ]
    )
    assert manifest.tiers() == {"A": 1, "B": 1}


def test_raw_area_is_named_so_it_cannot_be_mistaken_for_survey_area() -> None:
    """Overlaps are counted repeatedly here; the real number needs a MOC union.

    Asserted rather than trusted to the docstring, because a summed area that happened to
    look plausible is exactly the kind of number that gets published by accident.
    """
    same_sky = [
        product(uri="a.fits", ra=10.0, dec=10.0, area=11.0),
        product(uri="b.fits", ra=10.0, dec=10.0, area=11.0),
    ]
    assert Manifest.build(same_sky).raw_area_arcmin2() == pytest.approx(22.0)


def test_depth_histogram_spans_the_corpus() -> None:
    manifest = Manifest.build(
        [
            product(uri="a.fits", depth=25.0),
            product(uri="b.fits", depth=26.5),
            product(uri="c.fits", depth=27.2),
            product(uri="d.fits", depth=29.0),
        ]
    )
    counts = manifest.depth_histogram([26.0, 27.0, 28.0])
    assert counts["<26.0"] == 1
    assert counts["26.0-27.0"] == 1
    assert counts["27.0-28.0"] == 1
    assert counts[">28.0"] == 1
    assert sum(counts.values()) == len(manifest)


def test_round_trips_through_json(tmp_path: Path) -> None:
    manifest = Manifest.build(
        [product(uri="a.fits"), product(uri="b.fits", filter_name="F814W", depth=26.9)]
    )
    path = manifest.to_json(tmp_path / "manifest.json")
    assert Manifest.from_json(path).products == manifest.products


def test_reading_a_manifest_does_not_re_apply_the_latitude_cut(tmp_path: Path) -> None:
    """A written manifest is already filtered; re-filtering on read would silently shrink it.

    The cut belongs at build time, where it is a decision. Applying it again on every read
    would mean a change to the threshold retroactively rewrote existing manifests.
    """
    manifest = Manifest.build([product(uri="a.fits", latitude=-70.0)], extragalactic_only=False)
    path = manifest.to_json(tmp_path / "m.json")
    assert len(Manifest.from_json(path)) == 1
