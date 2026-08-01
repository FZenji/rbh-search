"""Injection-recovery: measure what fraction of injected wakes the pipeline finds.

This is the machinery that turns a search into a measurement (ADR-0009). A trial injects
one source into a real tile, runs the full stage 2-3 cascade, and records not just whether
something was detected but whether it **passed the selection window** - because a detection
that fails the length or axis-ratio cut never reaches the catalogue and must count as a
miss.

It also records fragmentation separately from detection, since Phase 1 showed those come
apart: a wake can be detected as three pieces, none of which survives the window.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from astropy.coordinates import SkyCoord

from rbh.detect import bright_source_mask, detect_ridges
from rbh.linking import link_collinear
from rbh.morphology import Morphology, measure

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from numpy.random import Generator

    from rbh.config import SelectionWindow
    from rbh.detect import RidgeDetection
    from rbh.inject import Injection
    from rbh.tile import Tile

    #: An injector takes a clean tile, a centre and a generator, and returns the injected
    #: tile plus a record of what went in.
    type Injector = Callable[[Tile, tuple[int, int], Generator], tuple[Tile, Injection]]


@dataclass(frozen=True)
class Trial:
    """Outcome of injecting one source and trying to get it back."""

    injection: Injection
    detected: bool
    passes_window: bool
    n_fragments: int
    measured: Morphology | None

    @property
    def fragmented(self) -> bool:
        """Whether the source arrived in more than one piece before stitching."""
        return self.n_fragments > 1


@dataclass(frozen=True)
class Summary:
    """Aggregate statistics over a set of trials at fixed parameters."""

    n_trials: int
    detected: int
    passed_window: int
    fragmented: int
    median_length_arcsec: float
    median_width_arcsec: float
    median_width_variation: float
    median_axis_ratio: float
    label: str = ""

    @property
    def detection_rate(self) -> float:
        """Fraction of injections detected at all."""
        return self.detected / self.n_trials if self.n_trials else 0.0

    @property
    def completeness(self) -> float:
        """Fraction of injections that reach the catalogue.

        This, not the detection rate, is the number that belongs in a selection function.
        """
        return self.passed_window / self.n_trials if self.n_trials else 0.0

    @property
    def fragmentation_rate(self) -> float:
        """Fraction of detected injections that arrived in pieces."""
        return self.fragmented / self.detected if self.detected else 0.0


#: Smallest truth-matching radius, used when the injected length is unknown.
MIN_MATCH_RADIUS_ARCSEC = 4.0


def match_radius_for(length_arcsec: float) -> float:
    """Truth-matching radius appropriate to a feature of this length.

    Half the length is the largest offset a fragment's centroid can have from the injection
    centre, plus a margin for centroiding noise. Going much larger is not free either: an
    over-wide radius starts matching unrelated detections, which showed up as completeness
    *falling* from 94% to 88% when the radius was pushed to 15 arcsec on an 8 arcsec feature.
    """
    if not np.isfinite(length_arcsec) or length_arcsec <= 0:
        return MIN_MATCH_RADIUS_ARCSEC
    return max(MIN_MATCH_RADIUS_ARCSEC, 0.5 * length_arcsec + 2.0)


def _passes(morphology: Morphology, window: SelectionWindow) -> bool:
    return bool(
        window.min_length_arcsec <= morphology.length_arcsec <= window.max_length_arcsec
        and morphology.width_arcsec <= window.max_width_arcsec
        and morphology.axis_ratio >= window.min_axis_ratio
        and morphology.straightness_arcsec <= window.max_straightness_residual_arcsec
    )


def run_trial(
    tile: Tile,
    injector: Injector,
    centre: tuple[int, int],
    *,
    window: SelectionWindow,
    rng: np.random.Generator,
    match_radius_arcsec: float | None = None,
    low_snr: float = 3.0,
    high_snr: float = 5.0,
    min_pixels: int = 40,
) -> Trial:
    """Inject one source, run detection, and report whether it came back.

    A detection counts as the injected source when its centroid falls within
    ``match_radius_arcsec`` of the injection centre. Where several qualify, the largest wins.

    **The radius must scale with the injected length**, which is why the default is computed
    rather than fixed. A feature recovered as a fragment has its centroid displaced toward
    that fragment, by up to half the feature's length. With the fixed 4 arcsec radius used
    initially, a 16 arcsec feature that fragmented was scored a miss despite being detected
    perfectly well: measured completeness at magnitude 23.8 read 19%, against 69% once the
    radius was large enough to reach the fragment. That was a defect in this harness being
    reported as a property of the detector.

    Passing an explicit value overrides the scaling, which is useful for testing but should
    not be done in a measurement.
    """
    injected, record = injector(tile, centre, rng)
    if match_radius_arcsec is None:
        match_radius_arcsec = match_radius_for(record.length_arcsec)
    image, noise = injected.detection_image()
    exclude = bright_source_mask(image, noise)
    fragments = detect_ridges(
        image, noise, low_snr=low_snr, high_snr=high_snr, min_pixels=min_pixels, exclude=exclude
    )
    linked = link_collinear(fragments, injected.pixel_scale_arcsec)

    truth = SkyCoord(injected.wcs.pixel_to_world(float(centre[1]), float(centre[0])))
    n_fragments = sum(
        1 for fragment in fragments if _matches(fragment, injected, truth, match_radius_arcsec)
    )

    matched = [d for d in linked if _matches(d, injected, truth, match_radius_arcsec)]
    if not matched:
        return Trial(
            injection=record,
            detected=False,
            passes_window=False,
            n_fragments=n_fragments,
            measured=None,
        )

    best = max(matched, key=lambda d: d.n_pixels)
    morphology = measure(best, image, injected.wcs, injected.pixel_scale_arcsec)
    return Trial(
        injection=record,
        detected=True,
        passes_window=_passes(morphology, window),
        n_fragments=n_fragments,
        measured=morphology,
    )


def _matches(
    detection: RidgeDetection,
    tile: Tile,
    truth: SkyCoord,
    radius_arcsec: float,
) -> bool:
    """Whether a detection's centroid lies within ``radius_arcsec`` of the injection.

    Only the centroid is needed, so only the centroid is computed. This used to call
    :func:`~rbh.morphology.measure` and discard everything but two of its twelve fields,
    which cost about a fifth of the run time of a trial: the match is tested once per
    fragment and again per linked detection, roughly twenty times per trial, while the
    full measurement is wanted exactly once, for the winner. The centroid here is the
    same flux-unweighted mean of the detection's pixels that ``measure`` reports, so the
    two agree exactly.
    """
    centre = np.column_stack([detection.xs, detection.ys]).astype(np.float64).mean(axis=0)
    centroid = SkyCoord(tile.wcs.pixel_to_world(centre[0], centre[1]))
    return bool(truth.separation(centroid).arcsec <= radius_arcsec)


def _nanmedian(values: Sequence[float]) -> float:
    """Median ignoring NaNs, returning NaN when nothing is measurable."""
    finite = [v for v in values if np.isfinite(v)]
    return float(np.median(finite)) if finite else float("nan")


def summarise(trials: Sequence[Trial], label: str = "") -> Summary:
    """Aggregate a set of trials run at the same parameters."""
    measured = [t.measured for t in trials if t.measured is not None]
    return Summary(
        n_trials=len(trials),
        detected=sum(1 for t in trials if t.detected),
        passed_window=sum(1 for t in trials if t.passes_window),
        fragmented=sum(1 for t in trials if t.detected and t.fragmented),
        median_length_arcsec=float(np.median([m.length_arcsec for m in measured]))
        if measured
        else float("nan"),
        median_width_arcsec=float(np.median([m.width_arcsec for m in measured]))
        if measured
        else float("nan"),
        # nanmedian, not median: a trial too faint for three measurable segments reports
        # NaN, and one such trial would otherwise poison the whole summary.
        median_width_variation=_nanmedian([m.width_variation for m in measured]),
        median_axis_ratio=float(np.median([m.axis_ratio for m in measured]))
        if measured
        else float("nan"),
        label=label,
    )
