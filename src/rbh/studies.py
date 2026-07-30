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
from typing import TYPE_CHECKING

import numpy as np
from scipy import ndimage

from rbh.config import SelectionWindow
from rbh.inject import Injection, free_positions, inject_synthetic, inject_template
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


def _run_transplant(
    sites: Sequence[InjectionSite],
    reference: ReferenceTemplate,
    *,
    flux_scale: float,
    window: SelectionWindow,
    seed: int,
) -> dict[str, float]:
    trials = []
    for index, site in enumerate(sites):
        rng = np.random.default_rng(seed + index)
        injector = _transplant_injector(reference.template, flux_scale, rng)
        trials.append(run_trial(site.tile, injector, site.centre, window=window, rng=rng))
    return _statistics(trials)


def _run_parametric(
    sites: Sequence[InjectionSite],
    params: WakeParameters,
    *,
    psf_fwhm_arcsec: float,
    window: SelectionWindow,
    seed: int,
    randomise_angle: bool = True,
) -> dict[str, float]:
    trials = []
    for index, site in enumerate(sites):
        rng = np.random.default_rng(seed + index)
        local = (
            replace(params, position_angle_deg=float(rng.uniform(0.0, 180.0)))
            if randomise_angle
            else params
        )
        injector = _parametric_injector(local, psf_fwhm_arcsec, rng)
        trials.append(run_trial(site.tile, injector, site.centre, window=window, rng=rng))
    return _statistics(trials)


def _statistics(trials: Sequence[Trial]) -> dict[str, float]:
    summary = summarise(trials)
    return {
        "n": float(summary.n_trials),
        "detection_rate": summary.detection_rate,
        "completeness": summary.completeness,
        "fragmentation": summary.fragmentation_rate,
        "median_length_arcsec": summary.median_length_arcsec,
        "median_width_arcsec": summary.median_width_arcsec,
        "median_axis_ratio": summary.median_axis_ratio,
    }


#: Mismatch tolerances setting the scale of "close enough" for each calibration statistic.
CALIBRATION_TOLERANCES = {
    "median_length_arcsec": 0.40,
    "median_width_arcsec": 0.025,
    "fragmentation": 0.15,
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

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serialisable record of the whole scan."""
        return {
            "psf_fwhm_arcsec": self.psf_fwhm_arcsec,
            "n_sites": self.n_sites,
            "target": self.target,
            "best_parameters": asdict(self.best),
            "best_statistics": self.best_statistics,
            "best_cost": self.best_cost,
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
    tail_values: Sequence[float] = (0.02, 0.10, 0.22, 0.40),
    clumpiness_values: Sequence[float] = (0.0, 0.2, 0.4, 0.6),
    width_values: Sequence[float] = (0.10, 0.16, 0.22, 0.28),
    psf_fwhm_arcsec: float = DEFAULT_PSF_FWHM_ARCSEC,
    length_arcsec: float = DEFAULT_LENGTH_ARCSEC,
    window: SelectionWindow | None = None,
    seed: int = 5000,
) -> CalibrationResult:
    """Fit the generator to the transplant over a joint grid (ADR-0017 Tier 2).

    The grid is joint rather than sequential on purpose. Widening a feature at fixed total
    flux lowers its peak surface brightness, so less of it clears the threshold and the
    recovered length drops; fitting width after length therefore undoes the length match.
    """
    window = window or SelectionWindow()
    target = _run_transplant(sites, reference, flux_scale=1.0, window=window, seed=seed)

    scanned: list[dict[str, float]] = []
    best: tuple[float, WakeParameters, dict[str, float]] | None = None
    for tail, clumpiness, width in itertools.product(tail_values, clumpiness_values, width_values):
        params = WakeParameters(
            length_arcsec=length_arcsec,
            width_arcsec=width,
            clumpiness=clumpiness,
            tail_brightness=tail,
            total_mag_ab=reference.total_mag_ab,
            colour_ab=reference.colour_ab,
        )
        got = _run_parametric(
            sites, params, psf_fwhm_arcsec=psf_fwhm_arcsec, window=window, seed=seed
        )
        cost = calibration_cost(got, target)
        scanned.append(
            {
                "tail_brightness": tail,
                "clumpiness": clumpiness,
                "width_arcsec": width,
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
    )


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
        got = _run_transplant(sites, reference, flux_scale=scale, window=window, seed=seed)
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
                sites, local, psf_fwhm_arcsec=psf_fwhm_arcsec, window=window, seed=seed
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
    lengths_arcsec: Sequence[float] = (2.5, 4.0, 6.0, 8.1, 12.0, 16.0),
    magnitudes: Sequence[float] = (23.0, 23.8, 24.4, 25.0),
    params: WakeParameters | None = None,
    psf_fwhm_arcsec: float = DEFAULT_PSF_FWHM_ARCSEC,
    window: SelectionWindow | None = None,
    per_tile: int = 3,
    seed: int = 9000,
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
                sites, local, psf_fwhm_arcsec=psf_fwhm_arcsec, window=window, seed=seed
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
    total_mag_ab: float, length_arcsec: float, width_arcsec: float
) -> float:
    """Mean surface brightness in mag per square arcsec, for a feature of this size.

    Reported alongside the completeness grid because magnitude alone is misleading across the
    length axis: at fixed total magnitude a longer feature is spread thinner, so it is fainter
    per unit area and harder to detect even though it is nominally "the same brightness".
    """
    area = max(length_arcsec * width_arcsec, 1e-9)
    return total_mag_ab + 2.5 * math.log10(area)


def half_completeness_limit(magnitudes: Sequence[float], completeness: Sequence[float]) -> float:
    """Magnitude at which completeness crosses 50%, by linear interpolation.

    Returns NaN if the curve never crosses, which is the honest answer rather than an
    extrapolation.
    """
    for i in range(len(magnitudes) - 1):
        if completeness[i] >= 0.5 > completeness[i + 1]:
            span = completeness[i] - completeness[i + 1]
            if span <= 0:
                return float(magnitudes[i])
            fraction = (completeness[i] - 0.5) / span
            return float(magnitudes[i] + fraction * (magnitudes[i + 1] - magnitudes[i]))
    return float("nan")
