"""Looking at a three-dimensional layout from somewhere.

A port of the camera the graph facet has always used, moved off the leaf so
that one geometry decides the picture. The reasoning it carries was paid for
twice in complaints about the picture pumping as it turned, and none of it is
re-derived here:

- the centre is the LAYOUT's own middle, not the origin — a layout whose
  middle is elsewhere orbits around a point outside itself, swings across the
  panel and sits low at rest;
- the focal distance comes from the layout's reach (`max(900, reach * 9)`),
  which bounds how much nearness can change a node's size no matter how far
  you rotate;
- the fit is a BOUND, not a sample, and belongs to the layout and the room
  rather than to the angle. A node's projected offset cannot exceed its
  distance from the axis it turns around, so the frame that holds one angle
  holds every angle. Sampling angles left the widest silhouettes — which
  fall between samples — hanging over the edge, and the picture appeared to
  zoom as it turned.
"""

from __future__ import annotations

from math import cos, hypot, sin

__all__ = ["Placed", "fit", "focal", "middle", "project"]

Placed = dict[str, tuple[float, float, float]]


def middle(places: Placed) -> tuple[float, float, float]:
    """The layout's own middle — what an orbit turns around."""
    n = len(places)
    if not n:
        return (0.0, 0.0, 0.0)
    return (
        sum(x for x, _y, _z in places.values()) / n,
        sum(y for _x, y, _z in places.values()) / n,
        sum(z for _x, _y, z in places.values()) / n,
    )


def focal(places: Placed, at: tuple[float, float, float]) -> float:
    """Near and far no wider than about 1.25:1 — depth reads, size stays put."""
    cx, cy, cz = at
    reach = max(
        (hypot(x - cx, y - cy, z - cz) for x, y, z in places.values()), default=0.0
    )
    return max(900.0, reach * 9)


def fit(places: Placed, wide: float, tall: float) -> float:
    """How much of the room the layout takes — per layout and per room, once."""
    cx, cy, cz = middle(places)
    radial = vertical = near = 0.0
    for x, y, z in places.values():
        dx, dy, dz = x - cx, y - cy, z - cz
        radial = max(radial, hypot(dx, dz))
        vertical = max(vertical, hypot(dy, dz))
        near = max(near, hypot(dx, dy, dz))
    f = focal(places, (cx, cy, cz))
    closest = f / max(f * 0.4, f - near)  # the biggest scale any angle reaches
    return min(
        max(60.0, wide - 60) / max(40.0, 2 * radial * closest),
        max(60.0, tall - 60) / max(40.0, 2 * vertical * closest),
        2.4,
    )


def project(
    places: Placed,
    yaw: float,
    pitch: float,
    wide: float,
    tall: float,
    zoom: float = 1.0,
) -> dict[str, tuple[float, float, float]]:
    """Every place as a point on the glass, with the scale it was drawn at.

    :returns: name → (x, y, nearness); nearness is the projected scale, so a
        node in front of the middle reads larger than one behind it.
    """
    if not places:
        return {}
    cx, cy, cz = middle(places)
    f = focal(places, (cx, cy, cz))
    k = fit(places, wide, tall) * zoom
    cyaw, syaw = cos(yaw), sin(yaw)
    cpit, spit = cos(pitch), sin(pitch)
    out: dict[str, tuple[float, float, float]] = {}
    for name, (px, py, pz) in places.items():
        dx, dy, dz = px - cx, py - cy, pz - cz
        x = dx * cyaw + dz * syaw
        z = -dx * syaw + dz * cyaw
        y = dy * cpit - z * spit
        z = dy * spit + z * cpit
        s = f / max(f * 0.4, f - z)  # no pole, no mirror
        out[name] = (wide / 2 + x * s * k, tall / 2 + y * s * k, s)
    return out
