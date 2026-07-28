"""Reading and writing tiles as FITS.

Tiles are stored with RICE compression and quantisation, which is what the archives
themselves do for floating-point image data. At ``quantize_level=16`` the largest pixel
change measured on the RBH-1 fixture was 1.7% of the noise - irrelevant to detection -
while the file shrank from 2.5 MB to 0.65 MB, bringing it inside the repository's
committed-fixture limit (ADR-0010).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS

from rbh.tile import BandImage, Tile

if TYPE_CHECKING:
    from pathlib import Path

#: Quantisation level for RICE compression of science arrays.
QUANTIZE_LEVEL = 16

#: Provenance keys promoted to primary-header cards, with their FITS keywords.
_PROVENANCE_CARDS = {
    "source_uri": "SRCURI",
    "proposal_id": "PROPOSID",
    "instrument": "INSTRUME",
    "target_ra_deg": "TARGRA",
    "target_dec_deg": "TARGDEC",
    "fetched_from": "FETCHSRC",
}


def write_tile(tile: Tile, path: Path) -> None:
    """Write a tile to a compressed FITS file."""
    primary = fits.PrimaryHDU()
    primary.header["PIXSCALE"] = (tile.pixel_scale_arcsec, "arcsec per pixel")
    primary.header["NBANDS"] = (len(tile.bands), "number of filters")
    primary.header["TIER"] = (tile.tier, "filter-coverage tier, see ADR-0006")
    for key, value in sorted(tile.provenance.items()):
        card = _PROVENANCE_CARDS.get(key)
        if card:
            primary.header[card] = str(value)[:68]
        else:
            primary.header.add_history(f"{key}={value}")

    hdus: list[fits.hdu.base.ExtensionHDU] = []
    wcs_header = tile.wcs.to_header()
    for band in tile.bands:
        sci_header = fits.Header(wcs_header)
        sci_header["FILTER"] = (band.filter_name, "filter name")
        sci_header["ZEROPT"] = (band.zeropoint_ab, "AB magnitude zero point")
        hdus.append(
            fits.CompImageHDU(
                band.science.astype(np.float32),
                header=sci_header,
                name=f"{band.filter_name}_SCI",
                compression_type="RICE_1",
                quantize_level=QUANTIZE_LEVEL,
            )
        )
        hdus.append(
            fits.CompImageHDU(
                band.weight.astype(np.float32),
                name=f"{band.filter_name}_WHT",
                compression_type="RICE_1",
                quantize_level=QUANTIZE_LEVEL,
            )
        )
    fits.HDUList([primary, *hdus]).writeto(path, overwrite=True)


def read_tile(path: Path) -> Tile:
    """Read a tile written by :func:`write_tile`."""
    with fits.open(path) as hdul:
        primary = hdul[0].header
        pixel_scale = float(primary["PIXSCALE"])
        provenance = {
            key: str(primary[card]) for key, card in _PROVENANCE_CARDS.items() if card in primary
        }

        filters = [
            hdu.header["FILTER"]
            for hdu in hdul[1:]
            if hdu.name.endswith("_SCI") and "FILTER" in hdu.header
        ]
        if not filters:
            msg = f"{path} contains no science extensions"
            raise ValueError(msg)

        wcs = WCS(hdul[f"{filters[0]}_SCI"].header)
        bands = tuple(
            BandImage(
                filter_name=name,
                science=np.asarray(hdul[f"{name}_SCI"].data, dtype=np.float32),
                weight=np.asarray(hdul[f"{name}_WHT"].data, dtype=np.float32),
                zeropoint_ab=float(hdul[f"{name}_SCI"].header["ZEROPT"]),
            )
            for name in filters
        )

    return Tile(bands=bands, wcs=wcs, pixel_scale_arcsec=pixel_scale, provenance=provenance)
