"""Build a blind test asking whether a person can tell a synthetic wake from a real one.

ADR-0017 asks for this directly, and it is the check no summary statistic replaces. The
generator is calibrated to reproduce the transplant's *recovery statistics* - length, width,
fragmentation rate - but reproducing four numbers is not the same as looking right. A person
comparing stamps uses everything at once, including whatever we forgot to measure.

The test is constructed so the only difference between the two classes is the source itself:

* both are injected into the **same real archival tiles**, at the same brightness, drawn from
  the same distribution of positions and orientations;
* both stamps are cut the same way and displayed on a **shared stretch**, because per-stamp
  scaling would leak class information through contrast alone - a mistake already made once
  in this project, when per-panel zscale made a clean field look striped;
* the answer key is separate from the stamps, so it cannot be read by accident.

Interpretation is the opposite of most tests: **near 50% accuracy is the good outcome**. It
means the synthetics are indistinguishable, and the completeness measured with them is
trustworthy. High accuracy means the generator is missing something a human can see.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from rbh.inject import free_positions, inject_synthetic, inject_template
from rbh.synthetic import WakeParameters
from rbh.template import transform_template

if TYPE_CHECKING:
    from collections.abc import Sequence

    from numpy.random import Generator
    from numpy.typing import NDArray

    from rbh.studies import ReferenceTemplate
    from rbh.tile import Tile

#: Class labels. "transplant" is real RBH-1 pixels; "parametric" is generated.
TRANSPLANT = "transplant"
PARAMETRIC = "parametric"


@dataclass(frozen=True)
class BlindStamp:
    """One stamp for the blind test, with its hidden truth."""

    index: int
    kind: str
    tile_name: str
    magnitude: float
    pixels: NDArray[np.float32]

    @property
    def is_real(self) -> bool:
        """Whether these are real transplanted pixels rather than generated ones."""
        return self.kind == TRANSPLANT


def make_blind_set(
    tiles: Sequence[tuple[str, Tile]],
    reference: ReferenceTemplate,
    *,
    rng: Generator,
    count: int = 20,
    stamp_half_size: int = 90,
    magnitudes: Sequence[float] = (23.4, 23.8, 24.2),
    psf_fwhm_arcsec: float = 0.11,
    params: WakeParameters | None = None,
) -> list[BlindStamp]:
    """Generate an interleaved set of transplanted and generated wakes.

    Stamps are emitted in **pairs**: one transplant and one generated wake at the same
    magnitude, from the same tile. That pairing is the point. An earlier version cycled the
    class on ``index % 2`` and the magnitude on ``index % len(magnitudes)``, which for two
    magnitudes put every transplant at one brightness and every synthetic at the other - the
    test could then be won by noticing one class was systematically fainter, without looking
    at a single wake. Class and magnitude must vary independently, and the cheapest way to
    guarantee that is to hold magnitude fixed within a pair.
    """
    params = params or WakeParameters()
    stamps: list[BlindStamp] = []

    for index in range(count):
        pair = index // 2
        name, tile = tiles[pair % len(tiles)]
        magnitude = magnitudes[pair % len(magnitudes)]
        kind = TRANSPLANT if index % 2 == 0 else PARAMETRIC

        positions = free_positions(
            tile,
            feature_length_arcsec=params.length_arcsec,
            rng=rng,
            count=1,
        )
        if not positions:
            continue
        centre = positions[0]

        if kind == TRANSPLANT:
            scale = 10.0 ** (-0.4 * (magnitude - reference.total_mag_ab))
            # Vary the orientation. The template is a fixed set of pixels, so without this
            # every transplant carries RBH-1's own position angle while the synthetics get a
            # random one - a systematic difference between the classes that has nothing to do
            # with what the test is asking. Spotted by a participant after the first round.
            # Quadrant rotations and reflection only: an arbitrary angle would resample and
            # smooth the knots, which is the bias ADR-0017 exists to avoid. Eight orientations
            # is not uniform coverage, and that limitation is real.
            oriented = transform_template(
                reference.template,
                quadrant_rotations=int(rng.integers(0, 4)),
                mirror=bool(rng.integers(0, 2)),
            )
            injected, _ = inject_template(tile, oriented, centre, flux_scale=scale, rng=rng)
        else:
            local = WakeParameters(
                **{
                    **params.__dict__,
                    "total_mag_ab": magnitude,
                    "colour_ab": reference.colour_ab,
                    "position_angle_deg": float(rng.uniform(0.0, 180.0)),
                }
            )
            injected, _ = inject_synthetic(
                tile, local, centre, psf_fwhm_arcsec=psf_fwhm_arcsec, rng=rng
            )

        image, _ = injected.detection_image()
        y0 = max(min(centre[0] - stamp_half_size, image.shape[0] - 2 * stamp_half_size), 0)
        x0 = max(min(centre[1] - stamp_half_size, image.shape[1] - 2 * stamp_half_size), 0)
        stamps.append(
            BlindStamp(
                index=index,
                kind=kind,
                tile_name=name,
                magnitude=magnitude,
                pixels=np.ascontiguousarray(
                    image[y0 : y0 + 2 * stamp_half_size, x0 : x0 + 2 * stamp_half_size]
                ),
            )
        )

    order = rng.permutation(len(stamps))
    return [
        BlindStamp(
            index=position,
            kind=stamps[source].kind,
            tile_name=stamps[source].tile_name,
            magnitude=stamps[source].magnitude,
            pixels=stamps[source].pixels,
        )
        for position, source in enumerate(order)
    ]


def shared_limits(
    stamps: Sequence[BlindStamp], percentiles: tuple[float, float] = (1.0, 99.5)
) -> tuple[float, float]:
    """Display limits computed across every stamp at once.

    Per-stamp scaling would let contrast alone betray the class, and would also risk the
    display artefact that once made a clean field look striped in this project's own figures.
    """
    combined = np.concatenate([s.pixels.ravel() for s in stamps])
    low, high = np.percentile(combined, percentiles)
    return float(low), float(high)


def score(stamps: Sequence[BlindStamp], answers: Sequence[str]) -> dict[str, float]:
    """Score a completed blind test.

    ``answers`` holds the guessed class per stamp, in stamp order. Accuracy near 0.5 means
    the classes are indistinguishable, which is the outcome that validates the generator.
    """
    if len(answers) != len(stamps):
        msg = f"expected {len(stamps)} answers, got {len(answers)}"
        raise ValueError(msg)

    correct = sum(1 for s, a in zip(stamps, answers, strict=True) if s.kind == a)
    total = len(stamps)
    accuracy = correct / total if total else 0.0
    # Standard error of a proportion under the null that the classes are indistinguishable.
    standard_error = float(np.sqrt(0.25 / total)) if total else 0.0
    return {
        "n": float(total),
        "correct": float(correct),
        "accuracy": accuracy,
        "chance": 0.5,
        "standard_error": standard_error,
        "sigma_above_chance": (accuracy - 0.5) / standard_error if standard_error > 0 else 0.0,
    }
