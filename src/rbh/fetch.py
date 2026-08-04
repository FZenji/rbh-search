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
    clamp_to_image: bool = False,
) -> Tile:
    """Stream a square cutout centred on a sky position from each of ``uris``.

    All products must share a pixel grid definition, which holds for products drizzled
    from the same visit. The WCS of the first is carried onto the tile.

    ``clamp_to_image`` chooses between two genuinely different jobs. Cutting a stamp around a
    *named object* should fail loudly if the object is too near an edge to image properly -
    that is the default. **Scanning wants the opposite**: a product's pointing centre is not
    its image centre, so a full-size box around it frequently overhangs an edge, and refusing
    is pure loss. Measured on the first scan, two of six targets were skipped for exactly
    this, both in images where the same box fits perfectly once slid inside the frame.

    Clamping slides the box, it never shrinks or re-centres silently: the returned tile
    carries its own WCS, so where it actually looked is always answerable, and the survey area
    is computed from that footprint rather than from the request (ADR-0019).
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

            # Bounds must be handled explicitly either way. A negative slice start is not an
            # error in numpy - it counts from the far end of the array - so an unchecked
            # out-of-bounds request returns pixels from the wrong part of the sky in silence.
            if clamp_to_image:
                if size > width or size > height:
                    msg = (
                        f"a {size}x{size} cutout does not fit in the {height}x{width} image "
                        f"at all; reduce half_size_pixels"
                    )
                    raise ValueError(msg)
                x0 = max(0, min(x0, width - size))
                y0 = max(0, min(y0, height - size))
            elif x0 < 0 or y0 < 0 or x0 + size > width or y0 + size > height:
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


#: Instruments ADR-0001 puts in scope, spelled the way CAOM spells them.
#:
#: **These strings are load-bearing and fail silently when wrong.** ``NIRCAM`` was the first
#: guess and returns exactly zero products, which would have dropped JWST from the survey
#: without raising anything; the archive calls it ``NIRCAM/IMAGE``. There is a network test
#: asserting every name here returns a non-zero count, because that is the only thing that
#: distinguishes a typo from an instrument that genuinely has no data.
#:
#: ``NIRCAM/CORON`` exists and is deliberately excluded: coronagraphic imaging is a masked,
#: heavily processed mode that shares neither the artifact population nor the selection
#: function measured for wide-field imaging.
SURVEY_INSTRUMENTS = ("ACS/WFC", "WFC3/UVIS", "WFC3/IR", "NIRCAM/IMAGE")

#: Measured corpus size per instrument, 2026-08-04, before the Galactic latitude cut and
#: before deduplication. Recorded so a sweep can be sized without asking the archive, and so
#: a future count that differs by an order of magnitude is visibly a query problem rather
#: than an archive that grew.
CORPUS_COUNTS = {
    "ACS/WFC": 183_637,
    "WFC3/UVIS": 185_072,
    "WFC3/IR": 152_601,
    "NIRCAM/IMAGE": 11_518,
}


def count_products(instruments: Sequence[str] = SURVEY_INSTRUMENTS) -> dict[str, int]:
    """Count drizzled science images per instrument, without downloading the table.

    Roughly ten seconds per instrument, against five and a half minutes for the full query -
    :func:`discover_products` has to pull every row before it can filter any. Size the job
    with this first.
    """
    from astroquery.mast import Observations

    return {
        instrument: int(
            Observations.query_criteria_count(
                dataproduct_type="image",
                intentType="science",
                calib_level=DRIZZLED_CALIB_LEVEL,
                instrument_name=instrument,
            )
        )
        for instrument in instruments
    }


#: Calibration level 3 is CAOM's marker for a combined, drizzled product - the search plane
#: ADR-0003 fixes. Levels 1 and 2 are raw and per-exposure calibrated, which carry cosmic
#: rays that would manufacture exactly the linear artifacts this search is vulnerable to.
DRIZZLED_CALIB_LEVEL = 3


def _text(row: object, column: str, default: str = "") -> str:
    """Read a column as text, tolerating absence and masked values.

    Thirty years of archive metadata has gaps in every column, and a manifest build must
    degrade rather than raise on one bad row.
    """
    value = _raw(row, column)
    return default if value is None else str(value)


def _number(row: object, column: str) -> float | None:
    """Read a column as a float, or None when it is absent, masked or unparseable."""
    value = _raw(row, column)
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _raw(row: object, column: str) -> object:
    """Read a raw column value, returning None for absent or masked entries."""
    try:
        value = row[column]  # type: ignore[index]
    except (KeyError, IndexError, TypeError):
        return None
    if value is None or bool(getattr(value, "mask", False)):
        return None
    return value


def discover_products(
    *,
    instruments: Sequence[str] = SURVEY_INSTRUMENTS,
    min_galactic_latitude_deg: float = 20.0,
    limit: int | None = None,
) -> list[dict[str, object]]:
    """Query MAST CAOM for the drizzled extragalactic corpus of ADR-0001.

    Returns plain dictionaries rather than :class:`~rbh.manifest.Product` objects, because
    two of a Product's fields cannot come from CAOM: the 5-sigma limiting magnitude has to be
    measured from a weight map (ADR-0018) and the ETag from the object store. Keeping the
    network layer to what the archive actually said avoids inventing the rest.

    **The Galactic latitude cut is applied here, in the query result rather than in the
    query**, because CAOM indexes equatorial coordinates and asking it to filter on Galactic
    latitude would either be unsupported or force a full scan. The corpus is small enough in
    row count that filtering client-side is free.

    **``limit`` truncates the result, it does not shorten the query.** The archive returns
    the whole table before anything here can filter it, so a five-row request costs the same
    five and a half minutes as the full one - measured, on ACS/WFC alone. Use
    :func:`count_products` to size a job; ``limit`` is only for keeping test output small.

    This endpoint is the least reliable component in the pipeline - it times out regularly
    and is slow when it does not, which is why every other part of Phase 3 was built to be
    testable without it.
    """
    from astropy.coordinates import SkyCoord
    from astroquery.mast import Observations

    rows: list[dict[str, object]] = []
    for instrument in instruments:
        table = Observations.query_criteria(
            dataproduct_type="image",
            intentType="science",
            calib_level=DRIZZLED_CALIB_LEVEL,
            instrument_name=instrument,
        )
        if table is None or len(table) == 0:
            continue

        for row in table:
            ra = _number(row, "s_ra")
            dec = _number(row, "s_dec")
            if ra is None or dec is None:
                continue
            latitude = float(SkyCoord(ra, dec, unit="deg").galactic.b.deg)
            if abs(latitude) <= min_galactic_latitude_deg:
                continue

            rows.append(
                {
                    "obs_id": _text(row, "obs_id"),
                    "instrument": _text(row, "instrument_name", instrument),
                    "filter_name": _text(row, "filters"),
                    "exposure_seconds": _number(row, "t_exptime") or 0.0,
                    "ra_deg": ra,
                    "dec_deg": dec,
                    "galactic_latitude_deg": latitude,
                    # The archive's own footprint polygon. Strictly better than a disc, and
                    # the reason rbh.footprint prefers it - see product_footprint.
                    "s_region": _text(row, "s_region"),
                    "proposal_id": _text(row, "proposal_id"),
                }
            )
            if limit is not None and len(rows) >= limit:
                return sorted(rows, key=lambda r: str(r["obs_id"]))

    # Sorted so a manifest built from this is deterministic regardless of the order MAST
    # happened to return rows in (ADR-0012).
    return sorted(rows, key=lambda r: str(r["obs_id"]))
