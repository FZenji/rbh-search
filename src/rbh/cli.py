"""Command line entry point.

The pipeline stages described in ``docs/design/architecture.md`` are not implemented
yet; this exposes only the introspection commands needed to verify a deployment.
"""

from __future__ import annotations

import json

import typer

from rbh import __version__
from rbh.config import Settings
from rbh.reference import RBH1

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
