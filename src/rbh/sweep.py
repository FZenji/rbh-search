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

from dataclasses import dataclass
from typing import TYPE_CHECKING

from rbh import __version__
from rbh.config import SelectionWindow
from rbh.depth import depth_of
from rbh.morphology import measure
from rbh.pipeline import detect_in_tile
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
