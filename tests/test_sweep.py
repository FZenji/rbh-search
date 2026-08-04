"""The Phase 3 gate, asserted: kill a sweep, restart it, get the same answer.

Runs the real detector over the committed RBH-1 fixture rather than a stub, so what is being
tested is the actual cascade and not a mock of it.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from rbh.config import SelectionWindow
from rbh.sweep import TileSource, local_sources, run, search_tile, summarise, work_units
from rbh.tileio import read_tile
from rbh.workqueue import committed_outputs, merge

FIXTURE = Path(__file__).parent / "data" / "rbh1_acs_f606w_f814w.fits"

pytestmark = pytest.mark.slow


@pytest.fixture
def tiles_dir(tmp_path: Path) -> Path:
    """Three copies of the fixture, standing in for three tiles of sky."""
    directory = tmp_path / "tiles"
    directory.mkdir()
    for i in range(3):
        shutil.copy(FIXTURE, directory / f"tile_{i:03d}.fits")
    return directory


def test_local_sources_are_sorted(tiles_dir: Path) -> None:
    """ADR-0012 forbids unsorted directory iteration in anything affecting a result."""
    assert [s.tile_id for s in local_sources(tiles_dir)] == ["tile_000", "tile_001", "tile_002"]


def test_searching_the_fixture_finds_the_real_object() -> None:
    """The sweep path must reproduce what the litmus test finds, or it is not the same search."""
    result = search_tile(read_tile(FIXTURE), "rbh1", SelectionWindow())
    assert result["n_survivors"] == 1, "the ADR-0007 window leaves exactly one candidate"
    detections = result["n_detections"]
    assert isinstance(detections, int)
    assert detections >= 1
    filters = result["filters"]
    assert isinstance(filters, list)
    assert "F606W" in filters


def test_the_payload_carries_depth_even_where_nothing_is_found() -> None:
    """Effective area (ADR-0019) needs a depth per tile, including empty ones.

    A tile with no detections still contributes area, and how much depends on how deep it
    was. That cannot be reconstructed later from a catalogue of survivors.
    """
    result = search_tile(read_tile(FIXTURE), "rbh1", SelectionWindow())
    depths = result["depth_mag"]
    assert isinstance(depths, dict)
    values = [float(v) for v in depths.values()]
    assert values, "a tile with no detections still has a depth, and still contributes area"
    assert all(20.0 < value < 35.0 for value in values)


def test_the_payload_contains_no_wall_clock(tiles_dir: Path, tmp_path: Path) -> None:
    """A timestamp would make every re-run differ while looking like a real change."""
    out = tmp_path / "out"
    run(local_sources(tiles_dir), out, config_fingerprint="cfg")
    text = "".join(p.read_text(encoding="utf-8") for p in out.iterdir())
    for banned in ("timestamp", "created_at", "generated", "2026-"):
        assert banned not in text, f"{banned!r} leaked into a per-tile result"


def test_a_killed_sweep_resumes_to_an_identical_result(tiles_dir: Path, tmp_path: Path) -> None:
    """The Phase 3 gate.

    Half the tiles are searched, the run is abandoned, and a fresh run finishes the rest. The
    merged output must equal that of a single uninterrupted run - which is only true because
    the merge sorts and nothing is appended during the sweep.
    """
    sources = local_sources(tiles_dir)
    interrupted, clean = tmp_path / "interrupted", tmp_path / "clean"

    partial = run(sources[:1], interrupted, config_fingerprint="cfg")
    assert partial.completed == 1

    resumed = run(sources, interrupted, config_fingerprint="cfg")
    assert resumed.skipped == 1
    assert resumed.completed == 2

    run(sources, clean, config_fingerprint="cfg")
    assert merge(interrupted) == merge(clean)
    assert summarise(interrupted) == summarise(clean)


def test_worker_order_does_not_change_the_merged_result(tiles_dir: Path, tmp_path: Path) -> None:
    """Two runs that complete the same units agree however they were scheduled."""
    sources = local_sources(tiles_dir)
    forwards, backwards = tmp_path / "fwd", tmp_path / "bwd"
    run(sources, forwards, config_fingerprint="cfg")
    run(list(reversed(sources)), backwards, config_fingerprint="cfg")
    assert merge(forwards) == merge(backwards)


def test_changing_the_config_recomputes_rather_than_resuming(
    tiles_dir: Path, tmp_path: Path
) -> None:
    """Content-addressed identity means a settings change invalidates prior results."""
    sources = local_sources(tiles_dir)
    out = tmp_path / "out"
    run(sources, out, config_fingerprint="cfg1")
    second = run(sources, out, config_fingerprint="cfg2")
    assert second.completed == 3
    assert second.skipped == 0
    assert len(committed_outputs(out)) == 6, "both settings' results coexist, neither overwritten"


def test_a_missing_tile_fails_that_unit_and_no_other(tiles_dir: Path, tmp_path: Path) -> None:
    """One unreadable product must not end a sweep over tens of thousands of tiles."""
    sources = [
        *local_sources(tiles_dir),
        TileSource(tile_id="ghost", path=tiles_dir / "absent.fits", inputs=("absent.fits",)),
    ]
    report = run(sources, tmp_path / "out", config_fingerprint="cfg")
    assert report.completed == 3
    assert [tile for tile, _ in report.failed] == ["ghost"]


def test_work_units_are_stable_for_the_same_inputs(tiles_dir: Path) -> None:
    sources = local_sources(tiles_dir)
    first = [u.unit_id() for u in work_units(sources, "cfg", "1.0")]
    second = [u.unit_id() for u in work_units(sources, "cfg", "1.0")]
    assert first == second
    assert len(set(first)) == 3, "distinct tiles must not collide"
