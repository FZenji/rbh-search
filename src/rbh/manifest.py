"""The survey manifest: every archive product we intend to search, and what it covers.

ADR-0001 makes the corpus "every public, drizzled, extragalactic imaging mosaic" with the
unique sky area published as a first-class product. ADR-0014 puts the manifest in Parquet
and the footprint in a MOC. ADR-0019 makes the *effective* area - sky weighted by
completeness at its depth - the denominator of every density limit, which means the manifest
has to carry a depth per product, not just a URI.

This module is deliberately offline. Discovering products is a network operation and lives
in :mod:`rbh.fetch`; everything here operates on the result, so the parts that decide what
the survey *is* can be tested without touching MAST - whose query endpoint is the least
reliable component in the whole pipeline.

Determinism (ADR-0012): products sort by a stable key before anything is written, so the
same inputs always produce byte-identical manifests regardless of the order the archive
returned them in.
"""

from __future__ import annotations

import itertools
import json
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from pathlib import Path

#: Galactic latitude floor from ADR-0001. Below this the sky is crowded with foreground
#: stars, which both hides wakes and manufactures linear artifacts from diffraction spikes.
MIN_GALACTIC_LATITUDE_DEG = 20.0


@dataclass(frozen=True)
class Product:
    """One drizzled archive mosaic, with everything needed to search it and to count it.

    ``etag`` is part of the identity, not decoration: archives re-reduce products in place,
    and a manifest that ignored it would let a re-run silently mix results computed from
    different pixels (ADR-0020 makes the same point about work units).
    """

    uri: str
    etag: str
    instrument: str
    filter_name: str
    exposure_seconds: float
    ra_deg: float
    dec_deg: float
    galactic_latitude_deg: float
    #: 5-sigma point-source limiting magnitude. The quantity ADR-0018 showed predicts wake
    #: completeness, and the reason this is a manifest column rather than a runtime lookup.
    point_source_limit_mag: float
    area_arcmin2: float

    def sort_key(self) -> tuple[str, str, str]:
        """Stable ordering key. URI last, as the tiebreaker that is guaranteed unique."""
        return (self.instrument, self.filter_name, self.uri)


def is_extragalactic(product: Product) -> bool:
    """Whether a product clears ADR-0001's Galactic latitude floor."""
    return abs(product.galactic_latitude_deg) > MIN_GALACTIC_LATITUDE_DEG


def filters_by_position(products: Iterable[Product]) -> dict[tuple[float, float], set[str]]:
    """Which filters cover each pointing, keyed by rounded coordinate.

    Rounded to a thousandth of a degree - about 3.6 arcsec - because products of the same
    field carry coordinates that differ in the last decimals, and treating those as distinct
    pointings would report every field as single-filter and fail ADR-0006's tier test.
    """
    grouped: dict[tuple[float, float], set[str]] = {}
    for product in products:
        key = (round(product.ra_deg, 3), round(product.dec_deg, 3))
        grouped.setdefault(key, set()).add(product.filter_name)
    return grouped


def tier_of(filter_count: int) -> str:
    """Search tier from the number of filters on a pointing (ADR-0006).

    Two or more filters allow the cross-filter check that rejects most artifacts; one filter
    is searchable but yields a weaker candidate, and the distinction has to survive into the
    catalogue rather than being decided silently at sweep time.
    """
    return "A" if filter_count >= 2 else "B"


@dataclass(frozen=True)
class Manifest:
    """An ordered, deduplicated set of products, plus the accounting that goes with it."""

    products: tuple[Product, ...]

    @classmethod
    def build(cls, products: Iterable[Product], *, extragalactic_only: bool = True) -> Manifest:
        """Filter, deduplicate and sort. The only way a Manifest should be constructed.

        Deduplication is by URI: an archive query can return the same product through more
        than one route, and counting it twice would inflate the survey area, which is the
        denominator of every limit.
        """
        seen: dict[str, Product] = {}
        for product in products:
            if extragalactic_only and not is_extragalactic(product):
                continue
            seen.setdefault(product.uri, product)
        return cls(products=tuple(sorted(seen.values(), key=lambda p: p.sort_key())))

    def __len__(self) -> int:
        return len(self.products)

    def raw_area_arcmin2(self) -> float:
        """Return the summed product area, **with overlaps counted repeatedly**.

        Not the survey area, and named so it cannot be mistaken for it. The real number needs
        the MOC union of the footprints; this is the upper bound you get for free, and the
        ratio between the two is a useful measure of how much the corpus overlaps itself.
        """
        return sum(p.area_arcmin2 for p in self.products)

    def tiers(self) -> dict[str, int]:
        """Count of pointings per ADR-0006 tier."""
        counts: dict[str, int] = {"A": 0, "B": 0}
        for filters in filters_by_position(self.products).values():
            counts[tier_of(len(filters))] += 1
        return counts

    def depth_histogram(self, edges: Sequence[float]) -> dict[str, int]:
        """Products per band of limiting magnitude, so the depth spread is visible up front.

        ADR-0018 exists because this distribution is wide. Printing it at manifest time is
        the cheapest possible check that the depth axis covers the corpus it will be applied
        to - and a warning if the corpus reaches outside the range that was measured.
        """
        counts = {f"<{edges[0]:.1f}": 0}
        for low, high in itertools.pairwise(edges):
            counts[f"{low:.1f}-{high:.1f}"] = 0
        counts[f">{edges[-1]:.1f}"] = 0

        for product in self.products:
            depth = product.point_source_limit_mag
            if depth < edges[0]:
                counts[f"<{edges[0]:.1f}"] += 1
            elif depth >= edges[-1]:
                counts[f">{edges[-1]:.1f}"] += 1
            else:
                for low, high in itertools.pairwise(edges):
                    if low <= depth < high:
                        counts[f"{low:.1f}-{high:.1f}"] += 1
                        break
        return counts

    def to_json(self, path: Path) -> Path:
        """Write the manifest deterministically.

        JSON rather than the Parquet ADR-0014 specifies, for now: the manifest is small
        during development and a text format is diffable, which matters more while its schema
        is still moving. Parquet before the production sweep, when it stops being small.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "n_products": len(self.products),
            "raw_area_arcmin2": self.raw_area_arcmin2(),
            "tiers": self.tiers(),
            "products": [asdict(p) for p in self.products],
        }
        path.write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")
        return path

    @classmethod
    def from_json(cls, path: Path) -> Manifest:
        """Read a manifest back, re-sorting rather than trusting the file's order."""
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls.build((Product(**row) for row in payload["products"]), extragalactic_only=False)
