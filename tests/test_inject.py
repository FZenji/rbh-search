"""Template extraction, transplanting, and injection placement."""

from __future__ import annotations

import numpy as np
import pytest

from conftest import PIXEL_SCALE, SHAPE, draw_line, make_tile
from rbh.inject import free_positions, inject_synthetic, inject_template
from rbh.pipeline import detect_in_tile
from rbh.synthetic import WakeParameters
from rbh.template import extract_template, transform_template
from rbh.tile import Tile


def sourced_tile(noise_field: np.ndarray, amplitude: float = 6.0) -> Tile:
    line = draw_line(
        SHAPE, length_pixels=120.0, width_pixels=3.0, angle_deg=30.0, amplitude=amplitude
    )
    return make_tile(
        {
            "F606W": (noise_field + line).astype(np.float32),
            "F814W": (noise_field[::-1] + 0.7 * line).astype(np.float32),
        }
    )


def test_template_keeps_only_source_pixels(noise_field: np.ndarray) -> None:
    """Everything outside the footprint must be exactly zero, or we transplant noise."""
    tile = sourced_tile(noise_field)
    detection = max(detect_in_tile(tile), key=lambda d: d.n_pixels)
    template = extract_template(tile, detection, name="synthetic")
    for stamp in template.stamps.values():
        assert np.all(stamp[~template.footprint] == 0.0)
    assert template.source_pixels > 0
    assert template.source_pixels == int(template.footprint.sum())


def test_template_records_the_noise_it_carries(noise_field: np.ndarray) -> None:
    tile = sourced_tile(noise_field)
    detection = max(detect_in_tile(tile), key=lambda d: d.n_pixels)
    template = extract_template(tile, detection, name="synthetic")
    assert set(template.noise_rms) == set(tile.filter_names)
    assert all(v > 0 for v in template.noise_rms.values())


def test_template_masks_unconnected_neighbours(noise_field: np.ndarray) -> None:
    """A bright blob beside the source must not travel with it."""
    line = draw_line(SHAPE, length_pixels=120.0, width_pixels=3.0, angle_deg=0.0, amplitude=6.0)
    contaminated = noise_field + line
    contaminated[60:70, 60:70] += 60.0  # a bright neighbour, well away from the line
    tile = make_tile({"F606W": contaminated.astype(np.float32)})
    detection = max(detect_in_tile(tile), key=lambda d: d.n_pixels)
    template = extract_template(tile, detection, name="synthetic", pad_arcsec=4.0)
    assert template.stamps["F606W"].max() < 30.0


def test_quadrant_rotation_preserves_flux(noise_field: np.ndarray) -> None:
    tile = sourced_tile(noise_field)
    detection = max(detect_in_tile(tile), key=lambda d: d.n_pixels)
    template = extract_template(tile, detection, name="synthetic")
    for turns in (1, 2, 3):
        rotated = transform_template(template, quadrant_rotations=turns)
        assert rotated.total_flux("F606W") == pytest.approx(template.total_flux("F606W"), rel=1e-6)


def test_transplant_adds_flux_without_mutating_the_source(noise_field: np.ndarray) -> None:
    tile = sourced_tile(noise_field)
    detection = max(detect_in_tile(tile), key=lambda d: d.n_pixels)
    template = extract_template(tile, detection, name="synthetic")
    before = tile.band("F606W").science.copy()

    injected, record = inject_template(tile, template, (60, 190), rng=np.random.default_rng(0))
    assert np.array_equal(tile.band("F606W").science, before)
    assert injected.band("F606W").science.sum() > before.sum()
    assert record.kind == "transplant"
    assert injected.provenance["injected"] == "true"


def test_flux_scaling_scales_the_added_signal(noise_field: np.ndarray) -> None:
    tile = sourced_tile(noise_field)
    detection = max(detect_in_tile(tile), key=lambda d: d.n_pixels)
    template = extract_template(tile, detection, name="synthetic")
    base = tile.band("F606W").science.sum()

    full, _ = inject_template(
        tile, template, (60, 190), flux_scale=1.0, rng=np.random.default_rng(0)
    )
    half, _ = inject_template(
        tile,
        template,
        (60, 190),
        flux_scale=0.5,
        rng=np.random.default_rng(0),
        compensate_noise=False,
    )
    added_full = full.band("F606W").science.sum() - base
    added_half = half.band("F606W").science.sum() - base
    assert added_half == pytest.approx(0.5 * added_full, rel=1e-4)


def test_noise_compensation_keeps_carried_noise_independent_of_flux_scale(
    noise_field: np.ndarray,
) -> None:
    """The whole point of the (1 - f^2) recipe: a constant penalty, not a sloped one.

    Without it, faint injections carry proportionally less of the template's noise than
    bright ones and the completeness curve acquires a spurious tilt.
    """
    tile = sourced_tile(noise_field)
    detection = max(detect_in_tile(tile), key=lambda d: d.n_pixels)
    template = extract_template(tile, detection, name="synthetic")
    sigma = template.noise_rms["F606W"]

    scatter = {}
    for scale in (0.25, 0.5, 1.0):
        # Inject a *zero-signal* template so only the noise terms remain.
        blank = type(template)(
            name=template.name,
            stamps={k: np.zeros_like(v) for k, v in template.stamps.items()},
            footprint=template.footprint,
            noise_rms=template.noise_rms,
            pixel_scale_arcsec=template.pixel_scale_arcsec,
            source_pixels=template.source_pixels,
        )
        injected, _ = inject_template(
            tile, blank, (60, 190), flux_scale=scale, rng=np.random.default_rng(5)
        )
        difference = injected.band("F606W").science - tile.band("F606W").science
        touched = difference != 0
        scatter[scale] = float(difference[touched].std()) if touched.any() else 0.0

    # Carried noise should be sigma * sqrt(1 - f^2) from the added term alone.
    for scale, value in scatter.items():
        assert value == pytest.approx(sigma * np.sqrt(1 - scale**2), rel=0.25)


def test_injection_outside_the_tile_is_rejected(noise_field: np.ndarray) -> None:
    tile = sourced_tile(noise_field)
    detection = max(detect_in_tile(tile), key=lambda d: d.n_pixels)
    template = extract_template(tile, detection, name="synthetic")
    with pytest.raises(ValueError, match="outside the tile"):
        inject_template(tile, template, (-500, -500), rng=np.random.default_rng(0))


def test_synthetic_injection_adds_the_expected_magnitude(noise_field: np.ndarray) -> None:
    tile = make_tile(
        {"F606W": noise_field, "F814W": noise_field}, zeropoints={"F606W": 26.0, "F814W": 25.5}
    )
    params = WakeParameters(total_mag_ab=20.0, colour_ab=0.5, colour_gradient=0.0)
    injected, record = inject_synthetic(
        tile, params, (128, 128), psf_fwhm_arcsec=0.11, rng=np.random.default_rng(2)
    )
    added = injected.band("F606W").science.sum() - tile.band("F606W").science.sum()
    magnitude = 26.0 - 2.5 * np.log10(added)
    assert magnitude == pytest.approx(20.0, abs=0.05)
    assert record.kind == "parametric"
    assert record.clumpiness == params.clumpiness


def test_free_positions_respects_the_edge_margin(noise_field: np.ndarray) -> None:
    tile = make_tile({"F606W": noise_field})
    positions = free_positions(
        tile, feature_length_arcsec=6.0, rng=np.random.default_rng(0), count=25
    )
    margin = 6.0 / 2 / PIXEL_SCALE
    assert positions
    for y, x in positions:
        assert margin <= y <= SHAPE[0] - margin
        assert margin <= x <= SHAPE[1] - margin


def test_free_positions_honours_an_exclusion_mask(noise_field: np.ndarray) -> None:
    tile = make_tile({"F606W": noise_field})
    exclude = np.zeros(SHAPE, dtype=bool)
    exclude[:, :120] = True
    positions = free_positions(
        tile,
        feature_length_arcsec=4.0,
        rng=np.random.default_rng(0),
        count=15,
        exclude=exclude,
        centre_clearance_arcsec=0.5,
    )
    assert positions
    assert all(x >= 120 for _, x in positions)


def test_a_feature_too_long_for_the_tile_is_rejected(noise_field: np.ndarray) -> None:
    tile = make_tile({"F606W": noise_field})
    with pytest.raises(ValueError, match="does not fit"):
        free_positions(tile, feature_length_arcsec=40.0, rng=np.random.default_rng(0), count=1)


def test_transplanting_a_rotated_template_still_recovers_a_linear_feature(
    noise_field: np.ndarray,
) -> None:
    """A quadrant rotation must not damage the source: it should still be found."""
    tile = sourced_tile(noise_field)
    detection = max(detect_in_tile(tile), key=lambda d: d.n_pixels)
    template = transform_template(
        extract_template(tile, detection, name="synthetic"), quadrant_rotations=1
    )
    blank = make_tile({"F606W": noise_field.copy(), "F814W": noise_field[::-1].copy()})
    injected, _ = inject_template(blank, template, (128, 128), rng=np.random.default_rng(0))
    found = detect_in_tile(injected)
    assert found
    assert max(d.n_pixels for d in found) > 100
