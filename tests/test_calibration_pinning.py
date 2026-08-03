"""A fit that lands on the edge of its search grid must announce itself.

An edge fit is indistinguishable from a good one in every number the calibration
reports: the statistics can sit well inside tolerance while the parameter strains
against a bound that was picked by guesswork. The first recalibration after the blind
test did exactly that, and it was caught by eye rather than by the code, which is the
kind of luck that should not be relied on twice.
"""

from __future__ import annotations

from collections.abc import Sequence

from rbh.studies import _pinned_parameters
from rbh.synthetic import WakeParameters

# Annotated rather than inferred: a bare literal infers dict[str, tuple[float, ...]], and
# dict is invariant in its value type, so it does not satisfy dict[str, Sequence[float]].
GRIDS: dict[str, Sequence[float]] = {
    "tail_brightness": (0.02, 0.10, 0.22, 0.40),
    "clumpiness": (0.0, 0.2, 0.4, 0.6),
    "width_arcsec": (0.10, 0.16, 0.22, 0.28),
}


def test_interior_fit_is_not_pinned() -> None:
    best = WakeParameters(tail_brightness=0.10, clumpiness=0.2, width_arcsec=0.16)
    assert _pinned_parameters(best, GRIDS) == ()


def test_upper_edge_is_reported() -> None:
    best = WakeParameters(tail_brightness=0.10, clumpiness=0.2, width_arcsec=0.28)
    assert _pinned_parameters(best, GRIDS) == ("width_arcsec",)


def test_lower_edge_is_reported_when_the_bound_was_a_choice() -> None:
    """A fit at the bottom of an arbitrary range is as suspect as one at the top."""
    best = WakeParameters(tail_brightness=0.02, clumpiness=0.2, width_arcsec=0.16)
    assert _pinned_parameters(best, GRIDS) == ("tail_brightness",)


def test_a_physical_floor_does_not_count_as_pinned() -> None:
    """Zero clumpiness is a smooth feature, not a truncated search.

    The grid starts at zero because nothing below it exists, so the range cannot be
    widened downwards and there is nothing for the reader to act on. Flagging it anyway
    was the first behaviour of this check, and it fired on the very first real fit --
    which is how a warning gets learned as noise.
    """
    best = WakeParameters(tail_brightness=0.10, clumpiness=0.0, width_arcsec=0.16)
    assert _pinned_parameters(best, GRIDS) == ()


def test_a_physical_floor_still_pins_at_the_top() -> None:
    """Exempting the floor must not exempt the ceiling of the same parameter."""
    best = WakeParameters(tail_brightness=0.10, clumpiness=0.6, width_arcsec=0.16)
    assert _pinned_parameters(best, GRIDS) == ("clumpiness",)


def test_single_valued_grid_cannot_pin() -> None:
    """A parameter held fixed is not being fitted, so it is not a warning."""
    best = WakeParameters(tail_brightness=0.10, clumpiness=0.4, width_arcsec=0.22)
    assert _pinned_parameters(best, {"clumpiness": (0.4,)}) == ()
