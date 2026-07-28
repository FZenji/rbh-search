"""Smoke tests for the CLI surface."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from rbh import __version__
from rbh.cli import app

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_config_emits_json_with_fingerprint() -> None:
    result = runner.invoke(app, ["config"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert len(payload["fingerprint"]) == 16
    assert "selection" in payload


def test_reference_emits_rbh1() -> None:
    result = runner.invoke(app, ["reference"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["name"] == "RBH-1"


def test_bare_invocation_shows_help() -> None:
    result = runner.invoke(app, [])
    assert "runaway supermassive black hole" in result.stdout
