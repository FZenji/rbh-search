"""Artifact rejection, checked against the real candidates that motivated it.

The thresholds are not invented: every one comes from the first scan of new sky, where one
bright elliptical galaxy produced 76 of 84 candidates. The tests use those measurements, so
a change that loosens a threshold has to explain itself against real data.

The failure to guard hardest against is over-rejection. Carving out real wakes would put an
unmeasurable hole in the selection function, which is the one thing ADR-0009 cannot tolerate.
"""

from __future__ import annotations

import math

import pytest

from rbh.artifacts import (
    IMPLAUSIBLE_AXIS_RATIO,
    IMPLAUSIBLE_LENGTH_ARCSEC,
    IMPLAUSIBLE_PEAK_SNR,
    ArtifactScore,
    concentration,
    count_sharing_angle,
    dominant_angle,
    field_is_contaminated,
    filter_field,
    score,
)
from rbh.reference import RBH1_LITMUS

#: The real object as this pipeline recovers it. Nothing here may reject it.
RBH1_CANDIDATE: dict[str, object] = {
    "ra_deg": 40.44013,
    "dec_deg": -8.35001,
    "length_arcsec": 5.50,
    "axis_ratio": 21.4,
    "position_angle_deg": 148.3,
    "peak_snr": 20.0,
}

#: The worst offender from the first scan: a saturation bleed in hst_10003_01.
BLEED_TRAIL: dict[str, object] = {
    "ra_deg": 192.16087,
    "dec_deg": -5.79994,
    "length_arcsec": 16.56,
    "axis_ratio": 78.4,
    "position_angle_deg": 108.0,
    "peak_snr": 85.9,
}


def test_the_real_object_is_never_rejected() -> None:
    """The single most important property. Rejecting RBH-1 would invalidate everything."""
    verdict = score(RBH1_CANDIDATE, [148.3])
    assert not verdict.is_artifact


def test_the_real_object_survives_even_in_a_contaminated_field() -> None:
    """A wake that happens to lie along the spike direction must still survive.

    Alignment alone cannot reject, precisely because a real wake can share an angle with an
    instrumental one by chance - and a rejection on that basis would be invisible in the
    selection function.
    """
    spike_angles = [148.0, 148.5, 147.8, 148.9, 149.1]
    verdict = score(RBH1_CANDIDATE, [*spike_angles, 148.3])
    assert verdict.aligned_with_others, "it does share the angle"
    assert not verdict.is_artifact, "but that alone must not reject it"


def test_the_litmus_values_are_inside_the_thresholds() -> None:
    """Tie the thresholds to the recorded recovery, not to a remembered number.

    If the detector legitimately improves and RBH-1 comes back longer or thinner, this fails
    and the thresholds get revisited deliberately rather than silently clipping the one object
    the whole pipeline is calibrated on.
    """
    assert RBH1_LITMUS.length_arcsec < IMPLAUSIBLE_LENGTH_ARCSEC
    assert RBH1_LITMUS.length_arcsec / RBH1_LITMUS.width_arcsec < IMPLAUSIBLE_AXIS_RATIO


def test_an_extreme_axis_ratio_is_rejected() -> None:
    """Axis ratio 109 at 39 arcsec was the best-scoring feature in the contaminated field."""
    spike = {**BLEED_TRAIL, "axis_ratio": 108.9, "length_arcsec": 39.01, "peak_snr": 202.3}
    assert score(spike, [102.0]).is_artifact


def test_extreme_brightness_is_rejected() -> None:
    bright = {**RBH1_CANDIDATE, "peak_snr": IMPLAUSIBLE_PEAK_SNR + 50}
    assert score(bright, [148.3]).is_artifact


def test_angles_are_orientations_not_directions() -> None:
    """179 and 1 degrees describe nearly the same line.

    Treating position angle as a direction would put them 178 degrees apart and miss the
    alignment this module exists to find.
    """
    assert count_sharing_angle(1.0, [179.0, 178.0, 2.0, 3.0]) == 4
    assert count_sharing_angle(1.0, [90.0, 91.0]) == 0


def test_a_dominant_angle_is_found_only_when_one_exists() -> None:
    spikes = [102.0, 103.5, 101.0, 104.0, 102.5]
    assert dominant_angle(spikes) is not None
    scattered = [10.0, 50.0, 95.0, 140.0]
    assert dominant_angle(scattered) is None
    assert dominant_angle([]) is None


def test_concentration_matches_the_measured_pile_up() -> None:
    """The first scan's 76 artifacts had a median nearest neighbour of 3.08 arcsec."""
    tight = [(192.1600 + 0.0002 * i, -5.7999) for i in range(10)]
    assert concentration(tight) < 10.0

    spread = [(192.0 + 0.05 * i, -5.8) for i in range(5)]
    assert concentration(spread) > 60.0

    assert math.isnan(concentration([(1.0, 2.0)]))


def test_a_contaminated_field_is_flagged_as_a_field() -> None:
    """The flag is on the product, not the candidate - the right response is to look."""
    pile: list[dict[str, object]] = [
        {
            "ra_deg": 192.1600 + 0.0002 * i,
            "dec_deg": -5.7999,
            "position_angle_deg": 102.0 + 0.4 * i,
            "axis_ratio": 30.0,
            "length_arcsec": 5.0,
            "peak_snr": 30.0,
        }
        for i in range(10)
    ]
    assert field_is_contaminated(pile)


def test_a_clean_field_is_not_flagged() -> None:
    """Over-flagging would send every product to manual inspection and help nobody."""
    scattered: list[dict[str, object]] = [
        {
            "ra_deg": 192.0 + 0.03 * i,
            "dec_deg": -5.8 + 0.02 * i,
            "position_angle_deg": 20.0 * i,
            "axis_ratio": 15.0,
            "length_arcsec": 4.0,
            "peak_snr": 25.0,
        }
        for i in range(5)
    ]
    assert not field_is_contaminated(scattered)


def test_rejections_carry_a_reason() -> None:
    """ADR-0014 retains every raw detection with why it was rejected; this supplies the why."""
    spike = {**BLEED_TRAIL, "axis_ratio": 120.0, "peak_snr": 202.0}
    kept, rejected = filter_field([RBH1_CANDIDATE, spike])
    assert [c["length_arcsec"] for c in kept] == [5.50]
    assert len(rejected) == 1
    reason = rejected[0]["reject_reason"]
    assert isinstance(reason, str)
    assert "shape" in reason
    assert "brighter" in reason


def test_kept_candidates_carry_their_suspicion() -> None:
    """Scored, not cut (ADR-0008): something can survive and still be ranked down."""
    borderline = {**RBH1_CANDIDATE, "position_angle_deg": 102.0}
    siblings = [{**BLEED_TRAIL, "axis_ratio": 20.0, "peak_snr": 30.0} for _ in range(5)]
    kept, _ = filter_field([borderline, *siblings])
    assert all("artifact_suspicion" in c for c in kept)
    suspicions: list[int] = []
    for candidate in kept:
        value = candidate["artifact_suspicion"]
        assert isinstance(value, int)
        suspicions.append(value)
    assert any(value > 0 for value in suspicions)


def test_the_score_dataclass_reports_each_signature_separately() -> None:
    """A wrong rejection has to be diagnosable, not mysterious."""
    verdict = ArtifactScore(
        aligned_with_others=True,
        implausible_shape=True,
        implausible_brightness=False,
        shared_angle_count=18,
    )
    assert verdict.is_artifact
    assert verdict.suspicion == 2
    assert verdict.shared_angle_count == 18


@pytest.mark.parametrize("ratio", [10.0, 21.4, 40.0, 59.0])
def test_plausible_wakes_survive_across_the_range(ratio: float) -> None:
    """Everything from a stubby wake to one near the published intrinsic limit."""
    assert not score({**RBH1_CANDIDATE, "axis_ratio": ratio}, [148.3]).is_artifact
