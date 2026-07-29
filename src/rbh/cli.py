"""Command line entry point.

The pipeline stages described in ``docs/design/architecture.md`` are not implemented
yet; this exposes only the introspection commands needed to verify a deployment.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from rbh import __version__
from rbh.config import Settings
from rbh.reference import RBH1, RBH1_FIXTURE

app = typer.Typer(
    name="rbh",
    help="Search public HST and JWST imaging for runaway supermassive black hole wakes.",
    no_args_is_help=True,
    add_completion=False,
)


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)


@app.command()
def config() -> None:
    """Print the resolved run configuration and its fingerprint."""
    settings = Settings()
    payload = settings.model_dump(mode="json")
    payload["fingerprint"] = settings.fingerprint()
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@app.command()
def reference() -> None:
    """Print the reference object the pipeline is calibrated against."""
    typer.echo(json.dumps(RBH1.model_dump(mode="json"), indent=2, sort_keys=True))


@app.command()
def inspect(
    tile_path: Annotated[
        Path,
        typer.Argument(help="Tile FITS file to inspect."),
    ] = Path("tests/data/rbh1_acs_f606w_f814w.fits"),
    out: Annotated[
        Path,
        typer.Option(help="Where to write the diagnostic image."),
    ] = Path("inspect.png"),
    low_snr: Annotated[float, typer.Option(help="Connectivity threshold.")] = 3.0,
    high_snr: Annotated[float, typer.Option(help="Seed threshold.")] = 5.0,
    mark_reference: Annotated[
        bool,
        typer.Option(help="Mark the published RBH-1 coordinate on the panels."),
    ] = True,
) -> None:
    """Render every stage of the detector for a tile, so you can see what it is doing.

    Produces a seven-panel figure: the raw filters, the combined image, the ridge-filter
    response, the threshold decisions, the fragments before and after stitching, and the
    measured geometry with the colour profile.
    """
    from astropy.coordinates import SkyCoord

    from rbh.diagnostics import save_stages
    from rbh.tileio import read_tile

    tile = read_tile(tile_path)
    mark = SkyCoord(RBH1.ra_deg, RBH1.dec_deg, unit="deg") if mark_reference else None
    save_stages(
        tile,
        out,
        low_snr=low_snr,
        high_snr=high_snr,
        mark=mark,
        title=f"{tile_path.name}  |  {' + '.join(tile.filter_names)}  |  tier {tile.tier}",
    )
    typer.echo(f"wrote {out} ({out.stat().st_size / 1024:.0f} KB)")


@app.command("fetch-fixture")
def fetch_fixture(
    out: Annotated[
        Path,
        typer.Option(help="Destination FITS path for the regenerated fixture."),
    ] = Path("tests/data/rbh1_acs_f606w_f814w.fits"),
) -> None:
    """Regenerate the committed RBH-1 litmus fixture from the MAST cloud archive.

    Requires network access. The fixture is committed, so this only needs re-running if
    the archive reprocesses the discovery data.
    """
    from rbh.fetch import fetch_tile, find_drizzled_products
    from rbh.tileio import write_tile

    typer.echo(f"resolving cloud products for {RBH1_FIXTURE.observation_ids}")
    uris = find_drizzled_products(RBH1_FIXTURE.observation_ids)
    if not uris:
        typer.echo("no drizzled products resolved in the cloud", err=True)
        raise typer.Exit(1)
    for uri in uris:
        typer.echo(f"  {uri}")

    tile = fetch_tile(
        RBH1_FIXTURE.centre_ra_deg,
        RBH1_FIXTURE.centre_dec_deg,
        uris,
        half_size_pixels=RBH1_FIXTURE.half_size_pixels,
        proposal_id=RBH1.discovery_proposal_id,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    write_tile(tile, out)
    size_kb = out.stat().st_size / 1024
    typer.echo(f"wrote {out} ({size_kb:.0f} KB), bands={tile.filter_names}, tier={tile.tier}")
