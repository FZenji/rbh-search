"""Manifest discovery: the row handling offline, the query itself behind the network mark.

MAST's query endpoint is the least reliable component in the pipeline, so everything that
can be tested without it is. What is left needing the network is one call.
"""

from __future__ import annotations

import pytest

from rbh.fetch import (
    CORPUS_COUNTS,
    DRIZZLED_CALIB_LEVEL,
    SURVEY_INSTRUMENTS,
    _number,
    _raw,
    _text,
)
from rbh.footprint import (
    account,
    area_arcmin2,
    circular_footprint,
    product_footprint,
    region_coverage,
    region_footprint,
)
from rbh.manifest import Product

#: A realistic CAOM s_region for an ACS/WFC pointing: a 3.4 arcmin square.
ACS_REGION = (
    "POLYGON 39.971667 -8.028333 40.028333 -8.028333 40.028333 -7.971667 39.971667 -7.971667"
)


class FakeRow:
    """Stands in for an astropy table row, including the ways real ones are broken."""

    def __init__(self, **values: object) -> None:
        self._values = values

    def __getitem__(self, key: str) -> object:
        if key not in self._values:
            raise KeyError(key)
        return self._values[key]


class Masked:
    """A masked table entry, which astropy yields for a missing value."""

    mask = True


def product(uri: str = "a.fits", *, region: str = "", area: float = 11.0) -> Product:
    return Product(
        uri=uri,
        etag="e",
        instrument="ACS/WFC",
        filter_name="F606W",
        exposure_seconds=2400.0,
        ra_deg=40.0,
        dec_deg=-8.0,
        galactic_latitude_deg=-60.0,
        point_source_limit_mag=27.5,
        area_arcmin2=area,
        s_region=region,
    )


def test_missing_columns_do_not_raise() -> None:
    """One bad row must not take out a manifest build over tens of thousands."""
    row = FakeRow(obs_id="x")
    assert _text(row, "absent") == ""
    assert _text(row, "absent", "fallback") == "fallback"
    assert _number(row, "absent") is None


def test_masked_values_read_as_absent() -> None:
    """Archive metadata has gaps in every column, and astropy marks them rather than omits."""
    row = FakeRow(s_ra=Masked(), obs_id="x")
    assert _raw(row, "s_ra") is None
    assert _number(row, "s_ra") is None


def test_unparseable_numbers_read_as_absent_not_zero() -> None:
    """Zero is a coordinate. Returning it for an unparseable value would place a product."""
    assert _number(FakeRow(s_ra="not a number"), "s_ra") is None


def test_the_scope_matches_the_adr() -> None:
    """ADR-0001 fixes the instruments; ADR-0003 fixes the calibration level."""
    assert set(SURVEY_INSTRUMENTS) == {"ACS/WFC", "WFC3/UVIS", "WFC3/IR", "NIRCAM/IMAGE"}
    assert DRIZZLED_CALIB_LEVEL == 3


def test_every_instrument_has_a_recorded_corpus_count() -> None:
    """A name with no recorded count is one nobody has checked returns anything."""
    assert set(CORPUS_COUNTS) == set(SURVEY_INSTRUMENTS)
    assert all(count > 0 for count in CORPUS_COUNTS.values())


@pytest.mark.network
def test_no_instrument_name_silently_returns_nothing() -> None:
    """The guard for the bug that made this test exist.

    ``NIRCAM`` is a plausible spelling that CAOM does not use, and it returns zero products
    rather than an error - so JWST would have been dropped from the survey with nothing to
    show for it. A wrong instrument name is indistinguishable from an instrument with no
    data unless something asserts the difference.
    """
    from rbh.fetch import count_products  # noqa: PLC0415

    counts = count_products()
    for instrument, count in counts.items():
        assert count > 0, f"{instrument} returned no products - is the CAOM name right?"
        recorded = CORPUS_COUNTS[instrument]
        assert 0.5 * recorded < count < 2.0 * recorded, (
            f"{instrument} returned {count:,} against a recorded {recorded:,}; "
            "an order-of-magnitude change is a query problem, not archive growth"
        )


def test_a_real_region_is_preferred_over_a_disc() -> None:
    """The archive's own polygon beats a disc of equal area, which is wrong at the edges."""
    moc = region_footprint(ACS_REGION)
    assert moc is not None
    assert area_arcmin2(moc) == pytest.approx(11.4, rel=0.1)


def test_a_missing_or_broken_region_falls_back_to_a_disc() -> None:
    """Degrade rather than fail: thirty years of metadata contains malformed regions."""
    assert region_footprint("") is None
    assert region_footprint("   ") is None
    assert region_footprint("CIRCLE-ish nonsense 1 2 3") is None

    fallback = product_footprint(product(region="not a polygon"))
    disc = circular_footprint(40.0, -8.0, 11.0)
    assert area_arcmin2(fallback) == pytest.approx(area_arcmin2(disc), rel=1e-6)


def test_region_coverage_reports_how_much_is_guesswork() -> None:
    """An overlap number computed over discs is indicative, and must be labelled as such."""
    products = [
        product("a.fits", region=ACS_REGION),
        product("b.fits", region=ACS_REGION),
        product("c.fits", region=""),
        product("d.fits", region="broken"),
    ]
    assert region_coverage(products) == pytest.approx(0.5)
    assert region_coverage([]) == pytest.approx(1.0)


def test_real_regions_flow_through_the_area_accounting() -> None:
    """The footprint used for area must be the polygon, not silently the disc."""
    with_region = account([product("a.fits", region=ACS_REGION, area=99.0)])
    as_disc = account([product("a.fits", area=99.0)])
    assert with_region.unique_arcmin2 == pytest.approx(11.4, rel=0.1)
    assert as_disc.unique_arcmin2 == pytest.approx(99.0, rel=0.1)


@pytest.mark.network
def test_discovery_returns_usable_rows() -> None:
    """One call, behind the mark, because this endpoint times out regularly."""
    from rbh.fetch import discover_products  # noqa: PLC0415 - keeps astroquery off the offline path

    rows = discover_products(instruments=("ACS/WFC",), limit=5)
    assert rows, "the archive returned nothing for ACS/WFC"
    for row in rows:
        assert abs(float(row["galactic_latitude_deg"])) > 20.0  # type: ignore[arg-type]
        assert row["obs_id"]
    assert [r["obs_id"] for r in rows] == sorted(str(r["obs_id"]) for r in rows)
