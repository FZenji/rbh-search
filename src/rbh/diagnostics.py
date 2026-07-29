"""Render what the detector is doing, stage by stage.

Every threshold in this pipeline is a scientific claim, and a claim you cannot look at is
a claim you cannot check. This module draws each stage of the cascade so a human can see
where a candidate came from and, more usefully, what got thrown away.

It is also the seed of the Phase 5 vetting queue (ADR-0011): the stamps a human will
eventually grade are these panels, minus the intermediate diagnostics.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from astropy.coordinates import SkyCoord
from astropy.visualization import ZScaleInterval
from matplotlib.figure import Figure

from rbh.colour import colour_profile
from rbh.detect import bright_source_mask, detect_ridges, ridge_response
from rbh.geometry import principal_axis, project
from rbh.linking import link_collinear
from rbh.morphology import measure

if TYPE_CHECKING:
    from pathlib import Path

    from numpy.typing import NDArray

    from rbh.detect import RidgeDetection
    from rbh.tile import Tile

_GREY = "gray"
_MARK = "#00e5ff"


def _stretch(data: NDArray[np.float32], contrast: float = 0.08) -> tuple[float, float]:
    """Return display limits using the same zscale astronomers use in DS9."""
    low, high = ZScaleInterval(contrast=contrast).get_limits(data)
    return float(low), float(high)


def _mask_of(detection: RidgeDetection, shape: tuple[int, ...]) -> NDArray[np.bool_]:
    mask = np.zeros(shape, dtype=bool)
    mask[detection.ys, detection.xs] = True
    return mask


def _extent(detection: RidgeDetection, tile: Tile) -> float:
    """Along-axis extent of a detection in arcsec, without a full morphology measurement."""
    points = np.column_stack([detection.xs, detection.ys]).astype(np.float64)
    centre = points.mean(axis=0)
    major, _ = principal_axis(points)
    along = project(points, centre, major)
    return float(along.max() - along.min()) * tile.pixel_scale_arcsec


def _bare(ax: object) -> None:
    ax.set_xticks([])  # type: ignore[attr-defined]
    ax.set_yticks([])  # type: ignore[attr-defined]


def render_stages(
    tile: Tile,
    *,
    low_snr: float = 3.0,
    high_snr: float = 5.0,
    min_pixels: int = 40,
    mark: SkyCoord | None = None,
    title: str = "",
) -> Figure:
    """Draw the full detection cascade for one tile.

    Parameters
    ----------
    tile
        The tile to inspect.
    low_snr, high_snr, min_pixels
        Detector settings, passed through so the picture matches the run being debugged.
    mark
        Optional sky position to mark on every panel, e.g. a published coordinate.
    title
        Figure heading.
    """
    image, noise = tile.detection_image()
    response = ridge_response(image, noise)
    bright = bright_source_mask(image, noise)
    masked_response = np.where(bright, 0.0, response)

    fragments = detect_ridges(
        image, noise, low_snr=low_snr, high_snr=high_snr, min_pixels=min_pixels, exclude=bright
    )
    linked = link_collinear(fragments, tile.pixel_scale_arcsec)
    best = max(linked, key=lambda d: d.n_pixels) if linked else None

    figure = Figure(figsize=(21.5, 11.0), layout="constrained")
    if title:
        figure.suptitle(title, fontsize=15)
    axes = figure.subplots(2, 4)

    _draw_data_row(axes[0], tile, image, response, high_snr)
    _draw_decision_row(
        axes[1], tile, image, masked_response, bright, fragments, linked, best, low_snr, high_snr
    )

    for row in axes:
        for ax in row:
            _bare(ax)
    if mark is not None:
        x, y = (float(v) for v in tile.wcs.world_to_pixel(mark))
        for row in axes:
            for ax in row[:3]:
                ax.plot(x, y, "+", color=_MARK, ms=17, mew=1.4, alpha=0.9)
        axes[1][0].plot(x, y, "+", color="white", ms=17, mew=1.4, alpha=0.9)
    return figure


def _draw_data_row(
    axes: object,
    tile: Tile,
    image: NDArray[np.float32],
    response: NDArray[np.float32],
    high_snr: float,
) -> None:
    """Panels 1-3: the observed filters, their combination, and the ridge response."""
    row = list(axes)  # type: ignore[call-overload]
    for column, band in enumerate(tile.bands[:2]):
        low, high = _stretch(band.science)
        row[column].imshow(band.science, origin="lower", cmap=_GREY, vmin=low, vmax=high)
        row[column].set_title(f"1. {band.filter_name} as observed", fontsize=11)

    low, high = _stretch(image)
    row[2].imshow(image, origin="lower", cmap=_GREY, vmin=low, vmax=high)
    row[2].set_title("2. bands combined, background removed", fontsize=11)

    row[3].imshow(response, origin="lower", cmap="magma", vmin=0, vmax=max(8.0, high_snr * 1.6))
    row[3].set_title("3. ridge filter: how line-like is each pixel", fontsize=11)


def _draw_decision_row(
    axes: object,
    tile: Tile,
    image: NDArray[np.float32],
    masked_response: NDArray[np.float32],
    bright: NDArray[np.bool_],
    fragments: list[RidgeDetection],
    linked: list[RidgeDetection],
    best: RidgeDetection | None,
    low_snr: float,
    high_snr: float,
) -> None:
    """Panels 4-7: thresholds, fragments, stitched result, and measurements."""
    row = list(axes)  # type: ignore[call-overload]

    layers = np.zeros((*image.shape, 3), dtype=np.float32)
    layers[..., 2] = (masked_response > low_snr).astype(np.float32) * 0.85  # weak: blue
    layers[..., 0] = (masked_response > high_snr).astype(np.float32)  # strong: red
    layers[..., 1] = bright.astype(np.float32) * 0.55  # masked: green
    row[0].imshow(layers, origin="lower")
    row[0].set_title(
        f"4. blue: above {low_snr:g}x noise | red: above {high_snr:g}x | green: masked as bright",
        fontsize=10,
    )

    low, high = _stretch(image)
    row[1].imshow(image, origin="lower", cmap=_GREY, vmin=low, vmax=high)
    for index, fragment in enumerate(fragments):
        row[1].contour(
            _mask_of(fragment, image.shape), levels=[0.5], colors=f"C{index % 10}", linewidths=1.1
        )
    longest_before = max((_extent(f, tile) for f in fragments), default=0.0)
    row[1].set_title(
        f'5. before stitching: {len(fragments)} pieces, longest {longest_before:.2f}"',
        fontsize=11,
    )

    row[2].imshow(image, origin="lower", cmap=_GREY, vmin=low, vmax=high)
    for detection in linked[:26]:
        row[2].contour(
            _mask_of(detection, image.shape),
            levels=[0.5],
            colors="lime" if detection is best else "#ff7f0e",
            linewidths=1.5 if detection is best else 0.9,
        )
    merges = len(fragments) - len(linked)
    longest_after = max((_extent(d, tile) for d in linked), default=0.0)
    merge_note = f"{merges} merge{'s' if merges != 1 else ''}" if merges else "no merges needed"
    row[2].set_title(
        f'6. after stitching: {len(linked)} objects, longest {longest_after:.2f}" ({merge_note})',
        fontsize=11,
    )

    _annotate_measurements(row[3], tile, best, image)


def _annotate_measurements(
    ax: object, tile: Tile, best: RidgeDetection | None, image: NDArray[np.float32]
) -> None:
    """Draw the measured numbers and, where possible, the colour profile."""
    if best is None:
        ax.set_title("7. nothing detected", fontsize=11)  # type: ignore[attr-defined]
        return

    morphology = measure(best, image, tile.wcs, tile.pixel_scale_arcsec)
    lines = [
        f'length          {morphology.length_arcsec:6.2f}"',
        f'width (FWHM)    {morphology.width_arcsec:6.3f}"',
        f"axis ratio      {morphology.axis_ratio:6.1f}",
        f"position angle  {morphology.position_angle_deg:6.1f} deg",
        f'straightness    {morphology.straightness_arcsec:6.3f}"',
        f"peak S/N        {morphology.peak_snr:6.1f}",
        f"pixels          {morphology.n_pixels:6d}",
    ]

    if len(tile.bands) >= 2:
        blue, red = tile.bands[0].filter_name, tile.bands[1].filter_name
        profile = colour_profile(tile, best, blue, red)
        if profile.along_arcsec.size >= 3:
            ax.errorbar(  # type: ignore[attr-defined]
                profile.along_arcsec,
                profile.colour_ab,
                yerr=profile.colour_error,
                fmt="o-",
                color="#1f77b4",
                ms=4,
                lw=1.2,
                capsize=2,
            )
            ax.set_xlabel("position along the feature (arcsec)", fontsize=9)  # type: ignore[attr-defined]
            ax.set_ylabel(f"{blue} - {red}  (AB)", fontsize=9)  # type: ignore[attr-defined]
            ax.grid(alpha=0.25)  # type: ignore[attr-defined]
            ax.set_title(  # type: ignore[attr-defined]
                f"7. colour along the feature: {profile.gradient_mag_per_arcsec:+.3f}"
                f" mag/arcsec ({profile.gradient_significance:.1f} sigma)",
                fontsize=10,
            )
            lines.append(f'colour grad    {profile.gradient_mag_per_arcsec:+.3f} mag/"')
    ax.text(  # type: ignore[attr-defined]
        0.02,
        0.02,
        "\n".join(lines),
        transform=ax.transAxes,  # type: ignore[attr-defined]
        family="monospace",
        fontsize=8.5,
        va="bottom",
        ha="left",
        bbox={"facecolor": "white", "alpha": 0.75, "edgecolor": "0.6", "pad": 4},
    )


def save_stages(tile: Tile, path: Path, *, dpi: int = 100, **kwargs: object) -> None:
    """Render :func:`render_stages` to an image file."""
    figure = render_stages(tile, **kwargs)  # type: ignore[arg-type]
    figure.savefig(path, dpi=dpi)
