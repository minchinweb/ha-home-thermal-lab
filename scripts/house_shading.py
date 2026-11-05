"""The house's own shading of the kitchen windows (hypothesis 11).

The OpenStreetMap outline (House Structure measures it) is two blocks. In
the house frame, in feet, ``x`` runs east along the wall normal at 100.4 degrees
and ``y`` north at 10.4 degrees, from the kitchen wing's south-west corner:

* the kitchen wing at the back: ``x`` 0 to 13.6, ``y`` 0 to 24.9, with a stub
  out to ``x`` = 15.7 at its north end (``y`` 20.3 to 24.9);
* the main block at the front: ``x`` 13.6 to 40.8, ``y`` -13 to 20.3, with a
  12:12 roof whose ridge runs north to south (gables to the north and south).

The main block casts the shade. The kitchen's east window is in the 4.6 ft stub
of east wall, with the main block's north gable running 25 ft east right beside
it. The patio door is in the wing's south wall, and the main block reaches
13 ft further south just east of it.

Window positions are the owner's measurements: the east window's glass is set
4 in into the wall, and its north edge is 28 in from the inside of the north
wall; the patio door's east edge is 54 in (outside) from the main block's west
wall. The main block's eave height (10 ft above the kitchen floor) is an
estimate from the photo of that wall from the patio door.

``lit_fraction`` traces a ray towards the sun from points across the glass. A
point is shaded when the reveal (jamb, sill or head) or the main block is in
the way.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

ROTATION = 10.4  # degrees clockwise of the house frame from true north


@dataclass(frozen=True)
class Block:
    """A block with a gable roof whose ridge runs along ``y``.

    Attributes:
        x0, x1, y0, y1: Footprint in the house frame, feet.
        eave: Height of the eaves (the top of the long walls), feet.
        pitch: Roof pitch in degrees.
    """

    x0: float
    x1: float
    y0: float
    y1: float
    eave: float
    pitch: float

    def roof(self, x: float) -> float:
        """Roof height at ``x`` (inside the footprint)."""
        rise = math.tan(math.radians(self.pitch))
        return self.eave + rise * min(x - self.x0, self.x1 - x)

    def blocks(self, origin: tuple[float, float, float], sun: tuple) -> bool:
        """Whether the ray from ``origin`` towards ``sun`` passes through."""
        ox, oy, oz = origin
        dx, dy, dz = sun
        horizontal = math.hypot(dx, dy)
        if horizontal < 1e-9:
            return False
        ux, uy, slope = dx / horizontal, dy / horizontal, dz / horizontal
        t_in, t_out = 0.0, math.inf
        for o, u, lo, hi in ((ox, ux, self.x0, self.x1), (oy, uy, self.y0, self.y1)):
            if abs(u) < 1e-12:
                if not lo <= o <= hi:
                    return False
                continue
            a, b = sorted(((lo - o) / u, (hi - o) / u))
            t_in, t_out = max(t_in, a), min(t_out, b)
        if t_in >= t_out:
            return False
        stops = [t_in, t_out]
        if abs(ux) > 1e-12:
            ridge = ((self.x0 + self.x1) / 2 - ox) / ux
            if t_in < ridge < t_out:
                stops.append(ridge)
        return any(oz + slope * t < self.roof(ox + ux * t) for t in stops)


@dataclass(frozen=True)
class Window:
    """A window in a vertical wall.

    Attributes:
        normal: Way the wall faces in the house frame: ``E``, ``S``, ``W``, ``N``.
        a, b: The two ends of the glass along the wall's outer face, (x, y) feet.
        sill, head: Bottom and top of the glass above the kitchen floor, feet.
        reveal: How far the glass is set in from the outer face, feet.
    """

    normal: str
    a: tuple[float, float]
    b: tuple[float, float]
    sill: float
    head: float
    reveal: float


OUTWARD = {"E": (1.0, 0.0), "W": (-1.0, 0.0), "N": (0.0, 1.0), "S": (0.0, -1.0)}

MAIN_BLOCK = Block(13.6, 40.8, -13.0, 20.3, eave=10.0, pitch=45.0)

KITCHEN_EAST = Window(
    "E",
    (15.7, 24.9 - 0.6 - 28 / 12),
    (15.7, 24.9 - 0.6 - 28 / 12 - 1.0),
    sill=2.0,
    head=7.0,
    reveal=4 / 12,
)
PATIO_DOOR = Window(
    "S",
    (13.6 - 54 / 12, 0.0),
    (13.6 - 54 / 12 - 70 / 12, 0.0),
    sill=0.0,
    head=80 / 12,
    reveal=4 / 12,
)
# (room, window wall) -> window the house shades
HOUSE_SHADE = {("Z1 kitchen", "E"): KITCHEN_EAST, ("Z1 kitchen", "S"): PATIO_DOOR}


def sun_vector(azimuth: float, elevation: float, rotation: float = ROTATION):
    """Unit vector towards the sun in the house frame (x east, y north, z up)."""
    turn = math.radians(azimuth - rotation)
    el = math.radians(elevation)
    return (math.cos(el) * math.sin(turn), math.cos(el) * math.cos(turn), math.sin(el))


def lit_fraction(
    window: Window,
    azimuth: float,
    elevation: float,
    rotation: float = ROTATION,
    blocks: tuple[Block, ...] = (MAIN_BLOCK,),
    across: int = 7,
    up: int = 3,
) -> float:
    """Share of the glass in direct sun (0 to 1), for a sun position."""
    if elevation <= 0:
        return 0.0
    sun = sun_vector(azimuth, elevation, rotation)
    nx, ny = OUTWARD[window.normal]
    out = sun[0] * nx + sun[1] * ny
    if out <= 0:
        return 0.0
    (ax, ay), (bx, by) = window.a, window.b
    width = math.hypot(bx - ax, by - ay)
    lit = 0
    for i in range(across):
        s = (i + 0.5) / across
        for j in range(up):
            z = window.sill + (j + 0.5) / up * (window.head - window.sill)
            # where the ray leaves the reveal, at the wall's outer face
            k = window.reveal / out
            px = ax + s * (bx - ax) - nx * window.reveal + sun[0] * k
            py = ay + s * (by - ay) - ny * window.reveal + sun[1] * k
            pz = z + sun[2] * k
            along = ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / width
            if not (0.0 <= along <= width and window.sill <= pz <= window.head):
                continue
            if any(b.blocks((px, py, pz), sun) for b in blocks):
                continue
            lit += 1
    return lit / (across * up)


def house_shade(room, face, azimuth, elevation, rotation: float = ROTATION):
    """Share of a room's window wall the house leaves in sun, per sun position.

    Ones for walls the house does not shade.
    """
    import numpy as np

    window = HOUSE_SHADE.get((room, face))
    if window is None:
        return np.ones(len(azimuth))
    return np.array(
        [
            lit_fraction(window, az, el, rotation)
            for az, el in zip(azimuth, elevation, strict=True)
        ]
    )


def wall_light(room, face, held, azimuth, elevation, rotation: float = ROTATION):
    """Light on a room's window wall: beam (less the house's shade) + half diffuse.

    ``held`` is the irradiance reading per bin (``None`` where missing, giving
    NaN). This is ``Irradiance.on_face`` with the house's own shading.
    """
    import numpy as np

    shade = house_shade(room, face, azimuth, elevation, rotation)
    return np.array(
        [
            h.beam_on_plane(face, 90.0, azimuth[i] - rotation, elevation[i]) * shade[i]
            + h.diffuse_on_plane(90.0, elevation[i])
            if h
            else np.nan
            for i, h in enumerate(held)
        ]
    )
