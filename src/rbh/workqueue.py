"""Claim, process, commit - the protocol that makes a killed sweep resumable.

ADR-0020. A sweep over tens of thousands of tiles will be interrupted, and Phase 3's gate is
that it restarts cleanly and produces bit-identical output either way. The design is one
sentence: **a work unit is complete if and only if its output file exists.** There is no
separate completion record, so there is nothing that can disagree with reality after a crash.

Three properties do the work:

* **Atomic commit.** Results are written to a temporary file and renamed into place, so a
  reader never sees a partial output and a killed worker leaves garbage rather than a
  half-committed result.
* **Content-addressed identity.** The unit id hashes the inputs, the config fingerprint and
  the code version, so changing any of them yields a different unit. Resume and invalidate
  become the same mechanism.
* **Idempotency instead of locking.** Claims are advisory. A crashed claim is redone, and
  because processing is deterministic that costs compute and nothing else. At-least-once is
  enough when the work is a pure function of its inputs.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

#: Suffix for committed per-unit outputs. Presence of one of these *is* the completion
#: record, so nothing else may use it.
OUTPUT_SUFFIX = ".json"

#: Prefix for in-flight temporary files. Distinct from the committed suffix so a directory
#: listing can never mistake one for the other.
TEMP_PREFIX = ".partial-"


@dataclass(frozen=True)
class WorkUnit:
    """One tile's worth of work, identified by everything that could change its answer.

    ``inputs`` should carry the product URIs and their ETags, not just the tile name: two
    runs against the same sky with different archive products are not the same unit, and
    conflating them would silently reuse results computed from different pixels.
    """

    tile_id: str
    inputs: tuple[str, ...]
    config_fingerprint: str
    code_version: str

    def unit_id(self) -> str:
        """Return the content-addressed identity of this unit.

        Deterministic across processes and machines: built from a sorted JSON encoding, so
        it does not depend on dict ordering, hash randomisation or platform.
        """
        payload = json.dumps(
            {
                "tile_id": self.tile_id,
                "inputs": sorted(self.inputs),
                "config_fingerprint": self.config_fingerprint,
                "code_version": self.code_version,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]

    def output_name(self) -> str:
        """Filename this unit commits to. The tile id leads so a listing is human-readable."""
        return f"{self.tile_id}-{self.unit_id()}{OUTPUT_SUFFIX}"


@dataclass
class SweepReport:
    """What a sweep did, so that skipped and failed units are counted rather than invisible."""

    completed: int = 0
    skipped: int = 0
    failed: list[tuple[str, str]] = field(default_factory=list)

    @property
    def attempted(self) -> int:
        """Units this run actually processed, successfully or not."""
        return self.completed + len(self.failed)


def committed_outputs(output_dir: Path) -> set[str]:
    """Names of every committed output, listed once per run rather than probed per unit.

    ADR-0020: the output directory *is* the queue. On a filesystem listing is free; on object
    storage it is neither free nor fast, so callers get the whole set in one pass and check
    membership in memory.
    """
    if not output_dir.is_dir():
        return set()
    return {p.name for p in output_dir.iterdir() if p.name.endswith(OUTPUT_SUFFIX)}


def commit(output_dir: Path, name: str, payload: dict[str, object]) -> Path:
    """Write a unit's result and move it into place atomically.

    The temporary file is created in the destination directory, because rename is only
    guaranteed atomic within a filesystem and a temp directory may be on another one. A
    worker killed between write and rename leaves a ``.partial-`` file, which
    :func:`sweep_partial_files` removes and which no reader will ever mistake for a result.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=output_dir, prefix=TEMP_PREFIX, suffix=".tmp")
    temp_path = Path(temp_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, sort_keys=True, indent=1)
            stream.flush()
            # fsync before the rename: without it the rename can land while the contents are
            # still only in the page cache, so a power loss leaves a committed-looking output
            # that is empty. Atomic visibility is not the same as durable content.
            os.fsync(stream.fileno())
        final = output_dir / name
        temp_path.replace(final)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise
    return final


def sweep_partial_files(output_dir: Path) -> int:
    """Delete leftover temporaries from killed workers. Returns how many were removed."""
    if not output_dir.is_dir():
        return 0
    stale = [p for p in output_dir.iterdir() if p.name.startswith(TEMP_PREFIX)]
    for path in stale:
        path.unlink(missing_ok=True)
    return len(stale)


def run_sweep(
    units: Sequence[WorkUnit],
    process: Callable[[WorkUnit], dict[str, object]],
    output_dir: Path,
    *,
    on_error: Callable[[WorkUnit, Exception], None] | None = None,
) -> SweepReport:
    """Process every unit that has no committed output yet.

    Deliberately does **not** stop on the first failure. A tile that crashes deterministically
    would otherwise halt the sweep, and skipping it silently would leave a hole in the survey
    footprint and therefore in the denominator of every density limit (ADR-0019). Failures are
    collected and reported.
    """
    report = SweepReport()
    done = committed_outputs(output_dir)

    for unit in units:
        name = unit.output_name()
        if name in done:
            report.skipped += 1
            continue
        try:
            payload = process(unit)
        except Exception as error:  # one bad tile must not end the sweep
            report.failed.append((unit.tile_id, f"{type(error).__name__}: {error}"))
            if on_error is not None:
                on_error(unit, error)
            continue
        commit(output_dir, name, payload)
        report.completed += 1
    return report


def merge(output_dir: Path) -> list[dict[str, object]]:
    """Read every committed output in sorted unit order.

    **This is what makes re-runs bit-identical.** Aggregates are never appended to during the
    sweep, because that would make the result depend on completion order and therefore on
    worker count and scheduling. Sorting by filename - which begins with the tile id and ends
    with the content hash - gives one canonical order regardless of how the sweep ran.
    """
    if not output_dir.is_dir():
        return []
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(output_dir.iterdir(), key=lambda p: p.name)
        if path.name.endswith(OUTPUT_SUFFIX)
    ]


def pending(units: Iterable[WorkUnit], output_dir: Path) -> list[WorkUnit]:
    """Units with no committed output. Resume needs no recovery logic beyond this."""
    done = committed_outputs(output_dir)
    return [unit for unit in units if unit.output_name() not in done]
