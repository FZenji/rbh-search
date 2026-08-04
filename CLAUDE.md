# Project notes for AI assistants

## What this is

A search for runaway supermassive black hole wakes — thin, linear, star-forming filaments
— in public HST and JWST imaging. Design phase; the documentation in `docs/` is the
current deliverable and the code is a scaffold.

## Read these before proposing anything

1. **`docs/design/lab-notebook.md`** — every measurement, gotcha and wrong assumption so
   far, newest first. Read this first: it is where the nuance lives that no ADR captures,
   and it will stop you re-deriving things the expensive way.
2. `docs/adr/README.md` — every locked decision. **Decisions get an ADR before they get
   code.** If you are about to make a design choice, check whether it is already fixed.
3. `docs/science/rbh-1-dossier.md` — the one known object; all published numbers, sourced.
4. `docs/design/architecture.md` — the stage cascade.

**When you learn something, write it to the lab notebook before the session ends.** A number
measured, a gotcha hit, an assumption disproved. Context gets compressed; the repo does not.

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
- **Python sources stay pure ASCII.** PowerShell 5.1 on this machine reads files as ANSI
  and writes UTF-8-with-BOM, so any `Get-Content | Set-Content` round-trip silently
  corrupts em-dashes and smart quotes. Use the Edit tool for source files, never a shell
  round-trip. Markdown keeps its typography because it is never round-tripped.

## Module layout

| Module | Role |
|---|---|
| `tile.py` | The normalised image unit: bands, weights, WCS, zero points. Nothing downstream knows which telescope produced the pixels. |
| `detect.py` | Stage 2 primitive: ridge filter, noise normalisation, hysteresis thresholding. |
| `linking.py` | Stage 2b primitive: rejoin collinear fragments (ADR-0016). |
| `pipeline.py` | Composes detect + linking. Kept separate so neither primitive imports the other. |
| `morphology.py` | Stage 3: length, width, axis ratio, position angle, straightness. |
| `colour.py` | Colour gradient along a feature's axis. |
| `geometry.py` | Shared principal-axis maths, so the three above need not import each other. |
| `fetch.py` | The **only** module that touches the network. |
| `tileio.py` | RICE-compressed FITS read/write. |
| `diagnostics.py` | Renders every detector stage; also the seed of the Phase 5 vetting queue. |
| `synthetic.py` | Parametric wake generator. Defaults are **fitted** to the transplant, not published values. |
| `depth.py` | Simulates shallower data by degrading real tiles, so completeness can be measured against depth (ADR-0018). Produces an **upper bound**: photon noise only. |
| `template.py` | Cuts the real RBH-1 out as a transplantable template (ADR-0017). |
| `inject.py` | Adds sources to real tiles, including the `(1 − f²)σ²` noise compensation. |
| `recovery.py` | Injection–recovery trials and completeness. |
| `controls.py` | Negative controls: noise, real sky, rotated/mirrored, shuffled filters, noise-model check. |
| `discriminate.py` | Stage 6 wake-vs-disc features. Docstrings record **measured** power, not intended. |
| `negatives.py` | Harvests real elongated galaxies as the discriminator's negative class. |
| `studies.py` | The measurement studies behind published numbers. Never put these in a scratch script. |

## Phase 2 gotchas worth knowing

- **Completeness means passing the selection window, not merely being detected.** A source
  detected as three fragments reaches no catalogue. `Trial` records both separately.
- **The generator's parameters interact.** Widening a feature at fixed flux lowers its peak
  surface brightness, so less clears the threshold and recovered length drops. Calibrate on
  a joint grid, never one parameter at a time.
- **`WakeParameters.width_arcsec` is degenerate with the effective PSF** and is not a
  physical claim. See ADR-0017.
- **`fetch-destinations --layout grid` puts its first tile on the RBH-1 field.** Always pass
  `--exclude dest_000` to `rbh controls`, or the real object gets counted as a false
  positive.
- **A ratio of 1.00 from one survivor is not a null result, it is no constraint.** The
  linking cost read as "zero cost" on 8 tiles and "five-fold" on 17. Report the power, not
  just the point estimate.
- MAST's *query* endpoint times out often; its S3 bucket is reliable. Prefer
  `_resolve_uris` / explicit `--uri` over `find_drizzled_products`.
- **Anything that produces a published number belongs in `rbh.studies`, not a scratch
  script.** Its output goes to `runs/` and, if quoted anywhere, is copied to `docs/data/`.
- `Select-Object -Last N` on a background command buffers until exit, so you cannot watch
  progress; write to a file from inside the script instead.

## Where the numbers are

| | |
|---|---|
| Published RBH-1 literature values | `rbh.reference.RBH1` (frozen; never edit) |
| What our pipeline recovers | `rbh.reference.RBH1_LITMUS` (ours; moves when the detector improves) |
| Fitted generator parameters | `rbh.synthetic.WakeParameters` defaults |
| Calibration and completeness results | `docs/data/phase2-*.json` |
| Narrative record of how we got them | `docs/design/lab-notebook.md` |
