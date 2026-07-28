"""Shared geometric primitives.

Kept in its own module so that :mod:`rbh.morphology`, :mod:`rbh.linking` and
:mod:`rbh.colour` can all describe a feature's axis the same way without importing one
another.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray


def principal_axis(
    points: NDArray[np.float64],
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Return the unit major and minor axes of a point cloud.

    The sign of the major axis is pinned to a fixed convention rather than left to the
    SVD, whose output sign is arbitrary. Without this, the same feature could be reported
    with its endpoints swapped between runs, and the colour gradient's sign would flip
    with it (ADR-0012).
    """
    _, _, vt = np.linalg.svd(points - points.mean(axis=0), full_matrices=False)
    major = vt[0]
    if major[0] < 0 or (major[0] == 0 and major[1] < 0):
        major = -major
    minor = np.array([-major[1], major[0]])
    return major, minor


def project(
    points: NDArray[np.float64],
    centre: NDArray[np.float64],
    axis: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Project points onto an axis through a centre."""
    return (points - centre) @ axis
