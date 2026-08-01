"""The measurement studies, on grids small enough to run in CI.

These exercise the plumbing and the arithmetic. The real grids are far larger and are run
deliberately with `rbh calibrate` / `rbh completeness`; their outputs live under
`docs/data/` so the published numbers stay traceable (ADR-0012).
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from rbh.studies import (
    CALIBRATION_TOLERANCES,
    InjectionSite,
    ReferenceTemplate,
    calibrate_generator,
    calibration_cost,
    collect_sites,
    completeness_grid,
    half_completeness_limit,
    real_object_exclusion,
    reference_template,
)

FIXTURE = Path(__file__).parent / "data" / "rbh1_acs_f606w_f814w.fits"

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def reference() -> ReferenceTemplate:
    return reference_template(FIXTURE)


@pytest.fixture(scope="module")
def sites() -> list[InjectionSite]:
    return collect_sites(FIXTURE, None, per_tile=3)


def test_reference_template_matches_the_published_photometry(
    reference: ReferenceTemplate,
) -> None:
    """The template covers the detected part of RBH-1, so it is a little fainter than the
    published total, and slightly bluer than the published integrated colour.
    """
    assert reference.blue_filter == "F606W"
    assert reference.red_filter == "F814W"
    assert 23.0 < reference.total_mag_ab < 24.5
    assert 0.4 < reference.colour_ab < 1.1
    assert reference.template.source_pixels > 500


def test_exclusion_mask_covers_the_real_object() -> None:
    mask = real_object_exclusion(FIXTURE)
    assert mask.any()
    assert not mask.all(), "the mask must not swallow the whole tile"


def test_sites_avoid_the_real_object(sites: list[InjectionSite]) -> None:
    mask = real_object_exclusion(FIXTURE)
    assert sites
    for site in sites:
        assert not mask[site.centre[0], site.centre[1]]


def test_calibration_cost_is_zero_at_a_perfect_match() -> None:
    target = dict.fromkeys(CALIBRATION_TOLERANCES, 1.0)
    assert calibration_cost(dict(target), target) == pytest.approx(0.0)


def test_calibration_cost_scales_with_the_tolerance() -> None:
    target = dict.fromkeys(CALIBRATION_TOLERANCES, 0.0)
    got = dict(CALIBRATION_TOLERANCES)
    # One tolerance of mismatch in each of three statistics.
    assert calibration_cost(got, target) == pytest.approx(len(CALIBRATION_TOLERANCES))


def test_calibration_returns_the_lowest_cost_configuration(
    sites: list[InjectionSite], reference: ReferenceTemplate
) -> None:
    result = calibrate_generator(
        sites,
        reference,
        tail_values=(0.02, 0.40),
        clumpiness_values=(0.0,),
        width_values=(0.10, 0.22),
        width_jitter_values=(0.45,),
    )
    assert len(result.scanned) == 4
    assert result.scanned == sorted(result.scanned, key=lambda row: row["cost"])
    assert result.best_cost == pytest.approx(result.scanned[0]["cost"])
    assert result.best.width_arcsec in (0.10, 0.22)
    assert set(result.to_dict()) >= {"target", "best_parameters", "scanned", "tolerances"}


def test_completeness_falls_with_faintness(
    sites: list[InjectionSite], reference: ReferenceTemplate
) -> None:
    rows = completeness_grid(sites, reference, magnitudes=(22.5, 26.5), clumpiness_values=(0.3,))
    for source in {str(r["source"]) for r in rows}:
        selected = sorted((r for r in rows if r["source"] == source), key=lambda r: float(r["mag"]))
        bright, faint = float(selected[0]["completeness"]), float(selected[-1]["completeness"])
        assert bright >= faint, f"{source} got more complete when fainter"


def test_completeness_grid_covers_transplant_and_each_clumpiness(
    sites: list[InjectionSite], reference: ReferenceTemplate
) -> None:
    rows = completeness_grid(sites, reference, magnitudes=(23.5,), clumpiness_values=(0.0, 0.9))
    sources = {str(r["source"]) for r in rows}
    assert sources == {"transplant", "parametric c=0.0", "parametric c=0.9"}


def test_half_limit_interpolates() -> None:
    assert half_completeness_limit([24.0, 25.0], [1.0, 0.0]) == pytest.approx(24.5)
    assert half_completeness_limit([24.0, 24.4], [0.75, 0.25]) == pytest.approx(24.2)


def test_half_limit_is_nan_when_the_curve_never_crosses() -> None:
    assert math.isnan(half_completeness_limit([24.0, 25.0], [1.0, 0.9]))
    assert math.isnan(half_completeness_limit([24.0, 25.0], [0.2, 0.1]))
