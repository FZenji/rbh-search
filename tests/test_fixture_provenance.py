"""The committed fixture must be able to say where it came from.

ADR-0012 requires that the exact source bytes behind any result be identifiable. For the
fixture that means its recorded provenance has to name a usable product URI for every band it
contains - otherwise the tile cannot be regenerated, and `rbh fetch-destinations`, which
resolves URIs from exactly this card, quietly builds single-filter tiles.

A round-trip test already covers the *writer*. This covers the artifact, which is a different
thing: the writer was fixed and the fixture on disk kept the old truncated value for weeks,
with every test passing.
"""

from __future__ import annotations

from pathlib import Path

from astropy.io import fits

from rbh.tileio import read_tile

FIXTURE = Path(__file__).parent / "data" / "rbh1_acs_f606w_f814w.fits"

#: The 68-character limit of a single FITS card. Longer values need the CONTINUE convention,
#: which astropy applies automatically - an earlier writer truncated instead.
FITS_CARD_VALUE_LIMIT = 68


def usable_uris(provenance: str) -> list[str]:
    """The URIs a caller could actually fetch, which is what `_resolve_uris` keeps."""
    return [u for u in provenance.split(";") if u.startswith("s3://") and u.endswith(".fits")]


def test_the_fixture_names_a_product_for_every_band() -> None:
    """One URI per filter, or the tile cannot be reconstructed from its own record."""
    tile = read_tile(FIXTURE)
    uris = usable_uris(tile.provenance.get("source_uri", ""))
    assert len(uris) == len(tile.bands), (
        f"{len(tile.bands)} bands but {len(uris)} usable URIs: {uris}"
    )


def test_the_provenance_survived_the_card_length_limit() -> None:
    """The specific failure: a value of exactly 68 characters is a truncation, not a value.

    The fixture carried `...jety02010_drc.fits;s3://stp` for weeks - two bands, one usable
    URI - because it was written before the CONTINUE fix and nothing checked the artifact
    afterwards.
    """
    with fits.open(FIXTURE) as hdul:
        recorded = str(hdul[0].header["SRCURI"])
    assert len(recorded) > FITS_CARD_VALUE_LIMIT, (
        "SRCURI fits in one card, which for two URIs means it was truncated"
    )
    assert not recorded.endswith("s3://stp"), "the old truncated value is back"


def test_every_recorded_uri_is_well_formed() -> None:
    tile = read_tile(FIXTURE)
    for uri in tile.provenance.get("source_uri", "").split(";"):
        assert uri.startswith("s3://stpubdata/"), f"{uri!r} is not a MAST public product"
        assert uri.endswith("_drc.fits"), f"{uri!r} is not a drizzled product (ADR-0003)"
