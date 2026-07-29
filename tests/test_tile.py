"""Tile assembly, noise maps, and the round trip through FITS."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from conftest import SHAPE, draw_line, make_tile, make_wcs
from rbh.tile import BandImage, Tile, ab_zeropoint
from rbh.tileio import read_tile, write_tile


def test_ab_zeropoint_matches_the_published_acs_value() -> None:
    """ACS/WFC F606W is a well-known 26.49 in AB."""
    assert ab_zeropoint(7.9070447e-20, 5921.8931) == pytest.approx(26.49, abs=0.01)


def test_mismatched_science_and_weight_shapes_are_rejected() -> None:
    with pytest.raises(ValueError, match="shapes differ"):
        BandImage(
            filter_name="F606W",
            science=np.zeros((10, 10), dtype=np.float32),
            weight=np.zeros((10, 11), dtype=np.float32),
            zeropoint_ab=26.0,
        )


def test_tile_requires_bands_on_a_common_grid() -> None:
    def band(name: str, shape: tuple[int, int]) -> BandImage:
        return BandImage(
            filter_name=name,
            science=np.zeros(shape, dtype=np.float32),
            weight=np.ones(shape, dtype=np.float32),
            zeropoint_ab=26.0,
        )

    with pytest.raises(ValueError, match="not on a common grid"):
        Tile(
            bands=(band("A", (10, 10)), band("B", (12, 12))),
            wcs=make_wcs(),
            pixel_scale_arcsec=0.05,
            provenance={},
        )


def test_empty_tile_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one band"):
        Tile(bands=(), wcs=make_wcs(), pixel_scale_arcsec=0.05, provenance={})


def test_tier_reflects_filter_count(noise_field: np.ndarray) -> None:
    assert make_tile({"F606W": noise_field}).tier == "B"
    assert make_tile({"F606W": noise_field, "F814W": noise_field}).tier == "A"


def test_band_lookup_reports_available_filters(noise_field: np.ndarray) -> None:
    tile = make_tile({"F606W": noise_field})
    assert tile.band("F606W").filter_name == "F606W"
    with pytest.raises(KeyError, match="F814W"):
        tile.band("F814W")


def test_noise_map_scales_as_inverse_root_weight(noise_field: np.ndarray) -> None:
    tile = make_tile({"F606W": noise_field}, weight_value=1000.0)
    band = tile.bands[0]
    band.weight[:, 128:] = 250.0  # a quarter of the exposure
    noise = band.noise_map()
    deep = float(np.median(noise[:, :128]))
    shallow = float(np.median(noise[:, 128:]))
    assert shallow / deep == pytest.approx(2.0, rel=0.01)


def test_uncovered_pixels_get_infinite_noise(noise_field: np.ndarray) -> None:
    tile = make_tile({"F606W": noise_field})
    band = tile.bands[0]
    band.weight[0, 0] = 0.0
    assert math.isinf(float(band.noise_map()[0, 0]))


def test_stacking_two_bands_beats_one(noise_field: np.ndarray, rng: np.random.Generator) -> None:
    """The combined image must be quieter than either band alone."""
    other = rng.normal(0.0, 1.0, size=SHAPE).astype(np.float32)
    one = make_tile({"F606W": noise_field})
    two = make_tile({"F606W": noise_field, "F814W": other})
    _, noise_one = one.detection_image()
    _, noise_two = two.detection_image()
    ratio = float(np.median(noise_two)) / float(np.median(noise_one))
    assert ratio == pytest.approx(1 / math.sqrt(2), rel=0.05)


def test_detection_image_is_background_subtracted(noise_field: np.ndarray) -> None:
    tile = make_tile({"F606W": (noise_field + 17.0).astype(np.float32)})
    image, _ = tile.detection_image()
    assert float(np.median(image)) == pytest.approx(0.0, abs=0.05)


def test_tile_round_trips_through_fits(tmp_path: Path, noise_field: np.ndarray) -> None:
    line = draw_line(SHAPE, length_pixels=100.0, width_pixels=3.0, angle_deg=20.0, amplitude=8.0)
    tile = make_tile(
        {"F606W": (noise_field + line).astype(np.float32), "F814W": noise_field},
        zeropoints={"F606W": 26.485, "F814W": 25.933},
    )
    path = tmp_path / "tile.fits"
    write_tile(tile, path)
    restored = read_tile(path)

    assert restored.filter_names == tile.filter_names
    assert restored.tier == tile.tier
    assert restored.pixel_scale_arcsec == pytest.approx(tile.pixel_scale_arcsec)
    assert restored.band("F606W").zeropoint_ab == pytest.approx(26.485)

    # Compression is lossy by design; the error must stay far below the noise.
    original = tile.band("F606W").science
    error = np.abs(restored.band("F606W").science - original).max()
    assert error < 0.05 * float(original.std())


def test_long_provenance_uris_survive_the_round_trip(
    tmp_path: Path, noise_field: np.ndarray
) -> None:
    """Source URIs must come back byte-identical, however long (ADR-0012).

    A FITS card holds 68 characters and two semicolon-joined S3 URIs are about 118, so an
    implementation that truncates instead of using CONTINUE silently destroys the record of
    which bytes a result came from.
    """
    uris = (
        "s3://stpubdata/hst/public/jety/jety02010/jety02010_drc.fits;"
        "s3://stpubdata/hst/public/jety/jety02020/jety02020_drc.fits"
    )
    assert len(uris) > 68
    tile = make_tile({"F606W": noise_field})
    tile = Tile(
        bands=tile.bands,
        wcs=tile.wcs,
        pixel_scale_arcsec=tile.pixel_scale_arcsec,
        provenance={"source_uri": uris, "proposal_id": "GO-16912"},
    )
    path = tmp_path / "tile.fits"
    write_tile(tile, path)
    restored = read_tile(path)
    assert restored.provenance["source_uri"] == uris
    assert restored.provenance["source_uri"].count("s3://") == 2


def test_round_trip_preserves_world_coordinates(tmp_path: Path, noise_field: np.ndarray) -> None:
    tile = make_tile({"F606W": noise_field})
    path = tmp_path / "tile.fits"
    write_tile(tile, path)
    restored = read_tile(path)
    before = tile.wcs.pixel_to_world(100.0, 120.0)
    after = restored.wcs.pixel_to_world(100.0, 120.0)
    assert before.separation(after).arcsec < 1e-6
