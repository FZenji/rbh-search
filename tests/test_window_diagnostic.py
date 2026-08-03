"""Which selection-window cut a calibrated synthetic fails, and by how much.

Not a test of behaviour so much as a check that the generator's fitted defaults still land
inside the window the survey actually applies (ADR-0007). Those two are calibrated against
different things - the generator against the transplant's recovery statistics, the window
against what a wake is expected to look like - so nothing guarantees they agree, and a
disagreement is a real finding rather than a broken test.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from conftest import make_tile
from rbh.config import SelectionWindow
from rbh.detect import bright_source_mask, detect_ridges
from rbh.inject import inject_synthetic
from rbh.linking import link_collinear
from rbh.morphology import Morphology, measure
from rbh.synthetic import WakeParameters
from rbh.tile import Tile

PSF = 0.11


def blank(noise_field: np.ndarray) -> Tile:
    """The same two-band noise tile the recovery tests use."""
    return make_tile(
        {"F606W": noise_field, "F814W": (noise_field[::-1] * 1.0).astype(np.float32)},
        zeropoints={"F606W": 26.485, "F814W": 25.933},
    )


def measured(noise_field: np.ndarray, params: WakeParameters) -> Morphology | None:
    tile = blank(noise_field)
    injected, _ = inject_synthetic(
        tile, params, (128, 128), psf_fwhm_arcsec=PSF, rng=np.random.default_rng(0)
    )
    image, noise = injected.detection_image()
    linked = link_collinear(
        detect_ridges(image, noise, exclude=bright_source_mask(image, noise)),
        injected.pixel_scale_arcsec,
    )
    if not linked:
        return None
    best = max(linked, key=lambda d: d.n_pixels)
    return measure(best, image, injected.wcs, injected.pixel_scale_arcsec)


def test_calibrated_defaults_stay_inside_the_selection_window(
    noise_field: np.ndarray,
) -> None:
    """A bright wake at the fitted defaults must survive the window it will be searched with.

    Uses the fitted width. At half that width the same injection fails the *length* cut,
    because ``path_wander_arcsec`` is an absolute deviation and a wander of 0.14 arcsec on a
    0.12 arcsec feature moves it further sideways than it is wide, breaking it up. That is
    a real property of the parameterisation and is asserted separately below.
    """
    params = WakeParameters(length_arcsec=6.0, width_arcsec=0.22, total_mag_ab=17.0)
    morphology = measured(noise_field, params)
    assert morphology is not None

    window = SelectionWindow()
    failures = {
        "length": not (
            window.min_length_arcsec <= morphology.length_arcsec <= window.max_length_arcsec
        ),
        "width": morphology.width_arcsec > window.max_width_arcsec,
        "axis_ratio": morphology.axis_ratio < window.min_axis_ratio,
        "straightness": (morphology.straightness_arcsec > window.max_straightness_residual_arcsec),
    }
    assert not any(failures.values()), (
        f"fails {[k for k, v in failures.items() if v]}; "
        f"length={morphology.length_arcsec:.2f} width={morphology.width_arcsec:.3f} "
        f"axis_ratio={morphology.axis_ratio:.1f} "
        f"straightness={morphology.straightness_arcsec:.3f} "
        f"(window straightness max {window.max_straightness_residual_arcsec})"
    )


def test_bright_fraction_shortens_what_is_recovered(noise_field: np.ndarray) -> None:
    """``length_arcsec`` is the full extent, not the length that comes back.

    Only ``bright_fraction`` of the feature carries flux, so the recovered length is
    inherently shorter - which is the honest way to reproduce the real object being injected
    at 8.10 arcsec and recovered at 5.61. Anything reading ``length_arcsec`` as "the length
    the detector will report" is wrong, and the completeness-versus-length grid in
    particular is indexed by the injected value.
    """
    base = WakeParameters(length_arcsec=6.0, width_arcsec=0.22, total_mag_ab=17.0)
    windowed = measured(noise_field, base)
    full = measured(noise_field, replace(base, bright_fraction=1.0))
    assert windowed is not None
    assert full is not None
    assert windowed.length_arcsec < full.length_arcsec


def test_wander_is_absolute_so_narrow_features_suffer_more(
    noise_field: np.ndarray,
) -> None:
    """A wander comparable to the width breaks a feature up; on a wide one it does not.

    Recorded as a test because it is a limitation of the parameterisation rather than a bug:
    ``path_wander_arcsec`` was fitted at RBH-1's width and does not scale, so a survey
    injecting much narrower wakes would be measuring a harsher selection than intended.
    """
    narrow = WakeParameters(length_arcsec=6.0, width_arcsec=0.12, total_mag_ab=17.0)
    wide = replace(narrow, width_arcsec=0.22)
    a, b = measured(noise_field, narrow), measured(noise_field, wide)
    assert a is not None
    assert b is not None
    assert a.length_arcsec < b.length_arcsec
