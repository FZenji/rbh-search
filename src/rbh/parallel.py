"""Run independent trials across cores.

Injection-recovery is embarrassingly parallel: every trial gets its own random seed,
derived as ``seed + index``, so no trial can observe another. Running them across
processes therefore returns *bit-identical* results to running them in a loop, which is
the property that makes this worth doing at all. If the seeding were sequential -- one
generator threaded through the loop -- this module would silently change every measured
number, and it would have to be treated as a change to the science rather than to the
plumbing.

Two deliberate restrictions:

**Small batches stay inline.** Starting a pool costs a second or two per worker on
Windows, where processes are spawned rather than forked, and each task has to pickle its
tile across. Below :data:`MIN_ITEMS_FOR_POOL` items that costs more than it saves. It
also keeps the unit tests single-process, which matters because pytest's
``filterwarnings = ["error"]`` does not reach into worker processes: a warning raised in
a worker would be printed rather than failing the run. Measurement code paths, which run
hundreds of trials, are not the place that check earns its keep.

**Work must be described by data, not closures.** Spawned workers receive their
arguments by pickle, and the injector callables used elsewhere in the pipeline close over
a live random generator, so they cannot cross that boundary. Callers pass a plain
function and picklable arguments, and the worker rebuilds what it needs on the far side.
"""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

#: Below this many items, run inline. See the module docstring.
MIN_ITEMS_FOR_POOL = 8

#: Cores left free for the rest of the machine, so a long grid does not make the
#: workstation unusable while it runs.
RESERVED_CORES = 2

_executor: ProcessPoolExecutor | None = None
_executor_workers = 0


def default_workers() -> int:
    """Report how many worker processes to use when the caller does not say."""
    return max(1, (os.cpu_count() or 1) - RESERVED_CORES)


def _shared_executor(workers: int) -> ProcessPoolExecutor:
    """Return a pool reused across calls, rebuilt only if the worker count changes.

    A completeness grid calls into here once per configuration -- dozens of times in a
    run -- and paying spawn costs on each would undo the saving. The pool is deliberately
    never shut down explicitly: it lives for the process and is reaped at exit. The
    worker count is tracked alongside rather than read back off the executor, whose own
    attribute for it is private.
    """
    global _executor, _executor_workers  # noqa: PLW0603
    if _executor is None or _executor_workers != workers:
        if _executor is not None:
            _executor.shutdown(wait=False)
        _executor = ProcessPoolExecutor(max_workers=workers)
        _executor_workers = workers
    return _executor


def map_trials[T, R](
    func: Callable[[T], R],
    items: Sequence[T] | Iterable[T],
    *,
    workers: int | None = None,
) -> list[R]:
    """Apply ``func`` to every item, in order, using several processes where worthwhile.

    Parameters
    ----------
    func
        A module-level function. Lambdas and closures cannot be pickled and will fail.
    items
        Picklable arguments, one per call.
    workers
        Process count. ``None`` uses :func:`default_workers`; ``1`` forces inline
        execution, which is what the tests want.

    Returns
    -------
    Results in the same order as ``items``, whether or not a pool was used.
    """
    materialised = list(items)
    resolved = default_workers() if workers is None else workers
    if resolved <= 1 or len(materialised) < MIN_ITEMS_FOR_POOL:
        return [func(item) for item in materialised]
    return list(_shared_executor(min(resolved, len(materialised))).map(func, materialised))
