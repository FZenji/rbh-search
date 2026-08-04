# Architectural Decision Records

An **ADR** is a short document recording one decision: what we chose, why, and what it
costs us. Each one below opens with an **"In plain terms"** summary, so you can get the
gist without the jargon. For all 15 in one place, see the table at the end of
[Start here](../start-here.md).

Every decision that shapes what this pipeline finds — and therefore what its catalogue
means — is recorded here before it is implemented.

This matters more than usual for this project. A candidate catalogue is only trustworthy
if the selection function behind it is legible, and the selection function *is* the sum of
these decisions. An ADR whose Decision section has been quietly edited after the fact
invalidates any published result derived from it, so **Accepted ADRs are superseded, never
rewritten**.

## Index

| # | Decision | Status |
|---|---|---|
| [0001](0001-search-the-full-archive.md) | Search the full HST + JWST archive, not just deep fields | Accepted |
| [0002](0002-compute-next-to-the-data.md) | Compute runs next to the data, with a local corpus for dev and CI | Accepted |
| [0003](0003-search-plane-drizzled-mosaics.md) | Search drizzled, CR-rejected, Gaia-aligned mosaics | Accepted |
| [0004](0004-work-unit-is-a-sky-tile.md) | The unit of work is a sky tile, not a file | Accepted |
| [0005](0005-detector-cascade.md) | Ridge filter primary, MRT cross-check, classical before ML | Accepted |
| [0006](0006-two-tier-filter-requirement.md) | Two tiers by filter coverage, prioritising cross-filter vetting | Accepted |
| [0007](0007-target-selection-window.md) | Fix the target selection window explicitly | Accepted |
| [0008](0008-scored-discriminants-not-cuts.md) | Score the wake-vs-disk discriminants, do not cut on them | Accepted |
| [0009](0009-injection-recovery.md) | Injection–recovery is mandatory; the selection function is a deliverable | Accepted |
| [0010](0010-rbh1-regression-test.md) | RBH-1 recovery is a hard, offline CI gate | Accepted |
| [0011](0011-human-vetting-protocol.md) | Human vetting is a measured pipeline stage, not an afterthought | Accepted |
| [0012](0012-reproducibility-contract.md) | Determinism and provenance contract | Accepted |
| [0013](0013-survey-agnostic-io.md) | Abstract the I/O layer for Euclid and Roman | Accepted |
| [0014](0014-output-data-model.md) | Output data model and formats | Accepted |
| [0015](0015-no-discovery-claims.md) | Publish candidates, never discoveries | Accepted |
| [0016](0016-rejoin-collinear-fragments.md) | Rejoin collinear fragments rather than tuning the threshold | Accepted |
| [0017](0017-synthetic-realism.md) | Anchor synthetic realism on transplanted real pixels | Accepted |
| [0018](0018-selection-function-stratified-by-depth.md) | Stratify the selection function by depth, measured by degrading real tiles | Accepted |

ADR-0003 and ADR-0005 carry **amendments** added during Phase 1, recording where
implementation contradicted an assumption. Amendments correct the Context and are appended
below the original text; the Decision sections are untouched.

## Format

Each record has: **Status**, **Context** (the forces at play, with evidence),
**Decision** (what we will do, in the imperative), **Consequences** (what this costs us,
honestly), and **Alternatives considered** (what we rejected and why).

Status is one of `Proposed`, `Accepted`, `Superseded by ADR-XXXX`, `Deprecated`.
