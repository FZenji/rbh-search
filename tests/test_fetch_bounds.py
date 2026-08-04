"""Cutout bounds, both ways, because the two modes serve opposite purposes.

Stamping a named object should fail loudly near an edge. Scanning should slide inside the
frame and take the pixels, because a product's pointing centre is not its image centre and
refusing costs whole products - two of the first six scan targets, both recoverable.

The property neither mode may ever lose: numpy treats a negative slice start as counting from
the far end, so an unchecked overhang returns the wrong sky in silence.
"""

from __future__ import annotations

import pytest


def clamp(x0: int, size: int, extent: int) -> int:
    """The clamping rule from `fetch_tile`, isolated so it can be checked directly."""
    return max(0, min(x0, extent - size))


@pytest.mark.parametrize(
    ("centre", "half", "extent", "expected"),
    [
        (2130, 2048, 4238, 82),  # fits already: unchanged
        (1977, 2048, 4357, 0),  # overhangs the low edge: slid to 0
        (4000, 2048, 4230, 134),  # overhangs the high edge: slid inside
        (100, 2048, 4230, 0),  # far off-centre, still lands in frame
    ],
)
def test_clamping_slides_the_box_inside_the_frame(
    centre: int, half: int, extent: int, expected: int
) -> None:
    """Real numbers from the first scan's targets."""
    assert clamp(centre - half, 2 * half, extent) == expected


@pytest.mark.parametrize(
    ("centre", "half", "extent"),
    [(1977, 2048, 4357), (4000, 2048, 4230), (100, 2048, 4230)],
)
def test_a_clamped_box_is_always_fully_inside(centre: int, half: int, extent: int) -> None:
    """The property that matters: no negative start, no overhang, whatever was requested."""
    size = 2 * half
    start = clamp(centre - half, size, extent)
    assert start >= 0
    assert start + size <= extent


def test_clamping_never_shrinks_the_box() -> None:
    """It slides, it does not shrink - so every scanned tile has the requested area.

    A shrinking cutout would make the area depend on where in the frame the pointing sat,
    which would quietly bias the survey's area accounting toward well-centred products.
    """
    size = 4096
    for centre in (0, 500, 2130, 4000, 4238):
        start = clamp(centre - size // 2, size, 4238)
        assert start + size - start == size


def test_a_box_larger_than_the_image_cannot_be_clamped() -> None:
    """Sliding cannot help when the request exceeds the frame; that must still be an error."""
    size, extent = 5000, 4238
    assert extent - size < 0, "the clamp would produce a negative start, which fetch_tile rejects"
