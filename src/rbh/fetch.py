"""Fetch tiles from the MAST cloud copy of the archive.

This is the only module that reaches the network. Everything else works on a
:class:`~rbh.tile.Tile`, whether it came from here or from a committed fixture, so tests
and CI never need connectivity (ADR-0002, ADR-0010).

Reads are byte-range requests via ``fsspec``: opening a 4300x4200 mosaic and taking a
400x400 section transfers only the section, not the file.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS

from rbh.tile import BandImage, Tile, ab_zeropoint

if TYPE_CHECKING:
    from collections.abc import Sequence

#: Drizzled, cosmic-ray-rejected products are the search plane (ADR-0003).
DRIZZLED_SUFFIX = "_drc.fits"


def find_drizzled_products(obs_ids: Sequence[str]) -> list[str]:
    """Return cloud URIs of the drizzled science products for the given observations.

    Note that not every MAST product has a cloud counterpart. In particular the Hubble
    Advanced Products single-visit mosaics were **not** resolvable in ``s3://stpubdata``
    when this was written, while the standard association ``_drc.fits`` products were;
    both are drizzled and cosmic-ray-rejected, so the search plane is unaffected. See
    ADR-0003 for the amended position.
    """
    from astroquery.mast import Observations

    Observations.enable_cloud_dataset(provider="AWS")
    uris: set[str] = set()
    for obs_id in obs_ids:
        observations = Observations.query_criteria(obs_id=obs_id)
        products = Observations.get_product_list(observations)
        science = Observations.filter_products(products, productType="SCIENCE", extension="fits")
        uris |= {
            uri
            for uri in Observations.get_cloud_uris(science)
            if uri and uri.endswith(DRIZZLED_SUFFIX)
        }
    return sorted(uris)


def fetch_tile(
    ra_deg: float,
    dec_deg: float,
    uris: Sequence[str],
    *,
    half_size_pixels: int = 200,
    proposal_id: str = "",
) -> Tile:
    """Stream a square cutout centred on a sky position from each of ``uris``.

    All products must share a pixel grid definition, which holds for products drizzled
    from the same visit. The WCS of the first is carried onto the tile.
    """
    if not uris:
        msg = "no product URIs given"
        raise ValueError(msg)

    target = SkyCoord(ra_deg, dec_deg, unit="deg")
    bands: list[BandImage] = []
    tile_wcs: WCS | None = None
    pixel_scale = 0.0

    for uri in uris:
        with fits.open(
            uri, use_fsspec=True, fsspec_kwargs={"anon": True}, lazy_load_hdus=True
        ) as hdul:
            primary = hdul[0].header
            filter_name = _filter_name(primary)
            wcs = WCS(hdul[1].header)
            x, y = (float(v) for v in wcs.world_to_pixel(target))
            x0 = round(x) - half_size_pixels
            y0 = round(y) - half_size_pixels
            size = 2 * half_size_pixels
            height, width = hdul[1].shape

            # Bounds must be checked explicitly. A negative slice start is not an error in
            # numpy - it counts from the far end of the array - so an out-of-bounds request
            # would silently return pixels from the wrong part of the sky rather than fail.
            if x0 < 0 or y0 < 0 or x0 + size > width or y0 + size > height:
                msg = (
                    f"cutout [{y0}:{y0 + size}, {x0}:{x0 + size}] falls outside the "
                    f"{height}x{width} image for {ra_deg:.6f} {dec_deg:+.6f}"
                )
                raise ValueError(msg)

            section = (slice(y0, y0 + size), slice(x0, x0 + size))
            science = np.asarray(hdul[1].section[section], dtype=np.float32)
            weight = np.asarray(hdul[2].section[section], dtype=np.float32)
            if science.shape != (size, size):
                msg = f"expected a {size}x{size} cutout, got {science.shape}"
                raise ValueError(msg)

            header = hdul[1].header.copy()
            header["CRPIX1"] -= x0
            header["CRPIX2"] -= y0
            if tile_wcs is None:
                tile_wcs = WCS(header)
                pixel_scale = float(abs(wcs.proj_plane_pixel_scales()[0].to("arcsec").value))
            zeropoint = ab_zeropoint(float(header["PHOTFLAM"]), float(header["PHOTPLAM"]))

        bands.append(
            BandImage(
                filter_name=filter_name,
                science=science,
                weight=weight,
                zeropoint_ab=zeropoint,
            )
        )

    assert tile_wcs is not None
    return Tile(
        bands=tuple(sorted(bands, key=lambda b: b.filter_name)),
        wcs=tile_wcs,
        pixel_scale_arcsec=pixel_scale,
        provenance={
            "source_uri": ";".join(uris),
            "proposal_id": proposal_id,
            "instrument": str(uris[0].split("/")[3]).upper(),
            "target_ra_deg": f"{ra_deg:.6f}",
            "target_dec_deg": f"{dec_deg:.6f}",
            "fetched_from": "s3://stpubdata",
        },
    )


def _filter_name(primary_header: fits.Header) -> str:
    """Resolve the filter name from an HST primary header.

    ACS records two filter wheels, one of which reads ``CLEAR*`` when unused, so taking
    ``FILTER1`` blindly mislabels every F814W exposure.
    """
    for key in ("FILTER1", "FILTER2", "FILTER"):
        value = str(primary_header.get(key, "")).strip().upper()
        if value and not value.startswith("CLEAR"):
            return value
    msg = "could not determine filter name from header"
    raise ValueError(msg)
