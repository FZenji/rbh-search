"""Command line entry point.

The pipeline stages described in ``docs/design/architecture.md`` are not implemented
yet; this exposes only the introspection commands needed to verify a deployment.
"""

from __future__ import annotations

import json
import math
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


#: Fallback path used to recover product URIs without touching the archive's query API.
FIXTURE_PATH = Path("tests/data/rbh1_acs_f606w_f814w.fits")


def _resolve_uris(explicit: list[str] | None) -> list[str]:
    """Find the S3 product URIs for the discovery visit, cheapest source first.

    MAST's query endpoint is markedly less reliable than its S3 bucket - it timed out
    repeatedly while this was being written - so it is the last resort rather than the
    first. Explicit URIs win; otherwise the committed fixture's own provenance is used,
    which is exactly what ADR-0012 records it for.
    """
    if explicit:
        return list(explicit)
    if FIXTURE_PATH.exists():
        from rbh.tileio import read_tile

        recorded = read_tile(FIXTURE_PATH).provenance.get("source_uri", "")
        uris = [u for u in recorded.split(";") if u.startswith("s3://") and u.endswith(".fits")]
        if uris:
            typer.echo(f"using {len(uris)} URIs recorded in the fixture provenance")
            return uris
    typer.echo("querying MAST for cloud product URIs (this endpoint is often slow)")
    from rbh.fetch import find_drizzled_products

    return find_drizzled_products(RBH1_FIXTURE.observation_ids)


@app.command()
def calibrate(
    destinations: Annotated[
        Path, typer.Option(help="Directory of cached destination tiles.")
    ] = Path("data/destinations"),
    out: Annotated[Path, typer.Option(help="Where to write the calibration record.")] = Path(
        "runs/calibration.json"
    ),
    per_tile: Annotated[int, typer.Option(help="Injection sites per destination tile.")] = 4,
) -> None:
    """Fit the synthetic generator to the transplanted real RBH-1 (ADR-0017 Tier 2).

    Scans a joint grid over tail brightness, clumpiness and width. Slow - a few hundred
    detection runs - and only needs re-running when the detector changes.
    """
    import json

    from rbh.studies import calibrate_generator, collect_sites, reference_template

    reference = reference_template(FIXTURE_PATH)
    sites = collect_sites(FIXTURE_PATH, destinations, per_tile=per_tile)
    typer.echo(
        f"{len(sites)} injection sites; template mag={reference.total_mag_ab:.2f} "
        f"colour={reference.colour_ab:+.2f}"
    )
    result = calibrate_generator(sites, reference)

    typer.echo(f"\ntransplant target: {_fmt(result.target)}")
    typer.echo(f"best fit         : {_fmt(result.best_statistics)}  cost={result.best_cost:.2f}")
    typer.echo(
        f"  tail_brightness={result.best.tail_brightness} "
        f"clumpiness={result.best.clumpiness} width_arcsec={result.best.width_arcsec}"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result.to_dict(), indent=1), encoding="utf-8")
    typer.echo(f"wrote {out}")


@app.command()
def completeness(
    destinations: Annotated[
        Path, typer.Option(help="Directory of cached destination tiles.")
    ] = Path("data/destinations"),
    out: Annotated[Path, typer.Option(help="Where to write the completeness grid.")] = Path(
        "runs/completeness.json"
    ),
    per_tile: Annotated[int, typer.Option(help="Injection sites per destination tile.")] = 4,
) -> None:
    """Measure completeness against brightness, at several clumpiness values.

    This is the Phase 2 deliverable: the selection function slice that lets a null result
    become a space-density limit.
    """
    import json

    from rbh.studies import (
        collect_sites,
        completeness_grid,
        half_completeness_limit,
        reference_template,
    )

    reference = reference_template(FIXTURE_PATH)
    sites = collect_sites(FIXTURE_PATH, destinations, per_tile=per_tile)
    typer.echo(f"{len(sites)} injection sites; template mag={reference.total_mag_ab:.2f}")

    rows = completeness_grid(sites, reference)
    sources: list[str] = []
    for row in rows:
        if row["source"] not in sources:
            sources.append(str(row["source"]))

    typer.echo("\n50% completeness limits:")
    limits = {}
    for source in sources:
        selected = [r for r in rows if r["source"] == source]
        mags = [float(r["mag"]) for r in selected]
        comp = [float(r["completeness"]) for r in selected]
        limits[source] = half_completeness_limit(mags, comp)
        typer.echo(f"  {source:<20} {limits[source]:.2f}")
    finite = [v for v in limits.values() if not math.isnan(v)]
    if finite:
        typer.echo(f"  spread across clumpiness: {max(finite) - min(finite):.2f} mag")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "n_sites": len(sites),
                "template_mag": round(reference.total_mag_ab, 3),
                "template_colour": round(reference.colour_ab, 3),
                "half_completeness_limits": limits,
                "rows": rows,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    typer.echo(f"wrote {out}")


def _fmt(stats: dict[str, float]) -> str:
    return (
        f'len={stats["median_length_arcsec"]:.2f}" '
        f'wid={stats["median_width_arcsec"]:.3f}" '
        f"ar={stats['median_axis_ratio']:.1f} "
        f"frag={100 * stats['fragmentation']:.0f}% "
        f"complete={100 * stats['completeness']:.0f}%"
    )


@app.command("fetch-destinations")
def fetch_destinations(
    count: Annotated[int, typer.Option(help="How many destination tiles to cache.")] = 12,
    out_dir: Annotated[
        Path,
        typer.Option(help="Cache directory. Git-ignored by design."),
    ] = Path("data/destinations"),
    seed: Annotated[int, typer.Option(help="Seed for the tile positions.")] = 20230208,
    uri: Annotated[
        list[str] | None,
        typer.Option(
            help="Explicit S3 product URI to read from; repeatable. Skips archive lookup.",
        ),
    ] = None,
) -> None:
    """Cache real sky tiles from the RBH-1 discovery visit, for injection-recovery.

    These are the destinations synthetic and transplanted wakes get injected into. Using
    the same visit means the same instrument, depth and epoch as the one object we can
    calibrate against, so a completeness measured here is directly comparable to the
    Phase 1 recovery. Requires network access; results are cached and git-ignored.
    """
    import numpy as np

    from rbh.fetch import fetch_tile
    from rbh.tileio import write_tile

    uris = _resolve_uris(uri)
    if not uris:
        typer.echo("no drizzled products resolved in the cloud", err=True)
        raise typer.Exit(1)

    rng = np.random.default_rng(seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    # Offsets in arcmin around the visit centre, avoiding the RBH-1 position itself.
    for index in range(count):
        path = out_dir / f"dest_{index:03d}.fits"
        if path.exists():
            typer.echo(f"  {path.name} already cached")
            written += 1
            continue
        # Offsets in arcmin, kept small enough that a 20 arcsec cutout stays inside the
        # ACS/WFC mosaic even at the corners of the range.
        offset_ra = float(rng.uniform(-0.8, 0.8)) / 60.0
        offset_dec = float(rng.uniform(-0.8, 0.8)) / 60.0
        ra = RBH1_FIXTURE.centre_ra_deg + offset_ra
        dec = RBH1_FIXTURE.centre_dec_deg + offset_dec
        try:
            tile = fetch_tile(
                ra,
                dec,
                uris,
                half_size_pixels=RBH1_FIXTURE.half_size_pixels,
                proposal_id=RBH1.discovery_proposal_id,
            )
        except (ValueError, OSError) as error:
            typer.echo(f"  skipped offset {index}: {error}")
            continue
        if any(not (band.weight > 0).all() for band in tile.bands):
            typer.echo(f"  skipped offset {index}: incomplete coverage")
            continue
        write_tile(tile, path)
        written += 1
        typer.echo(f"  wrote {path.name} at {ra:.5f} {dec:+.5f}")
    typer.echo(f"{written} destination tiles in {out_dir}")


@app.command("fetch-fixture")
def fetch_fixture(
    out: Annotated[
        Path,
        typer.Option(help="Destination FITS path for the regenerated fixture."),
    ] = Path("tests/data/rbh1_acs_f606w_f814w.fits"),
    uri: Annotated[
        list[str] | None,
        typer.Option(
            help="Explicit S3 product URI to read from; repeatable. Skips archive lookup.",
        ),
    ] = None,
) -> None:
    """Regenerate the committed RBH-1 litmus fixture from the MAST cloud archive.

    Requires network access. The fixture is committed, so this only needs re-running if
    the archive reprocesses the discovery data.
    """
    from rbh.fetch import fetch_tile
    from rbh.tileio import write_tile

    uris = _resolve_uris(uri)
    if not uris:
        typer.echo("no drizzled products resolved in the cloud", err=True)
        raise typer.Exit(1)
    for resolved in uris:
        typer.echo(f"  {resolved}")

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
