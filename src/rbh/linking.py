"""Join fragments of the same feature back together.

A wake is knotty: bright compact clumps separated by fainter bridges. Any threshold high
enough to reject the noise field will cut some of those bridges, and no single threshold
value avoids it - measured on RBH-1, the feature survives intact up to about 3.5 sigma and
breaks into three pieces by 4 sigma. Tuning to sit just below the break is exactly the
kind of knife-edge that ADR-0010 exists to prevent.

So instead of relying on the threshold to preserve connectivity, we detect fragments and
then explicitly rejoin those that are collinear, close, and consistent with lying on one
straight feature.

This is not free. Linking can also join unrelated collinear noise blobs, so it raises the
false-positive rate by an amount that must be *measured* in injection-recovery rather than
assumed small (ADR-0009). The three tolerances below are the knobs that trade recovered
length against spurious links.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

from rbh.detect import RidgeDetection
from rbh.geometry import principal_axis, project

if TYPE_CHECKING:
    from numpy.typing import NDArray


def _endpoints(
    detection: RidgeDetection,
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    """Return a fragment's centre, unit major axis, and its two extreme points."""
    points = np.column_stack([detection.xs, detection.ys]).astype(np.float64)
    centre = points.mean(axis=0)
    axis, _ = principal_axis(points)
    along = project(points, centre, axis)
    ends = np.array([centre + axis * along.min(), centre + axis * along.max()])
    return centre, axis, ends


def _gap_pixels(ends_a: NDArray[np.float64], ends_b: NDArray[np.float64]) -> float:
    """Smallest distance between any endpoint of A and any endpoint of B."""
    diff = ends_a[:, None, :] - ends_b[None, :, :]
    return float(np.sqrt((diff**2).sum(axis=2)).min())


def _union_axis_and_residual(
    a: RidgeDetection, b: RidgeDetection
) -> tuple[NDArray[np.float64], float]:
    """Return the joint principal axis of two fragments and the RMS scatter about it."""
    points = np.concatenate(
        [
            np.column_stack([a.xs, a.ys]).astype(np.float64),
            np.column_stack([b.xs, b.ys]).astype(np.float64),
        ]
    )
    centre = points.mean(axis=0)
    major, minor = principal_axis(points)
    perpendicular = project(points, centre, minor)
    return major, float(np.sqrt(np.mean(perpendicular**2)))


def _axis_angle_deg(axis_a: NDArray[np.float64], axis_b: NDArray[np.float64]) -> float:
    """Angle between two undirected axes, in degrees."""
    cosine = min(1.0, abs(float(np.dot(axis_a, axis_b))))
    return math.degrees(math.acos(cosine))


def link_collinear(
    detections: list[RidgeDetection],
    pixel_scale_arcsec: float,
    *,
    max_gap_arcsec: float = 1.5,
    max_residual_arcsec: float = 0.35,
    max_angle_deg: float = 15.0,
) -> list[RidgeDetection]:
    """Merge fragments that plausibly belong to a single straight feature.

    Two fragments are joined when all three hold: the gap between their nearest endpoints
    is under ``max_gap_arcsec``, **each** fragment's own axis lies within
    ``max_angle_deg`` of the axis of their union, and the union's RMS scatter about that
    axis stays under ``max_residual_arcsec``. Merging is transitive, so a chain of knots
    links into one feature.

    Comparing each fragment against the *joint* axis rather than against the other
    fragment is what stops two parallel lanes being merged. Their individual axes are
    perfectly parallel, so a fragment-to-fragment angle test sees nothing wrong, while
    the line through both is noticeably tilted with respect to either.

    For reference, the three fragments RBH-1 breaks into differ in position angle by
    about 4 degrees, so the default leaves a wide margin.

    Returns merged detections ordered by descending pixel count, deterministically.
    """
    if len(detections) < 2:
        return list(detections)

    max_gap = max_gap_arcsec / pixel_scale_arcsec
    max_residual = max_residual_arcsec / pixel_scale_arcsec

    geometry = [_endpoints(d) for d in detections]
    parent = list(range(len(detections)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(detections)):
        for j in range(i + 1, len(detections)):
            _, axis_i, ends_i = geometry[i]
            _, axis_j, ends_j = geometry[j]
            if _gap_pixels(ends_i, ends_j) > max_gap:
                continue
            union_axis, residual = _union_axis_and_residual(detections[i], detections[j])
            if residual > max_residual:
                continue
            if (
                max(
                    _axis_angle_deg(axis_i, union_axis),
                    _axis_angle_deg(axis_j, union_axis),
                )
                > max_angle_deg
            ):
                continue
            root_i, root_j = find(i), find(j)
            if root_i != root_j:
                parent[max(root_i, root_j)] = min(root_i, root_j)

    groups: dict[int, list[int]] = {}
    for index in range(len(detections)):
        groups.setdefault(find(index), []).append(index)

    merged: list[RidgeDetection] = []
    for members in groups.values():
        if len(members) == 1:
            merged.append(detections[members[0]])
            continue
        parts = [detections[m] for m in members]
        merged.append(
            RidgeDetection(
                ys=np.concatenate([p.ys for p in parts]),
                xs=np.concatenate([p.xs for p in parts]),
                peak_snr=max(p.peak_snr for p in parts),
                n_pixels=sum(p.n_pixels for p in parts),
            )
        )
    merged.sort(key=lambda d: (-d.n_pixels, int(d.ys[0]), int(d.xs[0])))
    return merged
