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
from scipy import ndimage

from rbh.geometry import principal_axis
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


#: Statistics the pre-flight scores the two classes on. Each one exists because it was a
#: reported or measured tell, not because it seemed like a good idea: the head contrast
#: and flux variation come from the round 1 debrief ("a large head at the start", "an
#: extremely clean and linear trail"), and the width variation from the round 2
#: pre-flight, where it separated the classes at AUC 0.84 while every fitted statistic
#: matched.
PREFLIGHT_STATISTICS = ("head_contrast", "width_variation", "flux_variation")

#: How far from 0.5 an AUC must sit before the set is called separable. At 20 stamps the
#: standard error on an AUC under the null is about 0.13, so 0.28 is roughly two of them:
#: loose enough not to cry wolf on noise, tight enough to catch a cue a person could use.
PREFLIGHT_AUC_MARGIN = 0.28


def stamp_statistics(pixels: NDArray[np.float32], n_segments: int = 12) -> dict[str, float]:
    """Measure the tell statistics on one stamp.

    Works on the stamp's own pixels rather than the rendered PNG, so display stretch and
    8-bit quantisation cannot influence the answer. The feature is located by taking the
    brightest pixels near the stamp centre - where the injection is by construction - and
    fitting their principal axis, rather than by rerunning the detector, which would drag
    the whole cascade into what should be a cheap check.
    """
    smooth = ndimage.gaussian_filter(np.asarray(pixels, dtype=np.float64), 1.5)
    half = np.array(smooth.shape) / 2.0
    ys, xs = np.mgrid[: smooth.shape[0], : smooth.shape[1]]
    core = (smooth > np.percentile(smooth, 99.0)) & (
        np.hypot(ys - half[0], xs - half[1]) < 0.42 * smooth.shape[0]
    )
    nan = dict.fromkeys(PREFLIGHT_STATISTICS, float("nan"))
    if core.sum() < 20:
        return nan

    points = np.column_stack([xs[core], ys[core]]).astype(np.float64)
    centre = points.mean(axis=0)
    major, minor = principal_axis(points)

    offset = np.column_stack([xs.ravel() - centre[0], ys.ravel() - centre[1]])
    along, across = offset @ major, offset @ minor
    weight = np.clip(smooth.ravel() - np.median(smooth), 0.0, None)

    band = np.abs(across) < 6.0
    if band.sum() < n_segments * 4:
        return nan
    edges = np.linspace(along[band].min(), along[band].max(), n_segments + 1)
    which = np.digitize(along[band], edges) - 1

    flux, width = [], []
    for segment in range(n_segments):
        selected = band.copy()
        selected[band] = which == segment
        w = weight[selected]
        if w.sum() <= 0:
            continue
        a = across[selected]
        flux.append(float(w.sum()))
        width.append(float(np.sqrt(np.average((a - np.average(a, weights=w)) ** 2, weights=w))))

    if len(flux) < 4:
        return nan
    flux_values, width_values = np.array(flux), np.array(width)
    return {
        # "A large head at the start of the wake": brightest segment against the typical one.
        "head_contrast": float(flux_values.max() / max(np.median(flux_values), 1e-9)),
        # "Much more irregular, a bit blobby" against a constant-width ribbon.
        "width_variation": float(width_values.std() / max(width_values.mean(), 1e-9)),
        "flux_variation": float(flux_values.std() / max(flux_values.mean(), 1e-9)),
    }


def _auc(values: NDArray[np.float64], is_real: NDArray[np.bool_]) -> float:
    """Probability that a random real stamp outranks a random synthetic one.

    Rank-sum rather than a mean difference, so it is unaffected by the scale of the
    statistic and by outliers, and reads directly as "how often could someone using this
    one cue alone get it right".
    """
    order = np.argsort(values)
    ranks = np.empty(values.size, dtype=float)
    ranks[order] = np.arange(1, values.size + 1)
    n_real, n_synthetic = int(is_real.sum()), int((~is_real).sum())
    if n_real == 0 or n_synthetic == 0:
        return float("nan")
    return float((ranks[is_real].sum() - n_real * (n_real + 1) / 2) / (n_real * n_synthetic))


def preflight(stamps: Sequence[BlindStamp]) -> dict[str, float]:
    """Score how separable the two classes are, before spending a person's attention.

    This does **not** replace the human test and cannot. A machine misses what a person
    sees at a glance - which is exactly what happened in round 1, where four fitted
    statistics all matched and the classes were still obvious. The converse is what makes
    it worth running: if a single number separates the classes, the set has a tell and
    there is no point running the human test yet.

    Returns one AUC per statistic. 0.5 means indistinguishable on that cue; distance from
    0.5 in either direction is separation, since a person only needs the cue to be
    informative, not to point in any particular direction.
    """
    rows = [stamp_statistics(stamp.pixels) for stamp in stamps]
    is_real = np.array([stamp.is_real for stamp in stamps])
    result = {}
    for name in PREFLIGHT_STATISTICS:
        values = np.array([row[name] for row in rows])
        usable = np.isfinite(values)
        result[name] = _auc(values[usable], is_real[usable]) if usable.sum() >= 4 else float("nan")
    return result


def separating_statistics(auc: dict[str, float]) -> tuple[str, ...]:
    """Names of the statistics that separate the classes by more than the noise floor."""
    return tuple(
        name
        for name, value in auc.items()
        if np.isfinite(value) and abs(value - 0.5) > PREFLIGHT_AUC_MARGIN
    )
