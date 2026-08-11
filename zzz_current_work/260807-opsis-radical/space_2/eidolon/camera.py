"""Looking at a three-dimensional layout from somewhere.

space_1 kept this in the leaf, and the two complaints that followed were the
same complaint: the picture resized as it turned. It resized because the
scale was fitted to the projected bounds, and those bounds change with every
degree of rotation. A cloud's RADIUS does not — so the scale is taken from
the radius once, and turning the grammar only turns it.
"""

from __future__ import annotations

from math import cos, sin, sqrt

__all__ = ["Placed", "project"]

Placed = dict[str, tuple[float, float, float]]

LENS = 900.0


def _middle(places: Placed) -> tuple[float, float, float]:
    n = max(1, len(places))
    return (
        sum(x for x, _y, _z in places.values()) / n,
        sum(y for _x, y, _z in places.values()) / n,
        sum(z for _x, _y, z in places.values()) / n,
    )


def radius(places: Placed) -> float:
    """How far the furthest rule sits from the middle — what rotation cannot change."""
    cx, cy, cz = _middle(places)
    return (
        max(
            (
                sqrt((x - cx) ** 2 + (y - cy) ** 2 + (z - cz) ** 2)
                for x, y, z in places.values()
            ),
            default=1.0,
        )
        or 1.0
    )


def project(
    places: Placed, yaw: float, pitch: float, wide: float, tall: float
) -> dict[str, tuple[float, float, float]]:
    """Every place as a point on the glass, with how far away it is.

    :returns: name → (x, y, nearness), nearness in 0..1 with 1 nearest.
    """
    if not places:
        return {}
    cx, cy, cz = _middle(places)
    span = radius(places)
    # the scale is the cloud's, not the frame's: the same grammar is the same
    # size at every angle, and only the room it is drawn in can change it
    scale = min(wide, tall) * 0.42 / span
    sy, cyw = sin(yaw), cos(yaw)
    sp, cp = sin(pitch), cos(pitch)
    out: dict[str, tuple[float, float, float]] = {}
    for name, (x, y, z) in places.items():
        dx, dy, dz = x - cx, y - cy, z - cz
        rx = dx * cyw + dz * sy
        rz = dz * cyw - dx * sy
        ry = dy * cp - rz * sp
        rz = rz * cp + dy * sp
        near = LENS / max(200.0, LENS + rz * scale)
        out[name] = (
            wide / 2 + rx * scale * near,
            tall / 2 + ry * scale * near,
            near,
        )
    return out
