# Contributing

## Ground rules

1. **Decisions get an ADR before they get code.** If a change would make a future reader
   ask "why is it done this way?", write an ADR in [`docs/adr/`](docs/adr/) first. See
   [ADR-0012](docs/adr/0012-reproducibility-contract.md) for why this matters more than
   usual here: a candidate catalogue is only trustworthy if the decisions behind its
   selection function are on the record.
2. **Nothing that touches science pixels ships without an injection–recovery test.** A
   detector change that improves the candidate list but is not measured against synthetic
   truth has silently changed the selection function.
3. **The RBH-1 litmus test is a hard gate.** Any change that stops the pipeline
   recovering RBH-1 fails CI, no exceptions and no `xfail`.
4. **No discovery claims.** See [ADR-0015](docs/adr/0015-no-discovery-claims.md).

## Setup

```bash
uv sync --all-extras --group dev --group docs
uv run pre-commit install
```

## The gates

All four must pass locally before you push; CI runs the same four.

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest -m "not network"
```

Tests that reach MAST or AWS are marked `network` and are excluded from CI. Run them
deliberately with `uv run pytest -m network`.

## Commits and branches

- Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`).
- Work on a branch; `main` is protected and only moves through PRs.
- Squash-merge, so the PR title becomes the history entry — make it a real sentence.

## Adding an ADR

Copy the structure of an existing one. Number sequentially. Status is `Proposed`,
`Accepted`, `Superseded by ADR-XXXX`, or `Deprecated`. **Never edit the Decision section
of an Accepted ADR** — supersede it with a new one instead, so the reasoning chain that
produced a published catalogue stays legible.

## Data hygiene

Nothing under `data/` or `runs/` is committed. Test fixtures live in `tests/data/` and
must be small (< 2 MB, enforced by pre-commit) and derived from public archival data with
their provenance recorded in `tests/data/PROVENANCE.md`.
