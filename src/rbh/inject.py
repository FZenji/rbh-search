"""Add sources to real tiles.

Injection happens into real archival pixels, upstream of detection (ADR-0009), so an
injected source meets every subsequent cut exactly as a real one would - including the real
background, its correlated noise, real neighbours and real artifacts. Only the source needs
modelling, which is half the realism problem solved by construction.

Transplanted templates carry their own noise, and the correction for that is the subtlest
thing in this module. See :func:`inject_template`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from rbh.detect import bright_source_mask
from rbh.synthetic import render_bands
from rbh.tile import BandImage, Tile

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from rbh.synthetic import WakeParameters
    from rbh.template import SourceTemplate


@dataclass(frozen=True)
class Injection:
    """Record of what was injected where, for comparison against what came back."""

    kind: str
    centre_y: float
    centre_x: float
    flux_scale: float
    length_arcsec: float
    total_mag_ab: float
    clumpiness: float | None
    detail: str


def _with_added(tile: Tile, added: dict[str, NDArray[np.float32]]) -> Tile:
    """Return a copy of ``tile`` with per-band arrays added, leaving the original alone."""
    bands = tuple(
        BandImage(
            filter_name=band.filter_name,
            science=(band.science + added.get(band.filter_name, 0.0)).astype(np.float32),
            weight=band.weight.copy(),
            zeropoint_ab=band.zeropoint_ab,
        )
        for band in tile.bands
    )
    provenance = dict(tile.provenance)
    provenance["injected"] = "true"
    return Tile(
        bands=bands,
        wcs=tile.wcs,
        pixel_scale_arcsec=tile.pixel_scale_arcsec,
        provenance=provenance,
    )


def _paste_window(
    tile_shape: tuple[int, ...], stamp_shape: tuple[int, ...], centre: tuple[int, int]
) -> tuple[tuple[slice, slice], tuple[slice, slice]] | None:
    """Return matching slices into the tile and the stamp, or None if fully outside."""
    half_y, half_x = stamp_shape[0] // 2, stamp_shape[1] // 2
    ty0, tx0 = centre[0] - half_y, centre[1] - half_x
    ty1, tx1 = ty0 + stamp_shape[0], tx0 + stamp_shape[1]

    cy0, cx0 = max(ty0, 0), max(tx0, 0)
    cy1, cx1 = min(ty1, tile_shape[0]), min(tx1, tile_shape[1])
    if cy0 >= cy1 or cx0 >= cx1:
        return None
    return (
        (slice(cy0, cy1), slice(cx0, cx1)),
        (slice(cy0 - ty0, cy1 - ty0), slice(cx0 - tx0, cx1 - tx0)),
    )


def inject_template(
    tile: Tile,
    template: SourceTemplate,
    centre: tuple[int, int],
    *,
    flux_scale: float = 1.0,
    rng: np.random.Generator,
    compensate_noise: bool = True,
) -> tuple[Tile, Injection]:
    """Transplant a real source's pixels into a tile.

    The template's own noise travels with its pixels, so an injected source always sits in
    slightly noisier sky than a real one at the same depth - by up to a factor sqrt(2) when
    template and destination depths match. That makes transplant completeness a
    **conservative lower bound**, which is the safe direction for an upper limit.

    Scaling the flux by ``f`` also scales that carried noise by ``f``, which would make
    faint injections progressively *cleaner* than bright ones and put a brightness-dependent
    tilt into the completeness curve. With ``compensate_noise`` set, noise of variance
    ``(1 - f^2) * sigma^2`` is added inside the footprint so the carried noise is
    ``sigma`` regardless of ``f``. The penalty is then a constant offset rather than a
    slope, which is what makes the curve interpretable.
    """
    if flux_scale <= 0:
        msg = f"flux_scale must be positive, got {flux_scale}"
        raise ValueError(msg)

    window = _paste_window(tile.shape, template.shape, centre)
    if window is None:
        msg = f"injection centre {centre} places the template entirely outside the tile"
        raise ValueError(msg)
    tile_slice, stamp_slice = window
    footprint = template.footprint[stamp_slice]

    added: dict[str, NDArray[np.float32]] = {}
    for band in tile.bands:
        name = band.filter_name
        if name not in template.stamps:
            continue
        layer = np.zeros(tile.shape, dtype=np.float32)
        contribution = template.stamps[name][stamp_slice] * np.float32(flux_scale)

        if compensate_noise and flux_scale < 1.0:
            extra = float(np.sqrt(max(1.0 - flux_scale**2, 0.0)) * template.noise_rms[name])
            noise = rng.normal(0.0, extra, size=contribution.shape).astype(np.float32)
            contribution = contribution + np.where(footprint, noise, np.float32(0.0))

        layer[tile_slice] = contribution
        added[name] = layer

    injection = Injection(
        kind="transplant",
        centre_y=float(centre[0]),
        centre_x=float(centre[1]),
        flux_scale=flux_scale,
        length_arcsec=float("nan"),
        total_mag_ab=float("nan"),
        clumpiness=None,
        detail=f"template={template.name} compensate_noise={compensate_noise}",
    )
    return _with_added(tile, added), injection


def inject_synthetic(
    tile: Tile,
    params: WakeParameters,
    centre: tuple[int, int],
    *,
    psf_fwhm_arcsec: float,
    rng: np.random.Generator,
) -> tuple[Tile, Injection]:
    """Render a parametric wake at ``centre`` and add it to the tile.

    No noise compensation is needed or wanted here: the rendered source is noiseless, so
    the only noise the injected object carries is the destination tile's own. That is
    exactly right, and it is also why the parametric generator brackets the transplant from
    the optimistic side rather than agreeing with it.
    """
    zeropoints = {band.filter_name: band.zeropoint_ab for band in tile.bands}
    rendered = render_bands(
        params,
        (tile.shape[0], tile.shape[1]),
        tile.pixel_scale_arcsec,
        zeropoints,
        psf_fwhm_arcsec=psf_fwhm_arcsec,
        centre=(float(centre[0]), float(centre[1])),
        rng=rng,
    )
    injection = Injection(
        kind="parametric",
        centre_y=float(centre[0]),
        centre_x=float(centre[1]),
        flux_scale=1.0,
        length_arcsec=params.length_arcsec,
        total_mag_ab=params.total_mag_ab,
        clumpiness=params.clumpiness,
        detail=f"n_clumps={params.n_clumps} pa={params.position_angle_deg:.1f}",
    )
    return _with_added(tile, rendered), injection


def free_positions(
    tile: Tile,
    *,
    feature_length_arcsec: float,
    rng: np.random.Generator,
    count: int,
    centre_clearance_arcsec: float = 1.2,
    avoid_snr: float = 8.0,
    exclude: NDArray[np.bool_] | None = None,
    max_attempts_per_position: int = 400,
) -> list[tuple[int, int]]:
    """Draw injection centres for a feature of the given length.

    Two separate constraints, which an earlier version wrongly conflated into one:

    * **Edge margin** keeps the whole feature inside the tile, so length is never clipped by
      the boundary. That needs half the feature length, whatever its orientation.
    * **Centre clearance** keeps the injection off a *bright* source. This is a small radius,
      not a whole clear square. Demanding a source-free square the size of the feature finds
      no valid position at all in a real archival tile, and it would also bias the
      measurement toward the emptiest sky, which is not where real wakes live.

    Faint overlaps are therefore permitted, deliberately: real wakes do cross other
    objects, and forbidding it would measure completeness in unrealistically empty fields.

    ``exclude`` masks regions off entirely - used to keep injections away from the real
    RBH-1 when the fixture doubles as a destination, since two features in one place would
    confuse the truth matching.
    """
    image, noise = tile.detection_image()
    occupied = bright_source_mask(image, noise, threshold_snr=avoid_snr, grow_pixels=3)
    if exclude is not None:
        occupied = occupied | exclude

    edge = int(np.ceil((feature_length_arcsec / 2.0) / tile.pixel_scale_arcsec)) + 2
    clearance = max(int(np.ceil(centre_clearance_arcsec / tile.pixel_scale_arcsec)), 1)
    if 2 * edge >= min(tile.shape[0], tile.shape[1]):
        msg = (
            f"a {feature_length_arcsec} arcsec feature does not fit in a {tile.shape} tile "
            f"at {tile.pixel_scale_arcsec} arcsec/pixel"
        )
        raise ValueError(msg)

    positions: list[tuple[int, int]] = []
    for _ in range(count):
        for _attempt in range(max_attempts_per_position):
            y = int(rng.integers(edge, tile.shape[0] - edge))
            x = int(rng.integers(edge, tile.shape[1] - edge))
            box = occupied[
                max(y - clearance, 0) : y + clearance,
                max(x - clearance, 0) : x + clearance,
            ]
            if not box.any():
                positions.append((y, x))
                break
    return positions
