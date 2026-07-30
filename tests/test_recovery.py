"""The recovery driver must distinguish detection from reaching the catalogue."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pytest
from numpy.random import Generator

from conftest import SHAPE, make_tile
from rbh.config import SelectionWindow
from rbh.inject import Injection, inject_synthetic
from rbh.recovery import (
    MIN_MATCH_RADIUS_ARCSEC,
    Summary,
    match_radius_for,
    run_trial,
    summarise,
)
from rbh.synthetic import WakeParameters
from rbh.tile import Tile

PSF = 0.11


def blank(noise_field: np.ndarray) -> Tile:
    return make_tile(
        {"F606W": noise_field, "F814W": (noise_field[::-1] * 1.0).astype(np.float32)},
        zeropoints={"F606W": 26.485, "F814W": 25.933},
    )


Injected = tuple[Tile, Injection]


def injector(params: WakeParameters) -> Callable[[Tile, tuple[int, int], Generator], Injected]:
    def inject(tile: Tile, centre: tuple[int, int], rng: Generator) -> Injected:
        return inject_synthetic(tile, params, centre, psf_fwhm_arcsec=PSF, rng=rng)

    return inject


def test_a_bright_wake_is_recovered_and_passes_the_window(noise_field: np.ndarray) -> None:
    params = WakeParameters(length_arcsec=6.0, width_arcsec=0.12, total_mag_ab=17.0)
    trial = run_trial(
        blank(noise_field),
        injector(params),
        (128, 128),
        window=SelectionWindow(),
        rng=np.random.default_rng(0),
    )
    assert trial.detected
    assert trial.passes_window
    assert trial.measured is not None


def test_a_very_faint_wake_is_missed(noise_field: np.ndarray) -> None:
    params = WakeParameters(length_arcsec=6.0, width_arcsec=0.12, total_mag_ab=30.0)
    trial = run_trial(
        blank(noise_field),
        injector(params),
        (128, 128),
        window=SelectionWindow(),
        rng=np.random.default_rng(0),
    )
    assert not trial.detected
    assert not trial.passes_window
    assert trial.measured is None


def test_detection_and_window_pass_are_separate(noise_field: np.ndarray) -> None:
    """A source can be detected and still never reach the catalogue.

    Conflating the two would overstate completeness, because the selection window is what
    actually decides whether a candidate exists. Tested by tightening the window rather
    than by shrinking the source: a feature short enough to fail the length cut naturally
    is also compact enough to be swallowed by the bright-source mask, which would test the
    wrong thing.
    """
    params = WakeParameters(length_arcsec=6.0, width_arcsec=0.12, total_mag_ab=19.0)
    common = {
        "window": SelectionWindow(),
        "rng": np.random.default_rng(0),
    }
    permissive = run_trial(blank(noise_field), injector(params), (128, 128), **common)  # type: ignore[arg-type]
    assert permissive.detected
    assert permissive.passes_window

    strict = run_trial(
        blank(noise_field),
        injector(params),
        (128, 128),
        window=SelectionWindow(min_length_arcsec=20.0),
        rng=np.random.default_rng(0),
    )
    assert strict.detected
    assert not strict.passes_window


def test_brightness_ordering_of_completeness(noise_field: np.ndarray) -> None:
    """Fainter injections must not be recovered more often than brighter ones."""
    outcomes = []
    for magnitude in (17.0, 22.0, 26.0, 30.0):
        trials = [
            run_trial(
                blank(noise_field),
                injector(
                    WakeParameters(length_arcsec=6.0, width_arcsec=0.12, total_mag_ab=magnitude)
                ),
                (128, 128),
                window=SelectionWindow(),
                rng=np.random.default_rng(seed),
            )
            for seed in range(3)
        ]
        outcomes.append(summarise(trials, f"m={magnitude}").completeness)
    assert outcomes == sorted(outcomes, reverse=True)


def test_a_wake_injected_far_away_is_not_matched(noise_field: np.ndarray) -> None:
    """Truth matching must be positional, or any detection anywhere would count."""
    params = WakeParameters(length_arcsec=6.0, width_arcsec=0.12, total_mag_ab=17.0)
    tile = blank(noise_field)

    def offset_injector(t: Tile, _centre: tuple[int, int], rng: Generator) -> Injected:
        return inject_synthetic(t, params, (60, 60), psf_fwhm_arcsec=PSF, rng=rng)

    trial = run_trial(
        tile,
        offset_injector,
        (200, 200),  # truth is claimed here, but the source went to (60, 60)
        window=SelectionWindow(),
        rng=np.random.default_rng(0),
        match_radius_arcsec=2.0,
    )
    assert not trial.detected


def test_match_radius_scales_with_injected_length() -> None:
    """A fragment's centroid can sit half a feature-length from the injection centre.

    Regression test for a real defect: with a fixed 4 arcsec radius, 16 arcsec features that
    fragmented were scored as misses despite being detected, and completeness at magnitude
    23.8 read 19% instead of 69%.
    """
    assert match_radius_for(4.0) == pytest.approx(MIN_MATCH_RADIUS_ARCSEC)
    assert match_radius_for(16.0) == pytest.approx(10.0)
    assert match_radius_for(16.0) > match_radius_for(8.0) > match_radius_for(2.0)


def test_match_radius_falls_back_when_length_is_unknown() -> None:
    assert match_radius_for(float("nan")) == pytest.approx(MIN_MATCH_RADIUS_ARCSEC)
    assert match_radius_for(0.0) == pytest.approx(MIN_MATCH_RADIUS_ARCSEC)


def test_a_long_feature_is_matched_without_an_explicit_radius(noise_field: np.ndarray) -> None:
    """The default must be derived, not left at the old fixed value."""
    params = WakeParameters(length_arcsec=10.0, width_arcsec=0.22, total_mag_ab=18.0)
    trial = run_trial(
        blank(noise_field),
        injector(params),
        (128, 128),
        window=SelectionWindow(),
        rng=np.random.default_rng(0),
    )
    assert trial.detected
    assert trial.injection.length_arcsec == pytest.approx(10.0)


def test_summary_arithmetic() -> None:
    summary = Summary(
        n_trials=10,
        detected=8,
        passed_window=6,
        fragmented=4,
        median_length_arcsec=5.0,
        median_width_arcsec=0.25,
        median_axis_ratio=20.0,
    )
    assert summary.detection_rate == pytest.approx(0.8)
    assert summary.completeness == pytest.approx(0.6)
    assert summary.fragmentation_rate == pytest.approx(0.5)


def test_summary_of_no_trials_is_zero_not_an_error() -> None:
    summary = summarise([])
    assert summary.n_trials == 0
    assert summary.completeness == 0.0
    assert summary.detection_rate == 0.0
    assert np.isnan(summary.median_length_arcsec)


def test_trials_are_reproducible(noise_field: np.ndarray) -> None:
    params = WakeParameters(length_arcsec=6.0, width_arcsec=0.12, total_mag_ab=24.5)
    results = [
        run_trial(
            blank(noise_field),
            injector(params),
            (128, 128),
            window=SelectionWindow(),
            rng=np.random.default_rng(99),
        )
        for _ in range(2)
    ]
    assert results[0].detected == results[1].detected
    assert results[0].n_fragments == results[1].n_fragments
    if results[0].measured and results[1].measured:
        assert results[0].measured.length_arcsec == pytest.approx(results[1].measured.length_arcsec)


def test_shape_of_the_blank_tile_is_as_expected(noise_field: np.ndarray) -> None:
    assert blank(noise_field).shape == SHAPE
