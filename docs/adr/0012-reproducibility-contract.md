# ADR-0012 — Determinism and provenance contract

**Status:** Accepted

## Context

A candidate catalogue is a scientific claim, and its value depends entirely on whether
someone else can work out how it was produced. For a rare-object search the standard is
higher than usual: if a candidate later turns out to be real, every decision that let it
through will be scrutinised, and if it turns out to be an artifact, every decision that let
it through will be scrutinised harder.

The specific risks are ordinary and well known: an unpinned dependency changing a filter's
behaviour between runs; an unseeded random number generator making injection–recovery
unrepeatable; a threshold edited between the sweep and the paper; an archive file quietly
reprocessed after we read it.

## Decision

**Determinism.** Identical inputs and identical configuration produce **bit-identical**
outputs.

- All randomness derives from a single configured seed (`Settings.random_seed`), including
  synthetic injection positions, orientations and parameters.
- No wall-clock time, hostname, PID or filesystem iteration order may influence any
  result. Timestamps are recorded as metadata, never used in computation.
- Tile IDs are deterministic functions of sky position.
- Floating-point reduction order is fixed where it affects results.

**Provenance.** Every output row carries enough to reconstruct itself:

| Field | Purpose |
|---|---|
| `tile_id` | Which sky tile |
| `source_uri` + `source_etag` | Which exact archive bytes — ETag catches silent reprocessing |
| `proposal_id`, `instrument`, `filter` | Attribution and required acknowledgements |
| `config_fingerprint` | SHA-256 prefix of the resolved settings (`rbh.config.Settings.fingerprint`) |
| `code_version` | Package version plus git SHA |
| `run_id` | Which sweep |

Two rows sharing a `config_fingerprint` came from identical thresholds and therefore share
a selection function. Two rows differing in it did not, however similar the runs looked.

**Environment.** `uv.lock` is committed and CI installs with `--locked`. A run records the
resolved environment alongside its outputs.

**Decisions.** Recorded as ADRs before implementation. **Accepted ADRs are superseded,
never rewritten** — an edited Decision section invalidates every published result derived
from it.

## Consequences

- Any run can be replayed. Any candidate can be traced to the bytes and thresholds that
  produced it.
- Silent archive reprocessing is detected rather than absorbed.
- Some convenient patterns become forbidden: parallel reductions with non-deterministic
  order, seeding from the clock, iterating a directory without sorting. These need to be
  caught in review, since no linter will catch them.
- Storage overhead per row is a few hundred bytes. Irrelevant.
- Superseding rather than editing ADRs makes the directory grow monotonically, including
  records of decisions no longer in force. That is a feature: the reasoning chain behind a
  published catalogue stays legible.

## Alternatives considered

- **Best-effort reproducibility** (pin dependencies, hope for the rest). Rejected: the
  failures are silent, and they surface exactly when a result is being challenged.
- **Full containerisation as the primary mechanism.** Strong for environment
  reproducibility and worth adding later, but it does nothing about seeds, ordering or
  provenance, which are the parts that actually bite.
- **Record provenance only for surviving candidates.** Cheaper, but makes it impossible to
  ask afterwards why something was *rejected* — which is the more common question.
