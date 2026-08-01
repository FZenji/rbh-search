"""The pre-flight must detect a tell it is given, and not invent one that is absent.

Both halves matter. A check that never fires is decoration; a check that always fires
trains its reader to skip it, which is how the first version of the calibration pinning
warning failed.
"""

from __future__ import annotations

import numpy as np
import pytest

from conftest import SHAPE, draw_line
from rbh.blind import (
    PREFLIGHT_AUC_MARGIN,
    BlindStamp,
    preflight,
    separating_statistics,
    stamp_statistics,
)

PARAMETRIC = "parametric"
TRANSPLANT = "transplant"


def make_stamp(index: int, kind: str, pixels: np.ndarray) -> BlindStamp:
    return BlindStamp(
        index=index,
        kind=kind,
        tile_name="test",
        magnitude=23.8,
        pixels=np.asarray(pixels, dtype=np.float32),
    )


def line(width: float, seed: int, amplitude: float = 10.0) -> np.ndarray:
    """A straight line with a little noise, so no two stamps are identical."""
    rng = np.random.default_rng(seed)
    image = draw_line(
        SHAPE, length_pixels=140.0, width_pixels=width, angle_deg=25.0, amplitude=amplitude
    )
    return image + rng.normal(0.0, 0.25, size=image.shape)


def test_statistics_are_measurable_on_a_plain_line() -> None:
    stats = stamp_statistics(np.asarray(line(4.0, seed=0), dtype=np.float32))
    assert np.isfinite(stats["width_variation"])
    assert np.isfinite(stats["head_contrast"])


def test_a_blank_stamp_reports_nan_rather_than_a_number() -> None:
    """No feature means no measurement, which must not be dressed up as one."""
    blank = np.zeros(SHAPE, dtype=np.float32)
    assert all(np.isnan(v) for v in stamp_statistics(blank).values())


def test_identical_classes_do_not_separate() -> None:
    """The null case: both classes drawn the same way must sit near an AUC of 0.5."""
    stamps = [
        make_stamp(i, TRANSPLANT if i % 2 == 0 else PARAMETRIC, line(4.0, seed=i))
        for i in range(20)
    ]
    assert separating_statistics(preflight(stamps)) == ()


def test_a_planted_width_tell_is_caught() -> None:
    """One class visibly narrower than the other must be reported, not missed.

    This is the round 2 situation in miniature: every stamp is a plausible feature and the
    difference is only in how the width behaves, which is precisely the cue a person used.
    """
    stamps = []
    for i in range(20):
        real = i % 2 == 0
        pixels = line(6.0 if real else 2.5, seed=i)
        stamps.append(make_stamp(i, TRANSPLANT if real else PARAMETRIC, pixels))

    auc = preflight(stamps)
    assert separating_statistics(auc) != ()


def test_margin_is_the_only_threshold() -> None:
    """separating_statistics must key off the margin constant, not a second hidden rule."""
    assert separating_statistics({"a": 0.5 + PREFLIGHT_AUC_MARGIN + 0.01}) == ("a",)
    assert separating_statistics({"a": 0.5 - PREFLIGHT_AUC_MARGIN - 0.01}) == ("a",)
    assert separating_statistics({"a": 0.5 + PREFLIGHT_AUC_MARGIN - 0.01}) == ()


def test_nan_statistics_do_not_count_as_separation() -> None:
    assert separating_statistics({"a": float("nan")}) == ()


@pytest.mark.parametrize("n_real", [0, 20])
def test_a_single_class_yields_no_auc(n_real: int) -> None:
    """With nothing to compare against, the answer is NaN rather than a misleading 1.0."""
    kinds = [TRANSPLANT] * n_real + [PARAMETRIC] * (20 - n_real)
    stamps = [make_stamp(i, k, line(4.0, seed=i)) for i, k in enumerate(kinds)]
    assert all(np.isnan(v) for v in preflight(stamps).values())
