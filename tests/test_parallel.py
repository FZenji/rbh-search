"""Running trials across processes must change the speed and nothing else.

The claim that makes :mod:`rbh.parallel` safe is that every trial draws from its own
generator, seeded as ``seed + index``, so no trial can observe another and the order they
run in cannot matter. That is a claim about the science, not about the plumbing, so it is
tested against the real study function rather than against a toy one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rbh.config import SelectionWindow
from rbh.parallel import MIN_ITEMS_FOR_POOL, default_workers, map_trials
from rbh.studies import _run_parametric, collect_sites
from rbh.synthetic import WakeParameters

FIXTURE = Path(__file__).parent / "data" / "rbh1_acs_f606w_f814w.fits"


def _double(value: int) -> int:
    """A module-level function, because a pool cannot pickle a closure."""
    return value * 2


def test_default_workers_leaves_headroom() -> None:
    assert default_workers() >= 1


def test_small_batches_stay_inline() -> None:
    """Below the threshold no pool is started, whatever the caller asks for."""
    items = list(range(MIN_ITEMS_FOR_POOL - 1))
    assert map_trials(_double, items, workers=4) == [2 * i for i in items]


def test_order_is_preserved() -> None:
    """Results come back in submission order, not completion order."""
    items = list(range(MIN_ITEMS_FOR_POOL * 3))
    assert map_trials(_double, items, workers=2) == [2 * i for i in items]


@pytest.mark.slow
def test_parallel_trials_are_bit_identical_to_serial() -> None:
    """The whole justification for the parallel path, asserted rather than assumed.

    Two workers rather than many: the point is to cross the process boundary at all, and
    a wider pool only adds spawn time. The site count must clear
    :data:`~rbh.parallel.MIN_ITEMS_FOR_POOL` or the parallel run would quietly fall back
    to the inline path and the test would compare serial against serial.
    """
    sites = collect_sites(FIXTURE, None, per_tile=MIN_ITEMS_FOR_POOL + 2)
    assert len(sites) >= MIN_ITEMS_FOR_POOL

    params = WakeParameters(total_mag_ab=24.0)
    window = SelectionWindow()

    def run(workers: int) -> dict[str, float]:
        return _run_parametric(
            sites, params, psf_fwhm_arcsec=0.11, window=window, seed=4242, workers=workers
        )

    assert run(1) == run(2)
