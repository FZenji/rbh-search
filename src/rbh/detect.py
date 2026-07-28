"""Stage 2 - find thin ridge-like features in a tile.

The primary sweep is a multi-scale ridge (vesselness) filter, chosen over line transforms
and source segmentation in ADR-0005. Two details matter more than the filter choice:

* the response is thresholded against the **noise map**, not a global sigma, and
* thresholding is **hysteretic**. A single high threshold breaks a low-surface-brightness
  filament into disconnected knots, which is the one failure mode this project can least
  afford. Measured on RBH-1: at a flat 4-sigma cut the feature fragments into two pieces
  of 2.1 and 2.0 arcsec; hysteresis recovers it as a single 5.5 arcsec object.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from astropy.stats import sigma_clipped_stats
from scipy import ndimage
from skimage.filters import meijering
from skimage.measure import label

if TYPE_CHECKING:
    from numpy.typing import NDArray

#: Ridge-filter scales in pixels. Chosen to span roughly the PSF width up to the widest
#: feature we accept (ADR-0007), for a 0.05 arcsec/pixel grid.
DEFAULT_SCALES: tuple[float, ...] = (1.0, 1.5, 2.0, 3.0)


@dataclass(frozen=True)
class RidgeDetection:
    """A connected set of pixels flagged as ridge-like."""

    ys: NDArray[np.intp]
    xs: NDArray[np.intp]
    peak_snr: float
    n_pixels: int

    @property
    def pixels(self) -> NDArray[np.intp]:
        """Pixel coordinates as an ``(N, 2)`` array of ``(x, y)``."""
        return np.column_stack([self.xs, self.ys])


def ridge_response(
    image: NDArray[np.float32],
    noise: NDArray[np.float32],
    scales: tuple[float, ...] = DEFAULT_SCALES,
) -> NDArray[np.float32]:
    """Return the noise-normalised multi-scale ridge response.

    The image is divided by its noise map before filtering, so that a given response
    corresponds to the same significance everywhere regardless of local depth. The result
    is expressed in units of its own robust scatter, so it is directly thresholdable.
    """
    finite = np.isfinite(noise) & (noise > 0)
    normalised = np.zeros(image.shape, dtype=np.float32)
    normalised[finite] = image[finite] / noise[finite]

    response = meijering(normalised, sigmas=list(scales), black_ridges=False)
    response = np.nan_to_num(response, nan=0.0, posinf=0.0, neginf=0.0)

    # Normalise by the sigma-clipped scatter of the response background. A median
    # absolute deviation was tried first and is wrong here: the Meijering response is
    # positive-definite and strongly right-skewed, so the MAD of the bulk comes out ~35%
    # *larger* than the clipped standard deviation, silently making every threshold
    # stricter than its nominal value. Iterative clipping rejects the real-ridge tail
    # instead of being inflated by it.
    background, scale = _background_scale(response)
    if scale <= 0:
        return np.zeros(image.shape, dtype=np.float32)
    normalised_response: NDArray[np.float32] = np.asarray(
        (response - background) / scale, dtype=np.float32
    )
    return normalised_response


def _background_scale(response: NDArray[np.float32]) -> tuple[float, float]:
    """Return the sigma-clipped median and standard deviation of a filter response."""
    _, median, std = sigma_clipped_stats(response, sigma=3.0, maxiters=5)
    return float(median), float(std)


def bright_source_mask(
    image: NDArray[np.float32],
    noise: NDArray[np.float32],
    threshold_snr: float = 40.0,
    grow_pixels: int = 6,
) -> NDArray[np.bool_]:
    """Mask bright compact sources and their immediate surroundings.

    Bright galaxies and stars produce strong ridge responses at their edges, and stars
    additionally carry diffraction spikes. Growing the mask suppresses both.
    """
    finite = np.isfinite(noise) & (noise > 0)
    snr = np.zeros(image.shape, dtype=np.float32)
    snr[finite] = image[finite] / noise[finite]
    seed = snr > threshold_snr
    if grow_pixels > 0:
        seed = ndimage.binary_dilation(seed, iterations=grow_pixels)
    return np.asarray(seed, dtype=bool)


def detect_ridges(
    image: NDArray[np.float32],
    noise: NDArray[np.float32],
    *,
    scales: tuple[float, ...] = DEFAULT_SCALES,
    low_snr: float = 3.0,
    high_snr: float = 5.0,
    min_pixels: int = 40,
    exclude: NDArray[np.bool_] | None = None,
) -> list[RidgeDetection]:
    """Find ridge-like connected components using hysteresis thresholding.

    Components are grown at ``low_snr`` for connectivity but only kept if they contain at
    least one pixel above ``high_snr``. That combination keeps faint filaments intact
    without admitting the whole noise field.

    Detections are returned in descending order of pixel count, which is deterministic
    for a given input (ADR-0012).
    """
    if high_snr < low_snr:
        msg = f"high_snr ({high_snr}) must not be below low_snr ({low_snr})"
        raise ValueError(msg)

    response = ridge_response(image, noise, scales)
    if exclude is not None:
        response = np.where(exclude, 0.0, response).astype(np.float32)

    weak = response > low_snr
    strong = response > high_snr
    labels: NDArray[np.intp]
    n: int
    labels, n = label(weak, connectivity=2, return_num=True)
    if n == 0:
        return []

    # Keep only components seeded by at least one strong pixel.
    seeded = np.zeros(n + 1, dtype=bool)
    seeded[labels[strong]] = True
    seeded[0] = False

    detections: list[RidgeDetection] = []
    for index in np.flatnonzero(seeded):
        ys, xs = np.nonzero(labels == index)
        if ys.size < min_pixels:
            continue
        detections.append(
            RidgeDetection(
                ys=ys,
                xs=xs,
                peak_snr=float(response[ys, xs].max()),
                n_pixels=int(ys.size),
            )
        )
    detections.sort(key=lambda d: (-d.n_pixels, int(d.ys[0]), int(d.xs[0])))
    return detections
