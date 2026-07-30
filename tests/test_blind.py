"""The blind synthetic-versus-real test: construction and scoring."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from rbh.blind import PARAMETRIC, TRANSPLANT, BlindStamp, make_blind_set, score, shared_limits
from rbh.studies import reference_template
from rbh.tileio import read_tile

FIXTURE = Path(__file__).parent / "data" / "rbh1_acs_f606w_f814w.fits"

pytestmark = pytest.mark.slow


def stamp(kind: str, index: int = 0) -> BlindStamp:
    return BlindStamp(
        index=index,
        kind=kind,
        tile_name="t",
        magnitude=23.8,
        pixels=np.zeros((4, 4), dtype=np.float32),
    )


def test_scoring_a_perfect_run() -> None:
    stamps = [stamp(TRANSPLANT, 0), stamp(PARAMETRIC, 1)]
    result = score(stamps, [TRANSPLANT, PARAMETRIC])
    assert result["accuracy"] == pytest.approx(1.0)
    assert result["sigma_above_chance"] > 0


def test_scoring_a_chance_run_is_the_good_outcome() -> None:
    """50% accuracy means the synthetics are indistinguishable, which validates them."""
    stamps = [stamp(TRANSPLANT, 0), stamp(PARAMETRIC, 1)]
    result = score(stamps, [TRANSPLANT, TRANSPLANT])
    assert result["accuracy"] == pytest.approx(0.5)
    assert result["sigma_above_chance"] == pytest.approx(0.0)


def test_scoring_rejects_a_mismatched_answer_count() -> None:
    with pytest.raises(ValueError, match="expected 2 answers"):
        score([stamp(TRANSPLANT, 0), stamp(PARAMETRIC, 1)], [TRANSPLANT])


def test_significance_scales_with_sample_size() -> None:
    """Eighteen of twenty correct is convincing; nine of ten less so, at the same accuracy."""
    small = score([stamp(TRANSPLANT, i) for i in range(10)], [TRANSPLANT] * 9 + [PARAMETRIC])
    large = score([stamp(TRANSPLANT, i) for i in range(20)], [TRANSPLANT] * 18 + [PARAMETRIC] * 2)
    assert small["accuracy"] == pytest.approx(large["accuracy"])
    assert large["sigma_above_chance"] > small["sigma_above_chance"]


def test_set_is_balanced_between_the_classes() -> None:
    tile = read_tile(FIXTURE)
    stamps = make_blind_set(
        [("fixture", tile)],
        reference_template(FIXTURE),
        rng=np.random.default_rng(7),
        count=10,
    )
    kinds = [s.kind for s in stamps]
    assert kinds.count(TRANSPLANT) == kinds.count(PARAMETRIC)


def test_magnitudes_are_matched_across_the_classes() -> None:
    """If one class were systematically fainter, brightness alone would give the game away."""
    tile = read_tile(FIXTURE)
    stamps = make_blind_set(
        [("fixture", tile)],
        reference_template(FIXTURE),
        rng=np.random.default_rng(11),
        count=12,
        magnitudes=(23.4, 23.8),
    )
    real = sorted(s.magnitude for s in stamps if s.is_real)
    fake = sorted(s.magnitude for s in stamps if not s.is_real)
    assert real == fake


def test_stamps_are_shuffled_and_reindexed() -> None:
    tile = read_tile(FIXTURE)
    stamps = make_blind_set(
        [("fixture", tile)],
        reference_template(FIXTURE),
        rng=np.random.default_rng(3),
        count=8,
    )
    assert [s.index for s in stamps] == list(range(len(stamps)))
    # A shuffle that left the classes strictly alternating would be no shuffle at all.
    kinds = [s.kind for s in stamps]
    assert kinds != [TRANSPLANT if i % 2 == 0 else PARAMETRIC for i in range(len(kinds))]


def test_shared_limits_span_every_stamp() -> None:
    stamps = [
        BlindStamp(0, TRANSPLANT, "t", 23.8, np.full((4, 4), -5.0, dtype=np.float32)),
        BlindStamp(1, PARAMETRIC, "t", 23.8, np.full((4, 4), 5.0, dtype=np.float32)),
    ]
    low, high = shared_limits(stamps, percentiles=(0.0, 100.0))
    assert low == pytest.approx(-5.0)
    assert high == pytest.approx(5.0)
