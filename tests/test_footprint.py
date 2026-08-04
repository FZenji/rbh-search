"""Unique sky area is the denominator of every density limit, so overlaps must not be summed.

The failure this guards against is the quiet one: a corpus that overlaps itself heavily
reporting its summed area as its coverage, inflating the denominator and understating every
limit derived from it.
"""

from __future__ import annotations

import pytest

from rbh.footprint import (
    ARCMIN2_PER_DEG2,
    QUANTISATION_BIAS,
    account,
    area_arcmin2,
    circular_footprint,
    deepest_patches,
    effective_area_curve,
    survey_footprint,
    union,
)
from rbh.manifest import Product


def product(
    uri: str,
    *,
    ra: float = 40.0,
    dec: float = -8.0,
    area: float = 11.0,
    depth: float = 27.5,
) -> Product:
    return Product(
        uri=uri,
        etag="e",
        instrument="ACS/WFC",
        filter_name="F606W",
        exposure_seconds=2400.0,
        ra_deg=ra,
        dec_deg=dec,
        galactic_latitude_deg=-60.0,
        point_source_limit_mag=depth,
        area_arcmin2=area,
    )


def test_a_footprint_has_roughly_the_area_asked_for() -> None:
    """The disc approximation must at least conserve area, or every total is wrong."""
    moc = circular_footprint(40.0, -8.0, 11.0)
    assert area_arcmin2(moc) == pytest.approx(11.0, rel=0.05)


def test_the_quantisation_bias_stays_within_what_is_documented() -> None:
    """A MOC over-covers a shape's boundary, and the survey area is a denominator.

    The first version of this module used order 14 on the reasoning that 13 arcsec cells are
    much finer than an 11 arcmin^2 product. That is true and it over-counts by 14%. The order
    is now chosen by measurement, and this test fails if anyone lowers it back for speed.
    """
    for area in (5.0, 11.0, 40.0):
        got = area_arcmin2(circular_footprint(40.0, -8.0, area))
        excess = got / area - 1.0
        assert excess >= -1e-6, "quantisation can only ever over-cover, never under-cover"
        assert excess <= 2 * QUANTISATION_BIAS, (
            f"a {area} arcmin^2 footprint over-counts by {100 * excess:.1f}%, "
            f"above the documented {100 * QUANTISATION_BIAS:.0f}%"
        )


@pytest.mark.parametrize(("order", "worst"), [(14, 0.20), (18, 0.02)])
def test_finer_orders_are_measurably_better(order: int, worst: float) -> None:
    """Records the trade-off in an executable form, so the constant is not folklore."""
    got = area_arcmin2(circular_footprint(40.0, -8.0, 11.0, order=order))
    assert 0.0 <= got / 11.0 - 1.0 <= worst


def test_identical_pointings_count_once() -> None:
    """The whole reason a MOC is used instead of a sum."""
    same = [product("a"), product("b"), product("c")]
    accounting = account(same)
    assert accounting.summed_arcmin2 == pytest.approx(33.0)
    assert accounting.unique_arcmin2 == pytest.approx(11.0, rel=0.05)
    assert accounting.overlap_fraction == pytest.approx(2 / 3, abs=0.05)


def test_disjoint_pointings_add_up() -> None:
    far_apart = [product("a", ra=40.0, dec=-8.0), product("b", ra=120.0, dec=35.0)]
    accounting = account(far_apart)
    assert accounting.unique_arcmin2 == pytest.approx(22.0, rel=0.05)
    assert accounting.overlap_fraction == pytest.approx(0.0, abs=0.02)


def test_unique_area_never_exceeds_the_sum() -> None:
    products = [product("a"), product("b", ra=40.02), product("c", ra=200.0, dec=10.0)]
    accounting = account(products)
    assert accounting.unique_arcmin2 <= accounting.summed_arcmin2 + 1e-6


def test_area_converts_to_square_degrees() -> None:
    accounting = account([product("a", area=ARCMIN2_PER_DEG2)])
    assert accounting.unique_deg2 == pytest.approx(1.0, rel=0.05)


def test_union_of_nothing_is_empty_not_an_error() -> None:
    assert area_arcmin2(union([])) == pytest.approx(0.0)
    assert area_arcmin2(survey_footprint([])) == pytest.approx(0.0)


def test_the_deepest_product_claims_shared_sky() -> None:
    """ADR-0019: overlapping sky is credited to the deepest coverage, once."""
    patches = deepest_patches([product("shallow", depth=26.0), product("deep", depth=28.0)])
    assert len(patches) == 1
    assert patches[0].point_source_limit_mag == pytest.approx(28.0)
    assert patches[0].area_arcmin2 == pytest.approx(11.0, rel=0.05)


def test_a_shallow_product_keeps_the_part_that_sticks_out() -> None:
    """Partial overlap must not discard the shallow product whole, nor dilute the deep sky.

    This is why the resolution is cell by cell rather than product by product.
    """
    patches = deepest_patches(
        [product("deep", ra=40.0, depth=28.0), product("shallow", ra=40.03, depth=26.0)]
    )
    depths = sorted(p.point_source_limit_mag for p in patches)
    assert depths == [26.0, 28.0], "both products contribute some sky"
    total = sum(p.area_arcmin2 for p in patches)
    assert total < 22.0, "the shared sky is counted once"
    assert total > 11.0, "but the shallow product's own sky is not thrown away"


def test_patches_are_disjoint_so_effective_area_is_meaningful() -> None:
    products = [product(f"p{i}", ra=40.0 + 0.02 * i, depth=27.0 + 0.1 * i) for i in range(4)]
    patches = deepest_patches(products)
    unique = account(products).unique_arcmin2
    assert sum(p.area_arcmin2 for p in patches) == pytest.approx(unique, rel=0.02)


def test_the_effective_area_curve_falls_with_faintness() -> None:
    products = [product("deep", depth=28.0), product("shallow", ra=41.0, depth=26.0)]
    curve = effective_area_curve(products, [23.0, 24.0, 25.0, 26.0])
    areas = [area for _, area in curve]
    assert areas == sorted(areas, reverse=True)
    assert areas[0] > areas[-1]


def test_effective_area_is_below_unique_area() -> None:
    """The denominator shrinks once completeness is accounted for; that is the point."""
    products = [product("deep", depth=27.5), product("shallow", ra=41.0, depth=26.0)]
    unique = account(products).unique_arcmin2
    for _, effective in effective_area_curve(products, [24.0, 25.0]):
        assert effective < unique


def test_ordering_of_products_does_not_change_the_accounting() -> None:
    """Determinism (ADR-0012): the manifest's order must not reach the published area."""
    products = [product("a", depth=27.0), product("b", ra=40.02, depth=27.0), product("c", ra=41.0)]
    forwards = account(products).unique_arcmin2
    backwards = account(list(reversed(products))).unique_arcmin2
    assert forwards == pytest.approx(backwards, rel=1e-9)
