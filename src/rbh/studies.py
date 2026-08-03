"""The measurement studies that produce published numbers.

These were prototyped as throwaway scripts, which was a mistake: they generate the
completeness figures the project's scientific claims rest on, and ADR-0012 requires that
anything a published number depends on be reproducible from version control. A script in a
temporary directory is not.

Two studies live here:

* :func:`calibrate_generator` fits the parametric generator to the transplanted real object
  (ADR-0017 Tier 2). Note it scans a **joint** grid: the parameters interact, and tuning
  them one at a time silently undoes earlier matches.
* :func:`completeness_grid` measures completeness against brightness at several clumpiness
  values, which is the Phase 2 deliverable.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import asdict, dataclass, replace
from typing import TYPE_CHECKING, NamedTuple

import numpy as np
from scipy import ndimage

from rbh.config import SelectionWindow
from rbh.inject import Injection, free_positions, inject_synthetic, inject_template
from rbh.parallel import map_trials
from rbh.pipeline import detect_in_tile
from rbh.recovery import Trial, run_trial, summarise
from rbh.synthetic import WakeParameters
from rbh.template import extract_template
from rbh.tileio import read_tile

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

    from numpy.random import Generator

    from rbh.template import SourceTemplate
    from rbh.tile import Tile

    #: Signature of an injection callable, as :func:`rbh.recovery.run_trial` expects it.
    type Injector = Callable[[Tile, tuple[int, int], Generator], tuple[Tile, Injection]]

#: Assumed effective PSF of the drizzled products. This is an assumption, not a measurement:
#: the discovery cutout contains no stars, only 175-215 pixel galaxies which measure their
#: own sizes. It is degenerate with the generator's fitted width - see ADR-0017.
DEFAULT_PSF_FWHM_ARCSEC = 0.11

#: Feature length used throughout, matching RBH-1's full extent.
DEFAULT_LENGTH_ARCSEC = 8.10


@dataclass(frozen=True)
class InjectionSite:
    """One destination tile and one position within it."""

    tile_name: str
    tile: Tile
    centre: tuple[int, int]


@dataclass(frozen=True)
class ReferenceTemplate:
    """The transplantable real object, with the photometry a synthetic must match."""

    template: SourceTemplate
    blue_filter: str
    red_filter: str
    total_mag_ab: float
    colour_ab: float


def reference_template(fixture_path: Path) -> ReferenceTemplate:
    """Extract RBH-1 from the committed fixture as a transplant template."""
    tile = read_tile(fixture_path)
    detection = max(detect_in_tile(tile), key=lambda d: d.n_pixels)
    template = extract_template(tile, detection, name="RBH-1")

    blue, red = tile.bands[0], tile.bands[1] if len(tile.bands) > 1 else tile.bands[0]
    blue_mag = blue.zeropoint_ab - 2.5 * float(np.log10(template.total_flux(blue.filter_name)))
    red_mag = red.zeropoint_ab - 2.5 * float(np.log10(template.total_flux(red.filter_name)))
    return ReferenceTemplate(
        template=template,
        blue_filter=blue.filter_name,
        red_filter=red.filter_name,
        total_mag_ab=blue_mag,
        colour_ab=blue_mag - red_mag,
    )


def real_object_exclusion(fixture_path: Path, grow_pixels: int = 45) -> np.ndarray:
    """Mask covering the real RBH-1, so injections into the fixture avoid it.

    Two features in the same place would confuse truth matching, silently inflating the
    recovered completeness.
    """
    tile = read_tile(fixture_path)
    detection = max(detect_in_tile(tile), key=lambda d: d.n_pixels)
    mask = np.zeros(tile.shape, dtype=bool)
    mask[detection.ys, detection.xs] = True
    return np.asarray(ndimage.binary_dilation(mask, iterations=grow_pixels), dtype=bool)


def collect_sites(
    fixture_path: Path,
    destinations_dir: Path | None,
    *,
    per_tile: int = 4,
    feature_length_arcsec: float = DEFAULT_LENGTH_ARCSEC,
    seed: int = 20230208,
) -> list[InjectionSite]:
    """Gather injection sites from the fixture and any cached destination tiles.

    The fixture is included with the real object masked off; cached destinations from the
    same visit contribute the rest. Using one visit keeps instrument, depth and epoch
    matched to the object we calibrate against.
    """
    sites: list[InjectionSite] = []
    entries: list[tuple[str, Tile, np.ndarray | None]] = [
        ("fixture", read_tile(fixture_path), real_object_exclusion(fixture_path))
    ]
    if destinations_dir is not None and destinations_dir.is_dir():
        entries.extend(
            (path.stem, read_tile(path), None) for path in sorted(destinations_dir.glob("*.fits"))
        )

    for index, (name, tile, exclude) in enumerate(entries):
        positions = free_positions(
            tile,
            feature_length_arcsec=feature_length_arcsec,
            rng=np.random.default_rng(seed + index),
            count=per_tile,
            exclude=exclude,
        )
        sites.extend(InjectionSite(tile_name=name, tile=tile, centre=p) for p in positions)
    return sites


def _transplant_injector(template: SourceTemplate, flux_scale: float, rng: Generator) -> Injector:
    """Build a transplant injector bound to one template, scale and generator."""

    def inject(tile: Tile, centre: tuple[int, int], _rng: Generator) -> tuple[Tile, Injection]:
        return inject_template(tile, template, centre, flux_scale=flux_scale, rng=rng)

    return inject


def _parametric_injector(
    params: WakeParameters, psf_fwhm_arcsec: float, rng: Generator
) -> Injector:
    """Build a parametric injector bound to one parameter set and generator."""

    def inject(tile: Tile, centre: tuple[int, int], _rng: Generator) -> tuple[Tile, Injection]:
        return inject_synthetic(tile, params, centre, psf_fwhm_arcsec=psf_fwhm_arcsec, rng=rng)

    return inject


class _TransplantTask(NamedTuple):
    """One transplant trial, described entirely by picklable data.

    The injectors elsewhere in this module are closures over a live generator, which
    cannot cross a process boundary, so a parallel worker is handed the ingredients and
    builds its own on the far side. See :mod:`rbh.parallel`.
    """

    tile: Tile
    centre: tuple[int, int]
    template: SourceTemplate
    flux_scale: float
    window: SelectionWindow
    seed: int


class _ParametricTask(NamedTuple):
    """One parametric trial, described entirely by picklable data."""

    tile: Tile
    centre: tuple[int, int]
    params: WakeParameters
    psf_fwhm_arcsec: float
    window: SelectionWindow
    seed: int
    randomise_angle: bool


def _transplant_trial(task: _TransplantTask) -> Trial:
    rng = np.random.default_rng(task.seed)
    injector = _transplant_injector(task.template, task.flux_scale, rng)
    return run_trial(task.tile, injector, task.centre, window=task.window, rng=rng)


def _parametric_trial(task: _ParametricTask) -> Trial:
    rng = np.random.default_rng(task.seed)
    local = (
        replace(task.params, position_angle_deg=float(rng.uniform(0.0, 180.0)))
        if task.randomise_angle
        else task.params
    )
    injector = _parametric_injector(local, task.psf_fwhm_arcsec, rng)
    return run_trial(task.tile, injector, task.centre, window=task.window, rng=rng)


def _run_transplant(
    sites: Sequence[InjectionSite],
    reference: ReferenceTemplate,
    *,
    flux_scale: float,
    window: SelectionWindow,
    seed: int,
    workers: int | None = None,
) -> dict[str, float]:
    tasks = [
        _TransplantTask(
            site.tile, site.centre, reference.template, flux_scale, window, seed + index
        )
        for index, site in enumerate(sites)
    ]
    return _statistics(map_trials(_transplant_trial, tasks, workers=workers))


def _run_parametric(
    sites: Sequence[InjectionSite],
    params: WakeParameters,
    *,
    psf_fwhm_arcsec: float,
    window: SelectionWindow,
    seed: int,
    randomise_angle: bool = True,
    workers: int | None = None,
) -> dict[str, float]:
    tasks = [
        _ParametricTask(
            site.tile,
            site.centre,
            params,
            psf_fwhm_arcsec,
            window,
            seed + index,
            randomise_angle,
        )
        for index, site in enumerate(sites)
    ]
    return _statistics(map_trials(_parametric_trial, tasks, workers=workers))


def _statistics(trials: Sequence[Trial]) -> dict[str, float]:
    summary = summarise(trials)
    return {
        "n": float(summary.n_trials),
        "detection_rate": summary.detection_rate,
        "completeness": summary.completeness,
        "fragmentation": summary.fragmentation_rate,
        "median_length_arcsec": summary.median_length_arcsec,
        "median_width_arcsec": summary.median_width_arcsec,
        "median_width_variation": summary.median_width_variation,
        "median_straightness_arcsec": summary.median_straightness_arcsec,
        "median_axis_ratio": summary.median_axis_ratio,
    }


#: Mismatch tolerances setting the scale of "close enough" for each calibration statistic.
#:
#: ``median_width_variation`` was added after the second blind-test pre-flight, where it
#: separated real from synthetic stamps at AUC 0.84 while every fitted statistic matched.
#: Its tolerance is the widest in relative terms because it is measured from four segments
#: per feature and is correspondingly noisy; the point is to stop the generator sitting at
#: a value nothing constrains, not to pin it to three decimal places.
#: ``median_straightness_arcsec`` was added after round 2, where a participant reported the
#: synthetics had "no jumps or lumps, or changes in direction mid trail". The quantity was
#: already measured by :mod:`rbh.morphology` and reported everywhere - it simply had never
#: been part of what the fit was asked to match, so the generator was free to be as smooth
#: as it liked. That is the third distinct instance of the same failure, and the reason the
#: rule is now: *anything a person could use has to be in this dictionary*.
#: ``completeness`` was added last, and it should have been first: it is the quantity the
#: whole project exists to report. It was left out on the assumption that it is saturated at
#: the calibration magnitude and so carries no information - the transplant does sit at
#: 1.00 there. **That assumption was never checked, and it is wrong.** Across one grid the
#: synthetics ranged from 0.60 to 0.95 at the same magnitude, falling monotonically as the
#: brightness ramp steepened. Completeness was the single most discriminating statistic
#: available and it was the one excluded, which is the most likely explanation for the
#: generator reading 0.29 mag pessimistic against the transplant.
CALIBRATION_TOLERANCES = {
    "median_length_arcsec": 0.40,
    "median_width_arcsec": 0.025,
    "median_width_variation": 0.05,
    "median_straightness_arcsec": 0.02,
    "fragmentation": 0.15,
    "completeness": 0.05,
}


@dataclass(frozen=True)
class CalibrationResult:
    """Outcome of fitting the generator to the transplant."""

    target: dict[str, float]
    best: WakeParameters
    best_statistics: dict[str, float]
    best_cost: float
    scanned: list[dict[str, float]]
    psf_fwhm_arcsec: float
    n_sites: int
    #: Parameters whose best value sits on an end of the range scanned. See
    #: :attr:`is_pinned` - a non-empty list here means the fit should not be trusted.
    pinned: tuple[str, ...] = ()

    @property
    def is_pinned(self) -> bool:
        """Whether the best fit sits on an edge of the search grid.

        A fit at the edge is not the best fit; it is the best *available*, and the true
        optimum probably lies outside the range scanned. This is worth flagging loudly
        because it looks exactly like a successful fit: the reported statistics can sit
        comfortably inside tolerance while the parameter is straining against a bound
        that was chosen by guesswork. The first recalibration after the blind test did
        precisely that, pinning ``width_arcsec`` at the top of its range.
        """
        return bool(self.pinned)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serialisable record of the whole scan."""
        return {
            "psf_fwhm_arcsec": self.psf_fwhm_arcsec,
            "n_sites": self.n_sites,
            "target": self.target,
            "best_parameters": asdict(self.best),
            "best_statistics": self.best_statistics,
            "best_cost": self.best_cost,
            "pinned": list(self.pinned),
            "scanned": self.scanned,
            "tolerances": CALIBRATION_TOLERANCES,
        }


def calibration_cost(got: dict[str, float], target: dict[str, float]) -> float:
    """Return the combined normalised mismatch across the calibration statistics."""
    return sum(
        abs(got[key] - target[key]) / tolerance for key, tolerance in CALIBRATION_TOLERANCES.items()
    )


def calibrate_generator(
    sites: Sequence[InjectionSite],
    reference: ReferenceTemplate,
    *,
    #: Ranges are wide on purpose. An earlier version of this grid was narrowed to keep
    #: the run short, and the fit promptly pinned itself against the bound that trimming
    #: had created - a self-inflicted version of exactly what :func:`_pinned_parameters`
    #: exists to catch. Trials now run across cores, so breadth is cheap and there is no
    #: excuse for trading it away.
    #: Extended to 1.0 - a feature of uniform brightness end to end - after round 2 of the
    #: blind test. A participant described RBH-1's brightness as barely changing along its
    #: length while the synthetics visibly faded, and the fitted value was 0.10, a tenfold
    #: ramp. The grid had stopped at 0.40, so **the answer being described was never in the
    #: search space**. Nothing flagged it: the pinning check cannot fire on 0.10 when 0.02
    #: is also scanned, because that is an interior point of a range that was simply in the
    #: wrong place.
    tail_values: Sequence[float] = (0.60, 0.80, 1.00),
    clumpiness_values: Sequence[float] = (0.0, 0.2, 0.4),
    #: **Do not trim these ranges using minima measured under a different objective.** That
    #: was done once, on the reasoning that a sharp interior minimum makes the outer points
    #: redundant - costs of 3.28, 1.53, 1.91, 5.43 across this axis, so why keep the ends.
    #: Then ``completeness`` was added to the objective and all three trimmed axes pinned at
    #: once, every one of them against a bound that had just been removed. A cost surface is
    #: a property of the objective, not of the model, so **changing the objective voids every
    #: measurement used to justify narrowing a grid.** The pinning check caught it, which is
    #: the third time it has paid for itself, but it should not have had to.
    width_values: Sequence[float] = (0.19, 0.22, 0.25),
    #: Multi-node spine deviation, giving direction changes partway along rather than a
    #: single smooth bow. Fitted against the straightness residual.
    path_wander_values: Sequence[float] = (0.08, 0.14, 0.20),
    #: Fraction of the length carrying flux. Measured on the real object at about
    #: 0.72; scanned around that because the measurement is one object in one band.
    bright_fraction_values: Sequence[float] = (0.58, 0.65, 0.72),
    #: Added as a fitted axis rather than a constant after the second blind-test
    #: pre-flight: set by eye it was the strongest remaining discriminator between real
    #: and synthetic stamps. Interpreted as a log-width scatter, so 0.6 means the width
    #: swings by a factor of e**0.6, roughly 1.8, either way along the feature.
    width_jitter_values: Sequence[float] = (0.15, 0.30, 0.45),
    psf_fwhm_arcsec: float = DEFAULT_PSF_FWHM_ARCSEC,
    length_arcsec: float = DEFAULT_LENGTH_ARCSEC,
    window: SelectionWindow | None = None,
    seed: int = 5000,
    workers: int | None = None,
) -> CalibrationResult:
    """Fit the generator to the transplant over a joint grid (ADR-0017 Tier 2).

    The grid is joint rather than sequential on purpose. Widening a feature at fixed total
    flux lowers its peak surface brightness, so less of it clears the threshold and the
    recovered length drops; fitting width after length therefore undoes the length match.
    """
    window = window or SelectionWindow()
    target = _run_transplant(
        sites, reference, flux_scale=1.0, window=window, seed=seed, workers=workers
    )

    scanned: list[dict[str, float]] = []
    best: tuple[float, WakeParameters, dict[str, float]] | None = None
    for tail, clumpiness, width, jitter, wander, bright in itertools.product(
        tail_values,
        clumpiness_values,
        width_values,
        width_jitter_values,
        path_wander_values,
        bright_fraction_values,
    ):
        params = WakeParameters(
            length_arcsec=length_arcsec,
            width_arcsec=width,
            width_jitter=jitter,
            path_wander_arcsec=wander,
            bright_fraction=bright,
            clumpiness=clumpiness,
            tail_brightness=tail,
            total_mag_ab=reference.total_mag_ab,
            colour_ab=reference.colour_ab,
        )
        got = _run_parametric(
            sites,
            params,
            psf_fwhm_arcsec=psf_fwhm_arcsec,
            window=window,
            seed=seed,
            workers=workers,
        )
        cost = calibration_cost(got, target)
        scanned.append(
            {
                "tail_brightness": tail,
                "clumpiness": clumpiness,
                "width_arcsec": width,
                "width_jitter": jitter,
                "path_wander_arcsec": wander,
                "bright_fraction": bright,
                "cost": cost,
                **got,
            }
        )
        if best is None or cost < best[0]:
            best = (cost, params, got)

    if best is None:  # pragma: no cover - only reachable with an empty parameter range
        msg = "calibration grid was empty"
        raise ValueError(msg)
    return CalibrationResult(
        target=target,
        best=best[1],
        best_statistics=best[2],
        best_cost=best[0],
        scanned=sorted(scanned, key=lambda row: row["cost"]),
        psf_fwhm_arcsec=psf_fwhm_arcsec,
        n_sites=len(sites),
        pinned=_pinned_parameters(
            best[1],
            {
                "tail_brightness": tail_values,
                "clumpiness": clumpiness_values,
                "width_arcsec": width_values,
                "bright_fraction": bright_fraction_values,
                "width_jitter": width_jitter_values,
                "path_wander_arcsec": path_wander_values,
            },
        ),
    )


#: Values below which a fitted parameter has no physical meaning. A grid whose lowest
#: value is one of these is not an arbitrary bound that could be widened, so a fit
#: landing there is a real answer rather than a truncated search: zero clumpiness is a
#: perfectly smooth feature and zero tail brightness is no tail, both of which the
#: generator can express. Without this the check flags every smooth best fit and quickly
#: trains the reader to ignore it.
PHYSICAL_FLOORS = {"clumpiness": 0.0, "tail_brightness": 0.0}


def _pinned_parameters(best: WakeParameters, grids: dict[str, Sequence[float]]) -> tuple[str, ...]:
    """Name the fitted parameters whose best value sits at an end of their scanned range.

    Two ends are not alike. Landing on the top of a range always means the search may
    have been truncated. Landing on the bottom means that only when the bottom was a
    choice -- see :data:`PHYSICAL_FLOORS`.

    A single-valued grid cannot pin anything and is skipped, otherwise every parameter
    held deliberately fixed would report itself as a problem.
    """
    fitted = asdict(best)
    pinned = []
    for name, values in grids.items():
        if len(set(values)) <= 1:
            continue
        low, high = min(values), max(values)
        at_floor = math.isclose(fitted[name], low) and not math.isclose(
            low, PHYSICAL_FLOORS.get(name, -math.inf)
        )
        if at_floor or math.isclose(fitted[name], high):
            pinned.append(name)
    return tuple(pinned)


def completeness_grid(
    sites: Sequence[InjectionSite],
    reference: ReferenceTemplate,
    *,
    magnitudes: Sequence[float] = (22.5, 23.0, 23.5, 23.8, 24.1, 24.4, 24.8, 25.3),
    clumpiness_values: Sequence[float] = (0.0, 0.3, 0.6, 0.9),
    params: WakeParameters | None = None,
    psf_fwhm_arcsec: float = DEFAULT_PSF_FWHM_ARCSEC,
    window: SelectionWindow | None = None,
    seed: int = 7000,
    workers: int | None = None,
) -> list[dict[str, float | str]]:
    """Measure completeness against magnitude, for the transplant and several clumpiness values.

    Reports the transplant alongside the generator because ADR-0017 requires them compared
    rather than the model trusted alone. ``completeness`` counts sources that pass the
    selection window, not merely those detected - a source found as three fragments reaches
    no catalogue.
    """
    window = window or SelectionWindow()
    params = params or WakeParameters()
    rows: list[dict[str, float | str]] = []

    for magnitude in magnitudes:
        scale = 10.0 ** (-0.4 * (magnitude - reference.total_mag_ab))
        got = _run_transplant(
            sites, reference, flux_scale=scale, window=window, seed=seed, workers=workers
        )
        rows.append({"source": "transplant", "mag": magnitude, **got})

    for clumpiness in clumpiness_values:
        for magnitude in magnitudes:
            local = replace(
                params,
                clumpiness=clumpiness,
                total_mag_ab=magnitude,
                colour_ab=reference.colour_ab,
            )
            got = _run_parametric(
                sites,
                local,
                psf_fwhm_arcsec=psf_fwhm_arcsec,
                window=window,
                seed=seed,
                workers=workers,
            )
            rows.append(
                {
                    "source": f"parametric c={clumpiness}",
                    "mag": magnitude,
                    **got,
                }
            )
    return rows


def completeness_vs_length(
    fixture_path: Path,
    destinations_dir: Path | None,
    *,
    #: 3.0 and 3.5 added to sample the short end finely. Only ``bright_fraction`` of the
    #: injected length carries flux, so a 2.5 arcsec feature presents a 1.8 arcsec bright
    #: segment - below ADR-0007's 2 arcsec floor. There is now a hard short-length cutoff
    #: in the selection function, and it needs locating rather than straddling.
    lengths_arcsec: Sequence[float] = (2.5, 3.0, 3.5, 4.0, 6.0, 8.1, 12.0, 16.0),
    magnitudes: Sequence[float] = (23.0, 23.8, 24.4, 25.0),
    params: WakeParameters | None = None,
    psf_fwhm_arcsec: float = DEFAULT_PSF_FWHM_ARCSEC,
    window: SelectionWindow | None = None,
    per_tile: int = 3,
    seed: int = 9000,
    workers: int | None = None,
) -> list[dict[str, float | str]]:
    """Measure completeness across the length axis as well as brightness.

    Sites are recollected for each length, because a longer feature needs a larger clear
    margin inside the tile. That has a consequence worth stating: with 20 arcsec tiles a
    16 arcsec feature can only be centred within about 4 arcsec of the tile centre, so
    trials within one tile sit on nearly the same background and are not independent. Longer
    still does not fit at all, which means **this measurement cannot cover the full
    2-25 arcsec selection window of ADR-0007** - a constraint on the tiling, not on the
    detector, and one Phase 3 should fix by using larger tiles.

    The transplant cannot participate here: it is a fixed set of real pixels, and stretching
    it to another length would resample and smooth the knots, which is precisely the bias
    ADR-0017 exists to avoid. So the length axis rests on the parametric generator, which was
    calibrated only at 8.1 arcsec. Extrapolation along this axis is an assumption, and the
    8.1 arcsec column is the one that is anchored.

    **``length_arcsec`` here is the injected full extent, not what the detector reports.**
    Since ``bright_fraction`` was measured off the real object, only about 72% of a feature
    carries flux, so the recovered length is systematically shorter - which is how RBH-1 is
    injected at 8.10 arcsec and recovered at 5.61. Each row records ``median_length_arcsec``
    alongside, and the two must not be conflated.

    That has a consequence at the short end. A 2.5 arcsec injection presents a 1.8 arcsec
    bright segment, below the 2 arcsec floor of ADR-0007's window, so it cannot pass however
    bright it is. **The selection function now has a hard short-length cutoff**, and it is
    inherited from a bright fraction measured on exactly one object at one length. Whether a
    short wake has the same bright fraction as an 8 arcsec one is an assumption, not a
    measurement, and it is doing real work here.
    """
    window = window or SelectionWindow()
    params = params or WakeParameters()
    reference = reference_template(fixture_path)
    rows: list[dict[str, float | str]] = []

    for length in lengths_arcsec:
        try:
            sites = collect_sites(
                fixture_path,
                destinations_dir,
                per_tile=per_tile,
                feature_length_arcsec=length,
                seed=seed,
            )
        except ValueError:
            # The feature does not fit in the tile at all; record the gap rather than skip it.
            rows.extend(
                {
                    "length_arcsec": length,
                    "mag": magnitude,
                    "n": 0.0,
                    "completeness": float("nan"),
                    "detection_rate": float("nan"),
                    "fragmentation": float("nan"),
                    "note": "does not fit in tile",
                }
                for magnitude in magnitudes
            )
            continue

        for magnitude in magnitudes:
            local = replace(
                params,
                length_arcsec=length,
                total_mag_ab=magnitude,
                colour_ab=reference.colour_ab,
            )
            got = _run_parametric(
                sites,
                local,
                psf_fwhm_arcsec=psf_fwhm_arcsec,
                window=window,
                seed=seed,
                workers=workers,
            )
            rows.append(
                {
                    "length_arcsec": length,
                    "mag": magnitude,
                    "note": "",
                    **got,
                }
            )
    return rows


def mean_surface_brightness(
    total_mag_ab: float,
    length_arcsec: float,
    width_arcsec: float,
    bright_fraction: float = 1.0,
) -> float:
    """Mean surface brightness in mag per square arcsec, over the part that carries flux.

    Reported alongside the completeness grid because magnitude alone is misleading across the
    length axis: at fixed total magnitude a longer feature is spread thinner, so it is fainter
    per unit area and harder to detect even though it is nominally "the same brightness".

    ``bright_fraction`` matters, and defaulting it to 1 would quietly misreport the number.
    The flux is confined to that fraction of the length, so the area it is spread over is
    smaller and the surface brightness correspondingly higher - by 0.36 mag at the fitted
    0.72. Before the real object's profile was measured the generator had a monotonic ramp
    with no such parameter, so this argument did not exist and every figure produced by this
    function assumed the flux filled the whole length.
    """
    area = max(length_arcsec * max(bright_fraction, 1e-9) * width_arcsec, 1e-9)
    return total_mag_ab + 2.5 * math.log10(area)


def describe_half_limit(magnitudes: Sequence[float], completeness: Sequence[float]) -> str:
    """Render the 50% limit as text, distinguishing the two ways it can be absent.

    :func:`half_completeness_limit` returns NaN both when the curve never rises to 50% and
    when it never falls to it, and those mean **opposite things**: the first is a feature
    that cannot be found at any brightness sampled, the second one that is found at every
    brightness sampled. Printing them identically is how the length grid briefly showed a
    2.5 arcsec feature (7% everywhere) and a 4.0 arcsec feature (57% at the faintest point)
    with the same label.
    """
    limit = half_completeness_limit(magnitudes, completeness)
    if not math.isnan(limit):
        return f"{limit:.2f}"
    if not completeness:
        return "n/a"
    if max(completeness) < 0.5:
        return f"< {min(magnitudes):.1f}"
    return f"> {max(magnitudes):.1f}"


def half_completeness_limit(magnitudes: Sequence[float], completeness: Sequence[float]) -> float:
    """Magnitude at which completeness crosses 50%, by linear interpolation.

    Returns NaN if the curve never crosses, which is the honest answer rather than an
    extrapolation. **NaN is ambiguous on its own** - see :func:`describe_half_limit`, which
    should be used for anything a person reads.
    """
    for i in range(len(magnitudes) - 1):
        if completeness[i] >= 0.5 > completeness[i + 1]:
            span = completeness[i] - completeness[i + 1]
            if span <= 0:
                return float(magnitudes[i])
            fraction = (completeness[i] - 0.5) / span
            return float(magnitudes[i] + fraction * (magnitudes[i + 1] - magnitudes[i]))
    return float("nan")
