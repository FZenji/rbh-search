"""The diagnostic renderer must work on any tile, including degenerate ones."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from astropy.coordinates import SkyCoord
from matplotlib.figure import Figure

from conftest import SHAPE, draw_line, make_tile
from rbh.diagnostics import render_stages, save_stages


def test_renders_for_a_two_filter_tile(noise_field: np.ndarray) -> None:
    line = draw_line(SHAPE, length_pixels=120.0, width_pixels=3.0, angle_deg=30.0, amplitude=5.0)
    tile = make_tile({"F606W": (noise_field + line).astype(np.float32), "F814W": noise_field})
    figure = render_stages(tile, title="synthetic")
    assert isinstance(figure, Figure)
    assert len(figure.axes) >= 8


def test_renders_for_a_single_filter_tile(noise_field: np.ndarray) -> None:
    """Tier B tiles have no colour information; the figure must still render."""
    line = draw_line(SHAPE, length_pixels=120.0, width_pixels=3.0, angle_deg=10.0, amplitude=5.0)
    tile = make_tile({"F606W": (noise_field + line).astype(np.float32)})
    assert isinstance(render_stages(tile), Figure)


def test_renders_when_nothing_is_detected(noise_field: np.ndarray) -> None:
    """An empty field must not crash the renderer - most tiles will look like this."""
    tile = make_tile({"F606W": noise_field, "F814W": (noise_field * 0.5).astype(np.float32)})
    figure = render_stages(tile)
    titles = [ax.get_title() for ax in figure.axes]
    assert any("nothing detected" in t for t in titles)


def test_marker_is_accepted(noise_field: np.ndarray) -> None:
    tile = make_tile({"F606W": noise_field})
    mark = tile.wcs.pixel_to_world(128.0, 128.0)
    assert isinstance(render_stages(tile, mark=SkyCoord(mark)), Figure)


def test_save_writes_a_png(tmp_path: Path, noise_field: np.ndarray) -> None:
    line = draw_line(SHAPE, length_pixels=110.0, width_pixels=3.0, angle_deg=45.0, amplitude=5.0)
    tile = make_tile({"F606W": (noise_field + line).astype(np.float32)})
    out = tmp_path / "stages.png"
    save_stages(tile, out, dpi=50)
    assert out.stat().st_size > 10_000
