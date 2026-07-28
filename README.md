# rbh-search

A reproducible search for **runaway supermassive black hole (RBH) wakes** in the public
HST and JWST imaging archives.

Exactly one such object is known: **RBH-1**, a 62 kpc linear trail of shocked gas and
newborn stars at z = 0.964, found serendipitously in a single-orbit HST/ACS image and
confirmed in 2026 by JWST/NIRSpec detection of its supersonic bow shock. This project
asks whether there are others hiding in thirty years of archival pixels, and — just as
importantly — puts a number on how many we would have found if they were there.

> **Status: design phase.** No detector is implemented yet. The documentation in
> [`docs/`](docs/) is the current deliverable and is complete; the code is a scaffold.

---

## The idea in one paragraph

An SMBH ejected from its host at ~1000 km/s ploughs through the circumgalactic medium,
driving a bow shock that compresses gas into a narrow trail of star formation behind it.
Seen on the sky this is a **thin, nearly-straight, blue, one-sided filament** — a few
arcseconds long, roughly PSF-wide, anchored to a galaxy at one end and terminating in a
compact knot at the other, with stellar ages increasing away from the tip. That is a very
specific morphological signature, and it is cheap to search for. It is also easy to
confuse with a bulgeless edge-on disk galaxy, which is precisely why RBH-1 was contested
in the literature for three years. Rejecting that contaminant is the hard part of this
project, not detecting the streaks.

## Why this is worth doing

- **The search is area-limited, not depth-limited.** RBH-1 was a high-significance
  detection in a *one-orbit* image. Depth buys almost nothing; sky area buys everything.
  See [ADR-0001](docs/adr/0001-search-the-full-archive.md).
- **A null result is still a result.** Because the pipeline measures its own completeness
  by injection–recovery over a MOC-accounted unique sky area, zero detections becomes a
  quantitative upper limit on the space density of SMBH wakes — which in turn *predicts
  the Euclid DR1 yield*. See [ADR-0009](docs/adr/0009-injection-recovery.md).
- **The timing is good.** Euclid DR1 releases ~1900 deg² on 21 October 2026 and Roman
  launched 30 August 2026. The HST/JWST archive is where we can calibrate against a known
  positive; those surveys are where the yield is. The I/O layer is built to move.

## Documentation

| | |
|---|---|
| **Science** | |
| [RBH-1 dossier](docs/science/rbh-1-dossier.md) | Everything measured about the one known object, with sources |
| [Target signature](docs/science/target-signature.md) | The observables the pipeline searches for, and their numeric ranges |
| [False positives](docs/science/false-positives.md) | The contaminant taxonomy and how each is rejected |
| **Design** | |
| [Architecture](docs/design/architecture.md) | Stages, data flow, work units, parallelism, memory |
| [Data sources](docs/design/data-sources.md) | What we search, where it lives, how it is accessed |
| [Validation](docs/design/validation.md) | Litmus test, injection–recovery, negative controls, human vetting |
| [Roadmap](docs/design/roadmap.md) | Phases, milestones, and the Euclid/Roman handover |
| **Decisions** | |
| [ADR index](docs/adr/README.md) | Every locked architectural and scientific decision |

## Quickstart

```bash
uv sync --all-extras --group dev
uv run rbh --help
uv run pytest -m "not network"
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Every non-trivial decision gets an ADR before it
gets code.

## Licence and citation

BSD-3-Clause. See [CITATION.cff](CITATION.cff). All data searched is public and hosted by
MAST; see [docs/design/data-sources.md](docs/design/data-sources.md) for the required
acknowledgements.
