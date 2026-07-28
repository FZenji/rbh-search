# Project notes for AI assistants

## What this is

A search for runaway supermassive black hole wakes — thin, linear, star-forming filaments
— in public HST and JWST imaging. Design phase; the documentation in `docs/` is the
current deliverable and the code is a scaffold.

## Read these before proposing anything

1. `docs/adr/README.md` — every locked decision. **Decisions get an ADR before they get
   code.** If you are about to make a design choice, check whether it is already fixed.
2. `docs/science/rbh-1-dossier.md` — the one known object; all published numbers, sourced.
3. `docs/design/architecture.md` — the stage cascade.

## The four things most likely to be got wrong

1. **This search is area-limited, not depth-limited.** RBH-1 was a high-S/N detection in a
   one-orbit image. Do not propose restricting to deep fields (ADR-0001).
2. **The hard false positive is the bulgeless edge-on disk galaxy**, not artifacts.
   Artifacts are largely handled by searching drizzled CR-rejected products (ADR-0003).
   The disk problem is what kept RBH-1 contested for three years.
3. **A null result is the expected outcome and is publishable** — but only because
   injection–recovery measures the selection function (ADR-0009). Anything that changes
   what survives the cascade must be measurable.
4. **Never call a candidate a discovery** (ADR-0015).

## Conventions

- `uv` for everything. `uv run <cmd>`, never a bare `python`.
- Gates: `ruff check` · `ruff format --check` · `mypy` · `pytest -m "not network"`.
- Angular quantities carry the unit in the name: `length_arcsec`, never `length`.
- Science data reads go through `.section[...]` on lazily-opened FITS — a bare `.data` on
  an archive mosaic pulls hundreds of MB per tile (ADR-0002).
- Nothing under `data/` or `runs/` is committed. Test fixtures go in `tests/data/` with
  provenance recorded.
- Determinism is a hard requirement: no wall-clock, no unseeded RNG, no unsorted directory
  iteration in anything that affects a result (ADR-0012).
