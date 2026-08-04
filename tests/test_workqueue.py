"""The work queue must survive being killed and still produce the same answer.

Phase 3's gate is "restartable from an arbitrary kill, with bit-identical output on re-run",
so these tests kill sweeps rather than assert that the code looks correct. ADR-0020.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from rbh.workqueue import (
    OUTPUT_SUFFIX,
    TEMP_PREFIX,
    WorkUnit,
    commit,
    committed_outputs,
    merge,
    pending,
    run_sweep,
    sweep_partial_files,
)


def make_units(count: int, *, fingerprint: str = "cfg1", version: str = "0.1.0") -> list[WorkUnit]:
    return [
        WorkUnit(
            tile_id=f"tile_{i:03d}",
            inputs=(f"s3://bucket/tile_{i:03d}_a.fits", f"s3://bucket/tile_{i:03d}_b.fits"),
            config_fingerprint=fingerprint,
            code_version=version,
        )
        for i in range(count)
    ]


def process(unit: WorkUnit) -> dict[str, object]:
    return {"tile_id": unit.tile_id, "unit_id": unit.unit_id(), "detections": len(unit.inputs)}


class KilledError(RuntimeError):
    """Stands in for a spot instance going away mid-sweep."""


def test_unit_id_is_stable_across_processes() -> None:
    """Content addressing must not depend on dict order or hash randomisation."""
    a = WorkUnit("t", ("b", "a"), "cfg", "1.0")
    b = WorkUnit("t", ("a", "b"), "cfg", "1.0")
    assert a.unit_id() == b.unit_id(), "input order must not change identity"
    assert len(a.unit_id()) == 32


def test_changing_any_input_changes_the_identity() -> None:
    """Resume and invalidate are the same mechanism, which only works if this holds.

    A changed threshold must not silently reuse results computed under the old one, and a
    re-reduced archive product must not be mistaken for the one already processed.
    """
    base = make_units(1)[0]
    variants = {
        "different product": replace(base, inputs=("s3://bucket/other.fits",)),
        "different config": replace(base, config_fingerprint="cfg2"),
        "different code": replace(base, code_version="0.2.0"),
        "different tile": replace(base, tile_id="tile_999"),
    }
    for label, variant in variants.items():
        assert variant.unit_id() != base.unit_id(), f"{label} must not reuse the same unit"
    assert len({v.unit_id() for v in variants.values()}) == len(variants)


def test_a_committed_output_is_the_completion_record(tmp_path: Path) -> None:
    units = make_units(3)
    report = run_sweep(units, process, tmp_path)
    assert report.completed == 3
    assert committed_outputs(tmp_path) == {u.output_name() for u in units}


def test_rerunning_skips_everything_already_done(tmp_path: Path) -> None:
    units = make_units(5)
    run_sweep(units, process, tmp_path)
    again = run_sweep(units, process, tmp_path)
    assert again.completed == 0
    assert again.skipped == 5


def test_a_killed_sweep_resumes_and_matches_an_uninterrupted_one(tmp_path: Path) -> None:
    """The gate, as an assertion.

    One directory gets a sweep killed part-way and then restarted; the other gets a single
    clean run. The merged results must be identical, byte for byte in ordering and content.
    """
    units = make_units(9)
    interrupted, clean = tmp_path / "interrupted", tmp_path / "clean"

    calls = {"n": 0}

    def flaky(unit: WorkUnit) -> dict[str, object]:
        calls["n"] += 1
        if calls["n"] == 4:
            raise KilledError("spot instance reclaimed")
        return process(unit)

    with pytest.raises(KilledError):
        run_sweep(units, flaky, interrupted, on_error=_reraise)

    resumed = run_sweep(units, process, interrupted)
    assert resumed.skipped == 3, "the three committed before the kill must be skipped"

    run_sweep(units, process, clean)
    assert merge(interrupted) == merge(clean)


def _reraise(_unit: WorkUnit, error: Exception) -> None:
    """run_sweep swallows failures by design; this lets one test opt out and kill the run."""
    raise error


def test_merge_order_does_not_depend_on_completion_order(tmp_path: Path) -> None:
    """Bit-identical output comes from sorting at merge, not from luck in scheduling."""
    units = make_units(6)
    forwards, backwards = tmp_path / "fwd", tmp_path / "bwd"
    run_sweep(units, process, forwards)
    run_sweep(list(reversed(units)), process, backwards)
    assert merge(forwards) == merge(backwards)


def test_one_failing_tile_does_not_end_the_sweep(tmp_path: Path) -> None:
    """Skipping a tile silently would leave a hole in the survey footprint (ADR-0019).

    So failures are collected and counted, and the rest of the sweep continues.
    """
    units = make_units(4)

    def sometimes(unit: WorkUnit) -> dict[str, object]:
        if unit.tile_id == "tile_002":
            msg = "corrupt product"
            raise ValueError(msg)
        return process(unit)

    report = run_sweep(units, sometimes, tmp_path)
    assert report.completed == 3
    assert [tile for tile, _ in report.failed] == ["tile_002"]
    assert "corrupt product" in report.failed[0][1]


def test_a_failed_unit_is_retried_on_the_next_run(tmp_path: Path) -> None:
    """No output means not done, so a transient failure heals itself on resume."""
    units = make_units(2)
    attempts = {"n": 0}

    def once(unit: WorkUnit) -> dict[str, object]:
        if unit.tile_id == "tile_001" and attempts["n"] == 0:
            attempts["n"] += 1
            msg = "transient"
            raise OSError(msg)
        return process(unit)

    first = run_sweep(units, once, tmp_path)
    assert len(first.failed) == 1
    second = run_sweep(units, once, tmp_path)
    assert second.completed == 1
    assert not second.failed


def test_a_killed_write_leaves_no_readable_output(tmp_path: Path) -> None:
    """Commit is atomic: a partial write must never be mistaken for a result."""
    unit = make_units(1)[0]

    def dies_mid_write(_unit: WorkUnit) -> dict[str, object]:
        raise KilledError("killed before returning a payload")

    report = run_sweep([unit], dies_mid_write, tmp_path)
    assert report.completed == 0
    assert committed_outputs(tmp_path) == set()
    assert merge(tmp_path) == []


def test_partial_files_are_swept_and_never_counted(tmp_path: Path) -> None:
    tmp_path.mkdir(exist_ok=True)
    leftover = tmp_path / f"{TEMP_PREFIX}abc.tmp"
    leftover.write_text("half a result", encoding="utf-8")
    commit(tmp_path, f"tile_000-deadbeef{OUTPUT_SUFFIX}", {"ok": True})

    assert committed_outputs(tmp_path) == {f"tile_000-deadbeef{OUTPUT_SUFFIX}"}
    assert sweep_partial_files(tmp_path) == 1
    assert not leftover.exists()


def test_pending_is_the_whole_of_resume(tmp_path: Path) -> None:
    units = make_units(4)
    run_sweep(units[:2], process, tmp_path)
    assert [u.tile_id for u in pending(units, tmp_path)] == ["tile_002", "tile_003"]


def test_changing_config_invalidates_previous_results(tmp_path: Path) -> None:
    """A re-run after a settings change must recompute, not resume onto stale results."""
    run_sweep(make_units(3), process, tmp_path)
    changed = make_units(3, fingerprint="cfg2")
    assert len(pending(changed, tmp_path)) == 3
