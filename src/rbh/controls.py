"""Negative controls: measure what the pipeline finds when there is nothing to find.

Completeness alone is half a selection function. Without a false-positive rate you cannot
set a sensible score threshold, cannot size the human vetting queue, and cannot turn a
candidate count into a space-density limit.

There is a specific debt to settle here. ADR-0016 adopted collinear fragment linking and
stated plainly that it "can also join unrelated collinear noise blobs, raising the
false-positive rate by an amount that must be *measured* rather than assumed small". This
module measures it.

Four controls, each isolating a different failure mode:

* **Noise** - synthetic Gaussian noise with the real tiles' statistics and nothing else in
  it. Every survivor is unambiguously false, so this is the only control that yields a true
  false-positive rate.
* **Real sky** - the archival tiles as they are. Survivors here are *candidates*, not
  established false positives: some will be real edge-on galaxies. This sets the vetting
  budget rather than measuring purity.
* **Rotated and mirrored real sky** - tests that the detector is invariant under quadrant
  rotation and reflection, i.e. that it is not keying on the pixel grid.

    This is **not** an artifact-rejection test, though an earlier version of this docstring
    claimed it was. Rotating the pixels rotates any detector-frame artifact along with them,
    so their relationship to the grid is preserved and nothing is decoupled. The test that
    does isolate detector-frame artifacts is cross-visit: the same sky observed at a
    different roll angle, where artifacts move on the sky and real objects do not. That
    needs multi-visit coverage, so it belongs to Phase 3.
* **Shuffled filters** - band A of one tile paired with band B of another. Real objects
  appear in both bands of the *same* field, so this measures how often cross-filter
  coincidence happens by chance, which is the assumption ADR-0006 rests on.

Every control is run with linking on and off, on identical data, so the linking cost is a
paired comparison. That matters: the paired ratio is far better constrained than either
absolute rate given how little area we have.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from rbh.config import SelectionWindow
from rbh.detect import bright_source_mask, detect_ridges
from rbh.linking import link_collinear
from rbh.morphology import measure
from rbh.tile import BandImage, Tile

if TYPE_CHECKING:
    from collections.abc import Sequence

    from numpy.typing import NDArray

#: One square degree in square arcseconds.
_ARCSEC2_PER_DEG2 = 3600.0 * 3600.0


@dataclass(frozen=True)
class ControlResult:
    """Outcome of running the detector over data containing no injected wakes."""

    label: str
    linked: bool
    n_tiles: int
    area_arcsec2: float
    raw_detections: int
    survivors: int

    @property
    def area_deg2(self) -> float:
        """Searched area in square degrees."""
        return self.area_arcsec2 / _ARCSEC2_PER_DEG2

    @property
    def survivors_per_deg2(self) -> float:
        """Survivors scaled to one square degree.

        A large extrapolation from a small area: treat the Poisson uncertainty below as
        the headline, not this central value.
        """
        return self.survivors / self.area_deg2 if self.area_deg2 > 0 else 0.0

    @property
    def poisson_error_per_deg2(self) -> float:
        """One-sigma Poisson uncertainty on :attr:`survivors_per_deg2`.

        Uses sqrt(N+1) so that a zero count still yields a usable upper bound rather than
        an uncertainty of zero.
        """
        if self.area_deg2 <= 0:
            return 0.0
        return float(np.sqrt(self.survivors + 1.0)) / self.area_deg2

    def to_dict(self) -> dict[str, float | str | bool | int]:
        """Return a JSON-serialisable record, including the derived rates."""
        return {
            "label": self.label,
            "linked": self.linked,
            "n_tiles": self.n_tiles,
            "area_arcsec2": self.area_arcsec2,
            "raw_detections": self.raw_detections,
            "survivors": self.survivors,
            "survivors_per_deg2": self.survivors_per_deg2,
            "poisson_error_per_deg2": self.poisson_error_per_deg2,
        }


def count_survivors(
    tile: Tile,
    *,
    window: SelectionWindow,
    link: bool,
    low_snr: float = 3.0,
    high_snr: float = 5.0,
    min_pixels: int = 40,
) -> tuple[int, int]:
    """Return (raw detections, survivors of the selection window) for one tile."""
    image, noise = tile.detection_image()
    exclude = bright_source_mask(image, noise)
    detections = detect_ridges(
        image, noise, low_snr=low_snr, high_snr=high_snr, min_pixels=min_pixels, exclude=exclude
    )
    if link:
        detections = link_collinear(detections, tile.pixel_scale_arcsec)

    survivors = 0
    for detection in detections:
        morphology = measure(detection, image, tile.wcs, tile.pixel_scale_arcsec)
        if (
            window.min_length_arcsec <= morphology.length_arcsec <= window.max_length_arcsec
            and morphology.width_arcsec <= window.max_width_arcsec
            and morphology.axis_ratio >= window.min_axis_ratio
            and morphology.straightness_arcsec <= window.max_straightness_residual_arcsec
        ):
            survivors += 1
    return len(detections), survivors


def _tile_area_arcsec2(tile: Tile) -> float:
    return float(tile.shape[0] * tile.shape[1]) * tile.pixel_scale_arcsec**2


def run_control(
    tiles: Sequence[Tile],
    label: str,
    *,
    link: bool,
    window: SelectionWindow | None = None,
) -> ControlResult:
    """Run the detector over tiles containing no injected sources and tally survivors."""
    window = window or SelectionWindow()
    raw = 0
    survivors = 0
    area = 0.0
    for tile in tiles:
        tile_raw, tile_survivors = count_survivors(tile, window=window, link=link)
        raw += tile_raw
        survivors += tile_survivors
        area += _tile_area_arcsec2(tile)
    return ControlResult(
        label=label,
        linked=link,
        n_tiles=len(tiles),
        area_arcsec2=area,
        raw_detections=raw,
        survivors=survivors,
    )


def noise_tiles(
    reference: Tile,
    count: int,
    *,
    rng: np.random.Generator,
) -> list[Tile]:
    """Generate pure-noise tiles matching a real tile's shape, noise level and zero points.

    The noise is white, which real drizzled noise is not - drizzling correlates neighbouring
    pixels. Correlated noise produces *more* spurious ridge response than white noise at the
    same variance, so this control is optimistic and its rate is a lower bound. The real-sky
    control brackets it from the other side.
    """
    scatters = [band.background_and_sigma()[1] for band in reference.bands]
    tiles: list[Tile] = []
    for _ in range(count):
        bands = tuple(
            BandImage(
                filter_name=band.filter_name,
                science=rng.normal(0.0, sigma, size=reference.shape).astype(np.float32),
                weight=band.weight.copy(),
                zeropoint_ab=band.zeropoint_ab,
            )
            for band, sigma in zip(reference.bands, scatters, strict=True)
        )
        tiles.append(
            Tile(
                bands=bands,
                wcs=reference.wcs,
                pixel_scale_arcsec=reference.pixel_scale_arcsec,
                provenance={"fetched_from": "synthetic-noise"},
            )
        )
    return tiles


def transformed_tiles(
    tiles: Sequence[Tile], *, quadrant_rotations: int, mirror: bool
) -> list[Tile]:
    """Rotate by multiples of 90 degrees and optionally mirror each tile's pixels.

    The WCS is deliberately left alone: these tiles are only ever counted, never positioned.

    Measured on real archival tiles, the detector returns **exactly** identical counts before
    and after any quadrant rotation or reflection. That is the expected and desired answer -
    isotropic filters plus 8-connectivity should be invariant - and it is worth having as a
    guarantee rather than an assumption. What it does not do is test artifact rejection: a
    detector-frame artifact rotates with the pixels, so nothing about its relation to the
    grid changes.
    """
    turns = quadrant_rotations % 4

    def apply(array: NDArray[np.float32]) -> NDArray[np.float32]:
        out = np.rot90(array, turns)
        if mirror:
            out = np.fliplr(out)
        return np.ascontiguousarray(out, dtype=np.float32)

    return [
        Tile(
            bands=tuple(
                BandImage(
                    filter_name=band.filter_name,
                    science=apply(band.science),
                    weight=apply(band.weight),
                    zeropoint_ab=band.zeropoint_ab,
                )
                for band in tile.bands
            ),
            wcs=tile.wcs,
            pixel_scale_arcsec=tile.pixel_scale_arcsec,
            provenance={**tile.provenance, "transformed": f"rot{turns * 90}mirror{mirror}"},
        )
        for tile in tiles
    ]


def shuffled_filter_tiles(tiles: Sequence[Tile]) -> list[Tile]:
    """Pair each tile's first band with the *next* tile's second band.

    Real objects appear in both bands of the same field. Pairing bands from different fields
    destroys that while preserving each band's noise and source statistics, so surviving
    detections measure how often cross-filter coincidence occurs by chance - the assumption
    Tier A vetting rests on (ADR-0006).
    """
    usable = [t for t in tiles if len(t.bands) >= 2]
    if len(usable) < 2:
        return []
    shuffled: list[Tile] = []
    for index, tile in enumerate(usable):
        other = usable[(index + 1) % len(usable)]
        if tile.shape != other.shape:
            continue
        shuffled.append(
            Tile(
                bands=(tile.bands[0], other.bands[1]),
                wcs=tile.wcs,
                pixel_scale_arcsec=tile.pixel_scale_arcsec,
                provenance={"fetched_from": "shuffled-filters"},
            )
        )
    return shuffled


def linking_cost(with_link: ControlResult, without_link: ControlResult) -> dict[str, float]:
    """Compare survivor counts with and without linking on identical data.

    The ratio is the number ADR-0016 promised to measure. Reported as a paired comparison
    because both arms see exactly the same pixels, which constrains the ratio far better
    than the small searched area constrains either rate on its own.
    """
    added = with_link.survivors - without_link.survivors
    ratio = (
        with_link.survivors / without_link.survivors
        if without_link.survivors > 0
        else float("inf")
        if with_link.survivors > 0
        else 1.0
    )
    return {
        "survivors_with_linking": float(with_link.survivors),
        "survivors_without_linking": float(without_link.survivors),
        "added_by_linking": float(added),
        "ratio": ratio,
        "area_deg2": with_link.area_deg2,
    }
