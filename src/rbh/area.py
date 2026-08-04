"""Effective survey area: sky area weighted by how likely we were to find a wake in it.

ADR-0019. A null result becomes a space-density limit by dividing by how much sky was
searched, but a one-orbit tile and a twenty-orbit tile are not equally searched. ADR-0018
measured the difference: the wake 50% completeness limit sits about 3 magnitudes brighter
than a tile's own 5-sigma point-source limit, so a sixteen-fold spread in exposure moves it
by 1.3 magnitudes.

The denominator is therefore

    A_eff(m) = sum over sky of  area * C(m | depth of that sky)

with raw unique area published alongside, unchanged, so the weighting is auditable rather
than buried.

**Everything here inherits ADR-0018's one-sidedness.** The completeness model is an upper
bound - degrading real tiles simulates photon noise and none of the other things that make
shallow archival data harder - so effective area is an upper bound and any density limit
derived from it is a lower bound on how constraining the search can claim to be.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from rbh.reference import WAKE_LIMIT_BELOW_POINT_SOURCE_MAG

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

#: Width of the completeness roll-off in magnitudes: a logistic whose 50% point is the
#: measured limit falls from 73% to 27% over this many magnitudes.
#:
#: **Fitted to the 25 points of the ADR-0018 depth grid, not chosen.** It was first set to
#: 0.55 by eye, which is the failure this project has now made three times - the terminal
#: knot, ``width_jitter``, and the monotonic brightness ramp - so it was fitted before being
#: used. The fit gives 0.212 with a mean absolute residual of 0.027 against 0.113 for the
#: guess, a fourfold improvement.
#:
#: It is load-bearing, which is why guessing it would have mattered: across the plausible
#: range 0.35 to 0.75 the effective-area fraction of a mixed-depth survey moves from 0.298
#: to 0.361 at magnitude 24.5, a 26% swing in the denominator of every density limit.
#:
#: A *shape* fitted to one depth ladder, not a law. Used to interpolate between measured
#: magnitudes; anything quoted far outside the measured 23.0-25.6 range is extrapolating and
#: should say so.
COMPLETENESS_ROLLOFF_MAG = 0.212


@dataclass(frozen=True)
class SkyPatch:
    """A piece of sky with a single depth, and its area.

    In practice a MOC cell or a group of them. Kept deliberately free of geometry: the
    overlap resolution that decides *which* depth applies to a patch happens before this,
    and this module only does the weighting.
    """

    area_arcmin2: float
    point_source_limit_mag: float

    def wake_limit_mag(self) -> float:
        """Return the 50% completeness magnitude for a wake here (the ADR-0018 relation)."""
        return self.point_source_limit_mag - WAKE_LIMIT_BELOW_POINT_SOURCE_MAG


def completeness_at(magnitude: float, wake_limit_mag: float) -> float:
    """Fraction of wakes of this magnitude that would pass the selection window.

    A logistic in magnitude centred on the 50% limit. Real completeness curves are not
    logistic in detail - this one is measured at five points - but the shape matters far less
    than the centre, which is what ADR-0018 pins.
    """
    return 1.0 / (1.0 + math.exp((magnitude - wake_limit_mag) / COMPLETENESS_ROLLOFF_MAG))


def effective_area_arcmin2(patches: Iterable[SkyPatch], magnitude: float) -> float:
    """Sky area weighted by completeness at this source magnitude (ADR-0019)."""
    return sum(p.area_arcmin2 * completeness_at(magnitude, p.wake_limit_mag()) for p in patches)


def raw_area_arcmin2(patches: Iterable[SkyPatch]) -> float:
    """Unweighted unique sky area, published alongside the effective area."""
    return sum(p.area_arcmin2 for p in patches)


def deepest_per_sky(patches: Iterable[SkyPatch]) -> list[SkyPatch]:
    """Collapse repeated coverage of the same sky to its deepest observation.

    Only meaningful once patches have been keyed to disjoint sky; the caller is responsible
    for that. Shallower duplicates add no area, and averaging them in would only lower the
    completeness of sky we have in fact searched more deeply.

    **This is about area accounting, not about what gets searched.** Repeat visits stay in
    the manifest: they are the only way to run the cross-visit artifact control, where a real
    feature appears in both epochs and a detector artifact does not.
    """
    return sorted(patches, key=lambda p: p.point_source_limit_mag, reverse=True)


def area_curve(
    patches: Sequence[SkyPatch], magnitudes: Sequence[float]
) -> list[tuple[float, float]]:
    """Effective area against source magnitude - the survey's denominator, as a curve.

    A curve rather than a number because it has to be: the search constrains bright wakes
    better than faint ones, and collapsing that to a single figure hides which.
    """
    return [(m, effective_area_arcmin2(patches, m)) for m in magnitudes]
