"""Run the detector over many tiles, resumably.

This is the Phase 3 gate made executable: a sweep that can be killed at any point, restarted,
and produce output identical to an uninterrupted run. The resumability lives entirely in
:mod:`rbh.workqueue` (ADR-0020); this module is the part that knows what a tile is and what a
result looks like.

Two things are deliberately kept out of the per-tile payload:

* **No wall-clock, anywhere.** ADR-0012 makes determinism a hard requirement, and a timestamp
  in the output would make every re-run differ from every other while looking like it had
  changed something meaningful. Timings belong in the run record, which is not a result.
* **No aggregate state.** Each tile's file depends only on that tile, so the merge can happen
  afterwards in sorted order and two runs with different worker counts agree exactly.

Every tile records its own **depth** alongside its detections, because the denominator of a
density limit is effective area (ADR-0019) and that cannot be reconstructed later from a
catalogue of survivors alone - a tile with no detections still contributes area, and how much
depends on how deep it was.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from mocpy import MOC

from rbh import __version__
from rbh.area import SkyPatch, completeness_at
from rbh.config import SelectionWindow
from rbh.depth import depth_of
from rbh.footprint import area_arcmin2, region_footprint, tile_region
from rbh.morphology import measure
from rbh.pipeline import detect_in_tile
from rbh.reference import WAKE_LIMIT_BELOW_POINT_SOURCE_MAG
from rbh.tileio import read_tile
from rbh.workqueue import WorkUnit, merge, run_sweep

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from rbh.tile import Tile
    from rbh.workqueue import SweepReport


@dataclass(frozen=True)
class TileSource:
    """A tile to search, and where its pixels came from.

    ``inputs`` feeds the work unit's content-addressed identity, so it must name the actual
    products - URI plus ETag in production, the file path during a local dry run.
    """

    tile_id: str
    path: Path
    inputs: tuple[str, ...]


def local_sources(tiles_dir: Path) -> list[TileSource]:
    """Every cached tile in a directory, in sorted order.

    Sorted because ADR-0012 forbids unsorted directory iteration in anything affecting a
    result: the work-unit set must not depend on what order the filesystem happened to
    return.
    """
    return [
        TileSource(tile_id=path.stem, path=path, inputs=(path.name,))
        for path in sorted(tiles_dir.glob("*.fits"))
    ]


def work_units(
    sources: Sequence[TileSource], config_fingerprint: str, code_version: str = __version__
) -> list[WorkUnit]:
    """Turn tile sources into content-addressed work units."""
    return [
        WorkUnit(
            tile_id=source.tile_id,
            inputs=source.inputs,
            config_fingerprint=config_fingerprint,
            code_version=code_version,
        )
        for source in sources
    ]


def search_tile(tile: Tile, tile_id: str, window: SelectionWindow) -> dict[str, object]:
    """Run the cascade on one tile and return its result payload.

    Records **both** the raw detection count and the survivors. A source found as three
    fragments reaches no catalogue, and Phase 2 had to learn twice that collapsing those two
    numbers into one hides the difference between "not detected" and "detected and rejected".
    """
    detections = detect_in_tile(tile)
    image, _ = tile.detection_image()

    survivors: list[dict[str, float]] = []
    for detection in detections:
        morphology = measure(detection, image, tile.wcs, tile.pixel_scale_arcsec)
        passes = (
            window.min_length_arcsec <= morphology.length_arcsec <= window.max_length_arcsec
            and morphology.width_arcsec <= window.max_width_arcsec
            and morphology.axis_ratio >= window.min_axis_ratio
            and morphology.straightness_arcsec <= window.max_straightness_residual_arcsec
        )
        if not passes:
            continue
        survivors.append(
            {
                "ra_deg": morphology.centroid_ra_deg,
                "dec_deg": morphology.centroid_dec_deg,
                "length_arcsec": morphology.length_arcsec,
                "width_arcsec": morphology.width_arcsec,
                "axis_ratio": morphology.axis_ratio,
                "position_angle_deg": morphology.position_angle_deg,
                "straightness_arcsec": morphology.straightness_arcsec,
                "peak_snr": morphology.peak_snr,
                "n_pixels": float(morphology.n_pixels),
            }
        )

    # Sorted so the payload does not depend on the order the labeller happened to emit
    # components in, which is an implementation detail of scipy and not of the sky.
    survivors.sort(key=lambda row: (row["ra_deg"], row["dec_deg"]))

    return {
        "tile_id": tile_id,
        "n_detections": len(detections),
        "n_survivors": len(survivors),
        "depth_mag": depth_of(tile),
        "filters": list(tile.filter_names),
        # The tile's own exact footprint, so the survey area is computable from committed
        # results alone - no manifest, no archive query, and as deterministic and resumable
        # as the sweep itself. It also means a tile that found nothing still contributes its
        # area, which is the half of the denominator a catalogue of survivors cannot supply.
        "s_region": tile_region(tile.wcs, tile.shape),
        "survivors": survivors,
    }


def run(
    sources: Sequence[TileSource],
    output_dir: Path,
    *,
    config_fingerprint: str,
    window: SelectionWindow | None = None,
) -> SweepReport:
    """Search every tile that has no committed result yet."""
    window = window or SelectionWindow()
    by_id = {source.tile_id: source for source in sources}

    def process(unit: WorkUnit) -> dict[str, object]:
        source = by_id[unit.tile_id]
        return search_tile(read_tile(source.path), unit.tile_id, window)

    return run_sweep(work_units(sources, config_fingerprint), process, output_dir)


def summarise(output_dir: Path) -> dict[str, object]:
    """Aggregate committed results, in the deterministic merge order of ADR-0020."""
    rows = merge(output_dir)
    return {
        "n_tiles": len(rows),
        "n_detections": sum(int(r["n_detections"]) for r in rows),  # type: ignore[call-overload]
        "n_survivors": sum(int(r["n_survivors"]) for r in rows),  # type: ignore[call-overload]
        "tiles": [str(r["tile_id"]) for r in rows],
    }


def _depth_of_row(row: dict[str, object]) -> float:
    """Bluest-band limiting magnitude for a swept tile.

    The bluer band is the one the selection function was measured in, and it is the shallower
    of the ACS pair, so taking it is the conservative choice as well as the consistent one.
    """
    depths = row.get("depth_mag")
    if not isinstance(depths, dict) or not depths:
        return float("nan")
    return float(min(depths.values()))


@dataclass(frozen=True)
class SurveyProducts:
    """The numbers a paper divides by, derived from committed sweep results.

    A dataclass rather than a dictionary because every consumer was casting fields out of
    ``object`` to use them, which is the type system pointing out that the shape is known and
    should be declared.
    """

    n_tiles: int
    summed_arcmin2: float
    unique_arcmin2: float
    overlap_fraction: float
    #: ``None`` rather than NaN when no tile carried a measurable depth.
    #:
    #: NaN never equals itself, so a NaN field makes the whole dataclass non-reflexive under
    #: ``==``: two identical empty runs compare unequal, and "the same run does not equal
    #: itself" is not a property a published data product should have. It went unnoticed
    #: because every test had tiles; the Phase 3 gate exercise, run against an empty
    #: directory by accident, is what surfaced it.
    median_depth_mag: float | None
    #: Effective area against source magnitude - the actual denominator (ADR-0019).
    effective_area_arcmin2: tuple[tuple[float, float], ...]
    candidates: tuple[dict[str, object], ...]

    @property
    def n_candidates(self) -> int:
        """Count of window survivors. **Candidates, never discoveries** (ADR-0015)."""
        return len(self.candidates)

    def to_dict(self) -> dict[str, object]:
        """JSON-serialisable form, for the published data product."""
        return {
            "n_tiles": self.n_tiles,
            "summed_arcmin2": self.summed_arcmin2,
            "unique_arcmin2": self.unique_arcmin2,
            "overlap_fraction": self.overlap_fraction,
            "median_depth_mag": self.median_depth_mag,
            "effective_area_arcmin2": [
                {"mag": mag, "arcmin2": area} for mag, area in self.effective_area_arcmin2
            ],
            "n_candidates": self.n_candidates,
            "candidates": list(self.candidates),
        }


def survey_products(
    output_dir: Path, magnitudes: Sequence[float] = (23.0, 23.5, 24.0, 24.5, 25.0)
) -> SurveyProducts:
    """Turn committed sweep results into the numbers a paper divides by.

    Everything here comes from the per-tile outputs and nothing else: the footprint each tile
    recorded, the depth it measured, and the candidates it found. That is deliberate. It
    means the published area is exactly as reproducible as the sweep (ADR-0020), it cannot
    drift from what was actually searched, and re-deriving it needs no archive access.

    Reports **raw, unique and effective** area together (ADR-0019). Unique area is what was
    searched; effective area is what was searched *usefully* at a given source brightness,
    and it is the denominator of a density limit. The gap between them is the selection
    function doing its job, and quoting only one of the three hides it.
    """
    rows = merge(output_dir)
    regions = [str(r.get("s_region", "")) for r in rows]
    depths = [_depth_of_row(r) for r in rows]

    patches: list[SkyPatch] = []
    claimed: MOC | None = None
    summed = 0.0
    # Deepest first, so overlapping sky is credited once to the coverage that searched it
    # best - the same rule the manifest-level accounting uses.
    for depth, region in sorted(zip(depths, regions, strict=True), key=lambda pair: -pair[0]):
        moc = region_footprint(region)
        if moc is None or not math.isfinite(depth):
            continue
        summed += area_arcmin2(moc)
        fresh = moc if claimed is None else moc.difference(claimed)
        gained = area_arcmin2(fresh)
        if gained > 0:
            patches.append(SkyPatch(area_arcmin2=gained, point_source_limit_mag=depth))
        claimed = moc if claimed is None else claimed.union(moc)

    unique = area_arcmin2(claimed) if claimed is not None else 0.0
    candidates: list[dict[str, object]] = []
    for row in rows:
        survivors = row.get("survivors")
        if not isinstance(survivors, list):
            continue
        candidates.extend(
            {"tile_id": str(row["tile_id"]), **entry}
            for entry in survivors
            if isinstance(entry, dict)
        )

    finite_depths = [d for d in depths if math.isfinite(d)]
    return SurveyProducts(
        n_tiles=len(rows),
        summed_arcmin2=summed,
        unique_arcmin2=unique,
        # Clamped at zero: unique can exceed summed by a hair when the two are equal and
        # quantisation rounds differently, and a "-0.0% overlap" reads as a bug.
        overlap_fraction=max(0.0, 1.0 - unique / summed) if summed > 0 else 0.0,
        median_depth_mag=float(np.median(finite_depths)) if finite_depths else None,
        effective_area_arcmin2=tuple(
            (
                magnitude,
                sum(
                    p.area_arcmin2
                    * completeness_at(
                        magnitude,
                        p.point_source_limit_mag - WAKE_LIMIT_BELOW_POINT_SOURCE_MAG,
                    )
                    for p in patches
                ),
            )
            for magnitude in magnitudes
        ),
        candidates=tuple(candidates),
    )
