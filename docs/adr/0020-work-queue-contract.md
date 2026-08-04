# ADR-0020 — Completion is a committed output file, not a queue state

**Status:** Accepted

**In plain terms:** A sweep over tens of thousands of tiles will be killed part-way — by a
spot instance going away, a crash, or someone pressing Ctrl-C. When it restarts it must pick
up where it left off and must end up with exactly the same answer as if it had never been
interrupted. The trick we use is to make the *existence of a finished output file* the only
record that a tile is done. There is no separate list of what has been completed, because a
separate list is one more thing that can disagree with reality.

## Context

Phase 3's gate is "a full dry-run over one deep field, restartable from an arbitrary kill,
with bit-identical output on re-run". [ADR-0012](0012-reproducibility-contract.md) already
requires determinism; [ADR-0014](0014-output-data-model.md) already puts per-tile results in
one file per tile, explicitly to enable claim–process–commit.

What is undecided is the protocol: how a worker claims a tile, what happens when it dies
holding a claim, and what guarantees the re-run actually gets.

The obvious design — a queue table with `pending` / `claimed` / `done` states — has a failure
mode that matters at this scale. The state and the output are two separate things that must
agree, and every crash is an opportunity for them to stop agreeing: a tile marked done whose
output was never flushed, or an output written by a worker that died before updating the
table. Reconciling them needs a repair pass that is itself only correct if written perfectly.

## Decision

**A work unit is complete if and only if its output file exists.** There is no other
completion record, so there is nothing to reconcile.

**Commit is an atomic rename.** Results are written to a temporary file and renamed into
place. A reader therefore never sees a partial output: on every filesystem the sweep targets,
rename within a directory is atomic. A worker killed mid-write leaves a temporary file, which
is garbage to be swept, never a half-committed result.

**Work-unit identity is content-addressed.** The unit id hashes the tile identity, the
product URIs and their ETags, the resolved config fingerprint, and the code version. Any
change to the inputs or the settings produces a *different* unit, so a re-run after a change
does not silently reuse stale results — it simply finds no output and recomputes. This is
what makes "resume" and "invalidate" the same mechanism.

**Claims are advisory leases, not locks.** A worker may write a claim marker to avoid
duplicating work, but correctness does not depend on it. A crashed claim expires and the unit
is redone; because processing is deterministic and commit is atomic, redundant processing
costs compute and changes nothing else. **We buy correctness with idempotency rather than
with distributed locking**, which is the only one of the two that survives a network
partition.

**Aggregates are produced by a separate deterministic merge**, never by appending to a shared
file during the sweep. The merge reads committed per-unit outputs in sorted unit-id order.
Appending during the sweep would make the output depend on completion order, and therefore on
worker count and scheduling — which is exactly what the gate forbids.

## Consequences

- **Bit-identical re-runs follow from the merge order, not from luck.** Any two runs that
  complete the same set of units produce the same aggregate, whatever order they finished in
  or how many workers were used.
- Resume is free and needs no recovery logic: list the outputs, skip those units.
- A tile whose processing crashes deterministically will be retried forever across restarts.
  That is the right default — silently skipping it would put a hole in the survey footprint
  and therefore in the denominator ([ADR-0019](0019-effective-area-is-the-denominator.md)) —
  but the retry must be **counted and reported**, not invisible, or a systematically failing
  class of tile becomes a systematically missing piece of sky.
- The output directory is the queue, so it must be listable at reasonable cost. On a
  filesystem this is free; on object storage, listing tens of thousands of keys costs real
  time and money, so the sweep caches the listing per run rather than probing per unit.
- Content-addressed identity means changing a threshold invalidates every unit. That is
  correct and it is expensive, which is a useful pressure against fiddling with settings
  mid-sweep.

## Alternatives considered

- **A queue table with explicit states.** Rejected: it duplicates the completion fact, and
  every crash risks divergence between the table and the outputs. The repair pass needed to
  fix that is more code than the entire protocol above.
- **A distributed lock service.** Rejected as disproportionate. It buys exactly-once
  processing, which we do not need, and adds a dependency that can fail in ways the sweep
  cannot recover from. Idempotency gives us at-least-once, which is sufficient because
  processing is deterministic.
- **Append results to one growing file.** Rejected: output would depend on completion order,
  the gate would be unmeetable, and a kill mid-append corrupts the file rather than one unit.
- **Mark completion by file existence but keep a mutable "in progress" state.** Rejected as
  the worst of both: it reintroduces the reconciliation problem for a benefit — avoiding some
  duplicate work — that the lease already delivers without correctness risk.
