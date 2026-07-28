# ADR-0010 — RBH-1 recovery is a hard, offline CI gate

**Status:** Accepted

## Context

We have exactly one known positive. It is the only empirical check that the pipeline
detects the real phenomenon rather than a plausible-looking abstraction of it.

Such a check is worth very little if it is run occasionally, by hand, against live archive
data. It needs to run on every commit, which means it must be **offline, fast and
deterministic** — a test that depends on MAST being reachable will be skipped, and a
skipped test protects nothing.

There is also a specific failure mode worth naming: threshold tuning. Detector work
naturally drifts toward whatever produces a cleaner candidate list, and a cleaner list is
usually a stricter one. Without a fixed anchor, it is entirely possible to tune the
pipeline until it can no longer find the object it was built to find.

## Decision

The RBH-1 litmus test is a **hard CI gate**.

- A small cutout of the discovery data — HST **GO-16912**, ACS/WFC, F606W + F814W, around
  02ʰ41ᵐ45.43ˢ −08°20′55.4″ — is cached as a **committed fixture** under `tests/data/`,
  under 2 MB (enforced by pre-commit), with provenance recorded in
  `tests/data/PROVENANCE.md`.
- The test runs **offline and deterministically** on every commit, marked `litmus`.
- The assertion is not "something was detected". The recovered **length, width, axis ratio,
  position angle and colour-gradient sign** must all fall within stated tolerance of the
  published values in the [dossier](../science/rbh-1-dossier.md).
- Published values live in `rbh.reference.RBH1` as a frozen model, with their own tests
  guarding them against edits. They are literature measurements, not tunables.
- **No `xfail`, no `skip`, no conditional relaxation.** If a change breaks RBH-1 recovery,
  the change is wrong until argued otherwise in a PR, in writing.

## Consequences

- Any threshold change that would have hidden the prototype fails immediately and loudly.
- CI stays fast and hermetic; it cannot go red because of a MAST outage.
- N = 1 remains the limitation. This test proves the pipeline is not broken; it says
  nothing about completeness. That is what
  [injection–recovery](0009-injection-recovery.md) is for, and the two must not be confused
  for one another.
- Over-fitting risk: tuning until RBH-1 is recovered and stopping. Mitigated by requiring
  completeness measured over a synthetic parameter range far wider than RBH-1 occupies,
  and by the realism gate in ADR-0009 running in the opposite direction.
- Committing archival pixels to git needs care — small, public, provenance-documented, and
  size-capped.

## Alternatives considered

- **Fetch the cutout from MAST at test time.** No committed data, always current.
  Rejected: slow, non-deterministic, and fails when MAST does — so it would end up marked
  `network` and excluded from CI, which defeats the purpose.
- **Test on synthetic data only.** Fast and unlimited. Rejected: circular. Synthetics test
  the pipeline against our model of the phenomenon, not against the phenomenon.
- **Make it a warning rather than a failure.** Rejected: a warning in CI is a warning
  nobody reads.
