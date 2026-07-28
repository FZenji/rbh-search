"""Tests for run configuration and its fingerprint."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from rbh.config import SelectionWindow, Settings
from rbh.reference import RBH1


def test_defaults_bracket_rbh1() -> None:
    window = SelectionWindow()
    assert window.min_length_arcsec < RBH1.length_arcsec < window.max_length_arcsec
    assert RBH1.width_arcsec < window.max_width_arcsec


def test_fingerprint_is_stable_across_instances() -> None:
    assert Settings().fingerprint() == Settings().fingerprint()


def test_fingerprint_changes_with_thresholds() -> None:
    baseline = Settings()
    tightened = Settings(selection=SelectionWindow(min_ridge_snr=7.0))
    assert baseline.fingerprint() != tightened.fingerprint()


def test_settings_are_frozen() -> None:
    settings = Settings()
    with pytest.raises(ValidationError):
        settings.tier = "B"


def test_unknown_settings_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(nonsense=True)  # type: ignore[call-arg]


def test_env_prefix_is_honoured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RBH_TIER", "B")
    assert Settings().tier == "B"


def test_nested_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RBH_SELECTION__MIN_RIDGE_SNR", "9.5")
    assert Settings().selection.min_ridge_snr == 9.5
