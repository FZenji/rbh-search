"""The synthetic generator must be controllable along the axes that matter."""

from __future__ import annotations

import numpy as np
import pytest

from rbh.synthetic import WakeParameters, render_bands, render_wake

SHAPE = (256, 256)
SCALE = 0.05
PSF = 0.11


def render(**kw: object) -> np.ndarray:
    params = WakeParameters(**kw)  # type: ignore[arg-type]
    return render_wake(params, SHAPE, SCALE, psf_fwhm_arcsec=PSF, rng=np.random.default_rng(3))


def test_shape_is_normalised_to_unit_flux() -> None:
    """Photometry and morphology must stay independent, so the shape carries unit flux."""
    assert render(length_arcsec=6.0).sum() == pytest.approx(1.0, rel=1e-5)


def test_clumpiness_does_not_change_total_flux() -> None:
    """Clumpiness redistributes flux along the feature, it does not add or remove any.

    Without this, varying clumpiness in the completeness grid would confound lumpiness
    with brightness and the resulting surface would be uninterpretable.
    """
    smooth = render(length_arcsec=8.0, clumpiness=0.0)
    clumpy = render(length_arcsec=8.0, clumpiness=0.9)
    assert smooth.sum() == pytest.approx(clumpy.sum(), rel=1e-5)


def test_clumpiness_increases_variation_along_the_axis() -> None:
    """A clumpy wake must actually be lumpier, not merely nominally so.

    Rendered horizontally (position angle 90) so that collapsing along image rows really
    is the along-axis ridge profile. Measuring a diagonal feature this way mixes the
    transverse profile in and washes the effect out.
    """
    profiles = []
    for clumpiness in (0.0, 0.5, 0.95):
        image = render(
            length_arcsec=8.0,
            clumpiness=clumpiness,
            n_clumps=6,
            position_angle_deg=90.0,
            terminal_knot_fraction=0.0,
        )
        ridge = image.max(axis=0)
        lit = ridge[ridge > 0.02 * ridge.max()]
        profiles.append(float(lit.std() / lit.mean()))
    assert profiles[0] < profiles[1] < profiles[2], profiles


@pytest.mark.parametrize("length", [3.0, 6.0, 12.0])
def test_length_controls_extent(length: float) -> None:
    image = render(length_arcsec=length, clumpiness=0.0, terminal_knot_fraction=0.0)
    lit = image > 0.02 * image.max()
    ys, xs = np.nonzero(lit)
    points = np.column_stack([xs, ys]).astype(float)
    centred = points - points.mean(axis=0)
    _, _, vt = np.linalg.svd(centred, full_matrices=False)
    extent = float(np.ptp(centred @ vt[0])) * SCALE
    assert extent == pytest.approx(length, rel=0.25)


def test_wider_features_are_wider() -> None:
    narrow = render(length_arcsec=8.0, width_arcsec=0.08, clumpiness=0.0)
    wide = render(length_arcsec=8.0, width_arcsec=0.40, clumpiness=0.0)
    assert (wide > 0.1 * wide.max()).sum() > (narrow > 0.1 * narrow.max()).sum()


def test_curvature_bends_the_spine() -> None:
    straight = render(length_arcsec=8.0, clumpiness=0.0, curvature_arcsec=0.0)
    bent = render(length_arcsec=8.0, clumpiness=0.0, curvature_arcsec=0.6)
    assert not np.allclose(straight, bent)


def test_terminal_knot_adds_a_bright_end() -> None:
    without = render(length_arcsec=8.0, clumpiness=0.0, terminal_knot_fraction=0.0)
    with_knot = render(length_arcsec=8.0, clumpiness=0.0, terminal_knot_fraction=0.3)
    assert with_knot.max() > 1.5 * without.max()


def test_bands_hit_the_requested_magnitudes() -> None:
    zeropoints = {"F606W": 26.485, "F814W": 25.933}
    params = WakeParameters(total_mag_ab=23.8, colour_ab=0.7, colour_gradient=0.0)
    bands = render_bands(
        params, SHAPE, SCALE, zeropoints, psf_fwhm_arcsec=PSF, rng=np.random.default_rng(1)
    )
    blue = 26.485 - 2.5 * np.log10(bands["F606W"].sum())
    red = 25.933 - 2.5 * np.log10(bands["F814W"].sum())
    assert blue == pytest.approx(23.8, abs=0.01)
    assert blue - red == pytest.approx(0.7, abs=0.01)


def test_colour_gradient_leaves_the_integrated_colour_alone() -> None:
    """The gradient tilts colour along the axis without shifting the overall colour."""
    zeropoints = {"F606W": 26.485, "F814W": 25.933}
    flat = render_bands(
        WakeParameters(colour_ab=0.7, colour_gradient=0.0),
        SHAPE,
        SCALE,
        zeropoints,
        psf_fwhm_arcsec=PSF,
        rng=np.random.default_rng(1),
    )
    tilted = render_bands(
        WakeParameters(colour_ab=0.7, colour_gradient=-0.05),
        SHAPE,
        SCALE,
        zeropoints,
        psf_fwhm_arcsec=PSF,
        rng=np.random.default_rng(1),
    )
    for name in zeropoints:
        assert flat[name].sum() == pytest.approx(tilted[name].sum(), rel=0.02)
    assert not np.allclose(flat["F814W"], tilted["F814W"])


def test_rendering_is_reproducible_for_a_given_seed() -> None:
    a = render_wake(
        WakeParameters(), SHAPE, SCALE, psf_fwhm_arcsec=PSF, rng=np.random.default_rng(11)
    )
    b = render_wake(
        WakeParameters(), SHAPE, SCALE, psf_fwhm_arcsec=PSF, rng=np.random.default_rng(11)
    )
    assert np.array_equal(a, b)


def test_invalid_parameters_are_rejected() -> None:
    with pytest.raises(ValueError, match="clumpiness"):
        WakeParameters(clumpiness=1.5)
    with pytest.raises(ValueError, match="positive"):
        WakeParameters(length_arcsec=-1.0)
    with pytest.raises(ValueError, match="n_clumps"):
        WakeParameters(n_clumps=0)
