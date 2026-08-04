"""Simulate shallower data, so the selection function can be measured against depth.

ADR-0001 commits the search to the whole public extragalactic archive and notes that depth
across it is wildly non-uniform; ADR-0009 makes the selection function the thing that turns a
null result into a limit. Phase 2 measured that function at exactly one depth - the RBH-1
discovery visit, one orbit per filter - so every completeness number the project quotes is
conditional on it.

ADR-0018 closes that gap by degrading real tiles rather than fetching shallower ones. The
arithmetic is fixed by the drizzle convention the rest of the pipeline already relies on:
weight is proportional to effective exposure time and pixel noise scales as ``1/sqrt(weight)``.

**What this does not simulate.** Genuinely shallow archival data carries more than photon
noise: cosmic-ray residuals survive fewer dithers, sky subtraction is poorer, the effective
PSF is worse, and more instrumental artifacts remain. All of those make real shallow data
*harder* than this simulation of it, so completeness measured here is an **upper bound**.
That is the safe direction for a null result - overstating our completeness understates the
space density we can claim - but it is a bound, not an estimate, and must be quoted as one.

Deeper cannot be simulated at all: noise can be added, not removed.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import TYPE_CHECKING

import numpy as np

from rbh.tile import BandImage, Tile

if TYPE_CHECKING:
    from numpy.random import Generator
    from numpy.typing import NDArray

#: Signal-to-noise a point source is taken to need to count as "detected" when quoting a
#: band's limiting magnitude. Five sigma is the convention in the imaging literature; it is
#: only a label for the depth axis, and nothing in the detector depends on it.
LIMITING_SNR = 5.0


def degrade_band(band: BandImage, exposure_fraction: float, rng: Generator) -> BandImage:
    """Return the band as it would look with ``exposure_fraction`` of the exposure time.

    Weight scales with exposure; noise scales as ``1/sqrt(weight)``. Reaching a total noise
    of ``sigma / sqrt(f)`` from a starting ``sigma`` therefore means adding an independent
    draw of variance ``sigma^2 (1/f - 1)``, which is what this does, per pixel, against the
    band's own noise map so that the tile's real weight structure is preserved rather than
    replaced by a flat number.

    Uncovered pixels stay uncovered: zero weight means no data, and no amount of scaling
    turns that into data.
    """
    if not 0.0 < exposure_fraction <= 1.0:
        msg = f"exposure_fraction must be in (0, 1], got {exposure_fraction}"
        raise ValueError(msg)
    if exposure_fraction == 1.0:
        return band

    covered = band.covered
    extra_variance_scale = 1.0 / exposure_fraction - 1.0
    added = np.zeros(band.science.shape, dtype=np.float64)
    added[covered] = rng.normal(0.0, 1.0, size=int(covered.sum())) * (
        band.noise_map()[covered] * math.sqrt(extra_variance_scale)
    )

    return replace(
        band,
        science=np.asarray(band.science + added, dtype=np.float32),
        weight=np.asarray(band.weight * exposure_fraction, dtype=np.float32),
    )


def degrade_tile(tile: Tile, exposure_fraction: float, rng: Generator) -> Tile:
    """Degrade every band of a tile to the same fraction of its exposure.

    The same fraction across bands, because the alternative - degrading filters
    independently - would change the tile's colour selection as well as its depth, and
    ADR-0006's two-filter requirement is measured separately.
    """
    return replace(
        tile,
        bands=tuple(degrade_band(band, exposure_fraction, rng) for band in tile.bands),
    )


def limiting_magnitude(
    band: BandImage, aperture_arcsec: float, pixel_scale_arcsec: float, snr: float = LIMITING_SNR
) -> float:
    """Point-source limiting magnitude of a band, in the AB system.

    Depth is reported this way rather than as an exposure time because exposure time is not
    comparable across instruments, filters or epochs, and the corpus spans all three. The
    axis exists to predict detectability, so it is indexed by the quantity that does.

    Uses the noise at the *median* weight, matching how every threshold in the pipeline is
    normalised, and assumes noise is uncorrelated between pixels. Drizzling correlates
    adjacent pixels, so this understates the true noise in an aperture and therefore
    overstates the depth by a fixed factor - a systematic offset shared by every row of the
    axis, which leaves comparisons between depths unaffected.
    """
    _, sigma = band.background_and_sigma()
    n_pixels = math.pi * (0.5 * aperture_arcsec / pixel_scale_arcsec) ** 2
    flux = snr * sigma * math.sqrt(max(n_pixels, 1.0))
    if flux <= 0:
        return float("nan")
    return band.zeropoint_ab - 2.5 * math.log10(flux)


def depth_of(tile: Tile, aperture_arcsec: float = 0.4) -> dict[str, float]:
    """Limiting magnitude per filter, keyed by filter name."""
    return {
        band.filter_name: limiting_magnitude(band, aperture_arcsec, tile.pixel_scale_arcsec)
        for band in tile.bands
    }


def noise_ratio(original: BandImage, degraded: BandImage) -> float:
    """How much noisier the degraded band is, measured rather than assumed.

    Exists so the arithmetic above can be checked against the pixels it produced instead of
    being trusted: a fraction ``f`` should give a ratio of ``1/sqrt(f)``.
    """
    _, before = original.background_and_sigma()
    _, after = degraded.background_and_sigma()
    return after / before if before > 0 else float("nan")


def added_noise_map(band: BandImage, exposure_fraction: float) -> NDArray[np.float32]:
    """Return the per-pixel sigma :func:`degrade_band` would add. Diagnostic only."""
    scale = math.sqrt(max(1.0 / exposure_fraction - 1.0, 0.0))
    return np.asarray(band.noise_map() * scale, dtype=np.float32)
