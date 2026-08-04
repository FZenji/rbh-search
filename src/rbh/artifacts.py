"""Reject the linear artifacts around bright sources, which the first real scan showed dominate.

`CLAUDE.md` used to assert that artifacts were largely handled by searching drizzled,
cosmic-ray-rejected products. The first scan of sky outside RBH-1's own field disproved it:
**76 of 84 candidates came from one bright elliptical galaxy** — diffraction spikes and
saturation bleeds, which appear in every exposure and so combine straight through drizzling
into the search plane, as perfectly linear high-contrast features. See the ADR-0003 amendment.

Three signatures separate them from a wake, and none of them had to be guessed — the first
scan measured all three:

* **They point where the optics say, not where the sky does.** Diffraction spikes and bleeds
  follow the detector axes, so their position angles pile up: 18 of 76 candidates in a single
  15 degree bin, against 6.3 if they scattered.
* **They radiate from a saturated source.** A wake has a host galaxy at one end; a spike has a
  saturated core at one end and is one of several sharing it.
* **They are too good.** The best-scoring feature in that field measured 39.0 arcsec at axis
  ratio 109 and peak signal-to-noise 202. RBH-1 measures 5.5 arcsec, axis ratio 21, and is
  the brightest such object known.

Scored, not cut ([ADR-0008](../../docs/adr/0008-scored-discriminants-not-cuts.md)). Each
signature returns a number, and a hard rejection is only applied where a value is outside
anything the real object could produce.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

#: Axis ratio above which a feature is more elongated than RBH-1 by a wide margin. RBH-1
#: measures 21 recovered; published intrinsic estimates reach 50. Above this a feature is
#: not a wake shaped like the one wake we know about.
IMPLAUSIBLE_AXIS_RATIO = 60.0

#: Length beyond which a feature exceeds ADR-0007's selection window anyway. Kept here so the
#: artifact score can say *why* something was rejected rather than only that it was.
IMPLAUSIBLE_LENGTH_ARCSEC = 25.0

#: Peak signal-to-noise above which a feature is far brighter than the brightest wake known.
#: RBH-1 is a high-S/N detection in a one-orbit image and does not approach this.
IMPLAUSIBLE_PEAK_SNR = 100.0

#: Half-width, in degrees, of the position-angle bin used to detect alignment. Chosen to
#: match the 15 degree binning that showed the pile-up in the first scan.
ALIGNMENT_TOLERANCE_DEG = 7.5

#: How many features must share a position angle before that angle is treated as an
#: instrumental direction rather than a coincidence. Two features can align by chance; a
#: detector axis collects many.
ALIGNMENT_MIN_COUNT = 4


@dataclass(frozen=True)
class ArtifactScore:
    """Why a candidate looks instrumental, component by component.

    Kept as separate numbers rather than one verdict so a vetting queue can show *which*
    signature fired, and so a wrong rejection is diagnosable rather than mysterious.
    """

    aligned_with_others: bool
    implausible_shape: bool
    implausible_brightness: bool
    shared_angle_count: int

    @property
    def is_artifact(self) -> bool:
        """Whether to reject outright.

        Alignment alone is not enough - a real wake can happen to lie along a detector axis,
        and rejecting on that would carve an unmeasurable hole in the selection function.
        Rejection requires either a shape or brightness no wake produces, or alignment
        *together with* one of them.
        """
        return self.implausible_shape or self.implausible_brightness

    @property
    def suspicion(self) -> int:
        """Count of signatures that fired, for ranking rather than cutting."""
        return sum((self.aligned_with_others, self.implausible_shape, self.implausible_brightness))


def _angle_difference_deg(a: float, b: float) -> float:
    """Separation between two position angles, on a 180 degree circle.

    Position angle is an *orientation*, not a direction: 179 degrees and 1 degree describe
    nearly the same line, and treating them as 178 apart would miss exactly the alignment
    this module exists to detect.
    """
    difference = abs(a - b) % 180.0
    return min(difference, 180.0 - difference)


def count_sharing_angle(
    position_angle_deg: float,
    others: Sequence[float],
    tolerance_deg: float = ALIGNMENT_TOLERANCE_DEG,
) -> int:
    """How many other features in the same field share this orientation."""
    return sum(
        1 for other in others if _angle_difference_deg(position_angle_deg, other) <= tolerance_deg
    )


def score(
    candidate: Mapping[str, object],
    field_angles: Sequence[float],
    *,
    alignment_min_count: int = ALIGNMENT_MIN_COUNT,
) -> ArtifactScore:
    """Score one candidate against the artifact signatures.

    ``field_angles`` are the position angles of every candidate in the same product,
    including this one - the alignment test is about the population, and a spike is only
    recognisable as one because it has siblings.
    """
    angle = float(candidate.get("position_angle_deg", 0.0))  # type: ignore[arg-type]
    ratio = float(candidate.get("axis_ratio", 0.0))  # type: ignore[arg-type]
    length = float(candidate.get("length_arcsec", 0.0))  # type: ignore[arg-type]
    snr = float(candidate.get("peak_snr", 0.0))  # type: ignore[arg-type]

    shared = count_sharing_angle(angle, field_angles)
    return ArtifactScore(
        aligned_with_others=shared >= alignment_min_count,
        implausible_shape=ratio > IMPLAUSIBLE_AXIS_RATIO or length > IMPLAUSIBLE_LENGTH_ARCSEC,
        implausible_brightness=snr > IMPLAUSIBLE_PEAK_SNR,
        shared_angle_count=shared,
    )


def dominant_angle(
    angles: Sequence[float], tolerance_deg: float = ALIGNMENT_TOLERANCE_DEG
) -> tuple[float, int] | None:
    """Return the orientation most features share, and how many, if one stands out.

    Returns None when no orientation is more popular than :data:`ALIGNMENT_MIN_COUNT`, which
    is the normal case for a field with no bright source in it.
    """
    if not angles:
        return None
    counts = [(angle, count_sharing_angle(angle, angles, tolerance_deg)) for angle in angles]
    best_angle, best_count = max(counts, key=lambda pair: pair[1])
    return (best_angle, best_count) if best_count >= ALIGNMENT_MIN_COUNT else None


def concentration(positions: Sequence[tuple[float, float]]) -> float:
    """Median nearest-neighbour separation in arcseconds, or NaN for fewer than two.

    A scatter of real wakes across a product is separated by arcminutes. The first scan's
    76 artifacts had a median nearest neighbour of 3.08 arcsec, which is the single clearest
    signal that a candidate list has piled onto one object.
    """
    if len(positions) < 2:
        return float("nan")
    coords = np.radians(np.asarray(positions, dtype=np.float64))
    ra, dec = coords[:, 0], coords[:, 1]
    cos_sep = np.clip(
        np.sin(dec)[:, None] * np.sin(dec)[None, :]
        + np.cos(dec)[:, None] * np.cos(dec)[None, :] * np.cos(ra[:, None] - ra[None, :]),
        -1.0,
        1.0,
    )
    separations = np.degrees(np.arccos(cos_sep)) * 3600.0
    np.fill_diagonal(separations, np.inf)
    return float(np.median(separations.min(axis=1)))


def filter_field(
    candidates: Sequence[Mapping[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Split one product's candidates into those kept and those rejected as instrumental.

    Returns ``(kept, rejected)``. Rejected entries carry a ``reject_reason`` so the vetting
    queue can explain itself and so ADR-0014's retention tier 1 - every raw detection with its
    rejection reason - can be reconstructed.
    """
    angles = [float(c.get("position_angle_deg", 0.0)) for c in candidates]  # type: ignore[arg-type]
    kept: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []

    for candidate in candidates:
        verdict = score(candidate, angles)
        if not verdict.is_artifact:
            kept.append({**candidate, "artifact_suspicion": verdict.suspicion})
            continue
        reasons = []
        if verdict.implausible_shape:
            reasons.append("shape beyond any known wake")
        if verdict.implausible_brightness:
            reasons.append("brighter than any known wake")
        if verdict.aligned_with_others:
            reasons.append(f"shares its angle with {verdict.shared_angle_count} others")
        rejected.append({**candidate, "reject_reason": "; ".join(reasons)})

    return kept, rejected


def field_is_contaminated(candidates: Sequence[Mapping[str, object]]) -> bool:
    """Whether a product's candidate list looks like one bright source rather than sky.

    A flag on the *field*, not on individual candidates. When it fires, the right response is
    to look at the image rather than to trust any of the entries - which is exactly what
    turned 76 candidates into one galaxy.
    """
    if len(candidates) < ALIGNMENT_MIN_COUNT:
        return False
    positions = [
        (float(c["ra_deg"]), float(c["dec_deg"]))  # type: ignore[arg-type]
        for c in candidates
    ]
    tight = concentration(positions)
    angles = [float(c.get("position_angle_deg", 0.0)) for c in candidates]  # type: ignore[arg-type]
    return (not math.isnan(tight) and tight < 10.0) or dominant_angle(angles) is not None
