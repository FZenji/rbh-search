"""Target selection must not quietly search the same field over and over, or RBH-1's own.

Both failures look like progress: the products-searched count rises while the unique area
does not, or the pipeline "finds a wake" that is the one it was calibrated on.
"""

from __future__ import annotations

import pytest

from rbh.reference import RBH1
from rbh.scan import ScanTarget, separation_deg, spread_over_sky


def test_separation_is_symmetric_and_zero_for_a_point() -> None:
    a, b = (40.0, -8.0), (120.0, 35.0)
    assert separation_deg(a, a) == pytest.approx(0.0, abs=1e-9)
    assert separation_deg(a, b) == pytest.approx(separation_deg(b, a))


def test_separation_handles_the_ra_wrap() -> None:
    """359 degrees and 1 degree are two degrees apart, not 358."""
    assert separation_deg((359.0, 0.0), (1.0, 0.0)) == pytest.approx(2.0, abs=1e-6)


def test_targets_are_spread_rather_than_clustered() -> None:
    """The archive is ordered by observation id, which clusters by proposal and so by field.

    Taking the first N would search one field many times and barely move the unique area.
    """
    clustered = [(f"a{i}", 40.0 + 0.001 * i, -8.0) for i in range(20)]
    far = [("b", 120.0, 30.0), ("c", 200.0, -40.0)]
    chosen = spread_over_sky([*clustered, *far], count=5, min_separation_deg=1.0)
    assert len(chosen) == 3, "one from the cluster, plus the two distant fields"
    names = [name for name, _, _ in chosen]
    assert "b" in names
    assert "c" in names


def test_the_rbh1_field_is_excluded() -> None:
    """Finding the object we calibrated on is not a discovery (ADR-0015).

    Counting it as one would be the most embarrassing possible version of this project's
    central mistake, so the exclusion is asserted rather than left to whoever writes the
    call.
    """
    targets = [("rbh1", RBH1.ra_deg, RBH1.dec_deg), ("elsewhere", 200.0, 40.0)]
    chosen = spread_over_sky(targets, count=5, avoid=[(RBH1.ra_deg, RBH1.dec_deg)])
    assert [name for name, _, _ in chosen] == ["elsewhere"]


def test_selection_is_deterministic() -> None:
    """ADR-0012: the same manifest must always give the same targets."""
    candidates = [(f"t{i}", 10.0 * i, 5.0 * (i % 7)) for i in range(30)]
    assert spread_over_sky(candidates, 6) == spread_over_sky(candidates, 6)


def test_asking_for_more_than_exist_returns_what_there_is() -> None:
    assert len(spread_over_sky([("a", 10.0, 10.0)], count=9)) == 1


def test_tier_follows_the_filter_count() -> None:
    """ADR-0006: two filters allow the cross-filter check, one does not."""
    two = ScanTarget("x", 10.0, 10.0, ("a_drc.fits", "b_drc.fits"))
    one = ScanTarget("y", 10.0, 10.0, ("a_drc.fits",))
    assert two.tier == "A"
    assert one.tier == "B"
