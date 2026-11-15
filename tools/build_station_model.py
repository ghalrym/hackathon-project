"""Build the space station model used by the game.

    blender -b --factory-startup --python tools/build_station_model.py [-- --renders DIR]

The station is assembled from blocks, tubes and swept rings in game coordinates
(x right, y up, z toward the arriving ship, one unit about four metres). The
origin is where the ship parks, in the middle of a hangar bay that runs
straight through the base of the station. Surfaces carry tiling panel textures
painted here. The result is exported as GLB to assets/models/station.glb.
"""
import math
import os
import sys

import bpy
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PATH = os.path.join(ROOT, "assets", "models", "station.glb")

# ---------------------------------------------------------------- parameters
TEX = 1024

# Hangar bay: a tunnel along z that the ship flies in one end of and out the other.
BAY_W = 22.0        # half width
BAY_FLOOR = -0.7    # the parked ship's belly rests just above this
BAY_TOP = 14.0
BAY_IN = 56.0       # z of the entrance
BAY_OUT = -78.0     # z of the exit
BAY_SHELL = 10.0    # thickness of the hull around the bay
RIB_SPACING = 12.0

# The tower stands on the bay; the habitat ring circles it.
TOWER_Z = (BAY_IN + BAY_OUT) / 2
RING_Y = 84.0
RING_RADIUS = 118.0

# World units covered by one repeat of each material's texture.
TILE = dict(hull=16.0, hull_dark=16.0, deck=8.0, windows=12.0, solar=8.0,
            paint_yellow=4.0, paint_white=4.0)

# Untextured materials: colour, roughness, metallic, emission strength.
FLAT = dict(
    truss=((0.07, 0.075, 0.085), 0.5, 0.9, 0),
    paint_yellow=((0.86, 0.58, 0.04), 0.55, 0.1, 0),
    paint_white=((0.82, 0.84, 0.86), 0.55, 0.1, 0),
    rubber=((0.02, 0.02, 0.022), 0.9, 0.0, 0),
    crate_orange=((0.72, 0.27, 0.06), 0.6, 0.2, 0),
    crate_blue=((0.10, 0.22, 0.38), 0.6, 0.2, 0),
    crate_grey=((0.36, 0.38, 0.40), 0.6, 0.3, 0),
    light_white=((0.91, 0.92, 0.94), 0.4, 0.0, 2.5),
    light_cyan=((0.25, 0.77, 0.88), 0.4, 0.0, 3.1),
    light_amber=((1.0, 0.52, 0.12), 0.4, 0.0, 3.6),
    light_red=((1.0, 0.10, 0.06), 0.4, 0.0, 8.0),
    light_green=((0.10, 1.0, 0.25), 0.4, 0.0, 8.0),
    glass_warm=((1.0, 0.78, 0.48), 0.2, 0.0, 3.0),
)


def unit(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


# --------------------------------------------------------------------- shape
class Shell:
    """Faces collected in game coordinates, to become one Blender mesh."""

    def __init__(self):
        self.points, self.faces, self.uvs = [], [], []
        self.materials, self.smooth = [], []
        self.slots = {}

    def _face(self, corners, uvs, material, smooth=False):
        self.faces.append(tuple(corners))
        self.uvs.extend(uvs)
        self.materials.append(self.slots.setdefault(material, len(self.slots)))
        self.smooth.append(smooth)

    def quad(self, material, origin, across, up):
        """A flat rectangle facing across x up."""
        o, a, u = (np.asarray(v, float) for v in (origin, across, up))
        la, lu = np.linalg.norm(a), np.linalg.norm(u)
        tile = TILE.get(material, 1.0)
        s, t = o @ a / la / tile, o @ u / lu / tile
        start = len(self.points)
        self.points += [o, o + a, o + a + u, o + u]
        self._face(range(start, start + 4), [(s, t), (s + la / tile, t),
                   (s + la / tile, t + lu / tile), (s, t + lu / tile)], material)

    def block(self, material, origin, ex, ey, ez, **sides):
        """A box from one corner and its three edges (ex x ey must point along
        ez). `sides` gives a face (x0, x1, y0, y1, z0, z1) another material, or
        None to leave it out."""
        o, ex, ey, ez = (np.asarray(v, float) for v in (origin, ex, ey, ez))
        for side, corner, across, up in (
                ("x1", o + ex + ez, -ez, ey), ("x0", o, ez, ey),
                ("y1", o + ey + ez, ex, -ez), ("y0", o, ex, ez),
                ("z1", o + ez, ex, ey), ("z0", o + ex, -ex, ey)):
            face_material = sides.get(side, material)
            if face_material:
                self.quad(face_material, corner, across, up)

    def box(self, material, lo, hi, **sides):
        lo, hi = np.minimum(lo, hi), np.maximum(lo, hi)
        d = hi - lo
        self.block(material, lo, (d[0], 0, 0), (0, d[1], 0), (0, 0, d[2]), **sides)

    def tube(self, material, a, b, radius, segments=24, end_radius=None, caps=True, cap_material=None):
        """A cylinder, or a cone if end_radius is given, from a to b."""
        a, b = np.asarray(a, float), np.asarray(b, float)
        length = np.linalg.norm(b - a)
        axis = (b - a) / length
        helper = np.array([1.0, 0, 0]) if abs(axis[1]) > 0.9 else np.array([0, 1.0, 0])
        u = unit(np.cross(helper, axis))
        v = np.cross(axis, u)
        tile = TILE.get(material, 1.0)
        radii = (radius, radius if end_radius is None else end_radius)
        angles = np.linspace(0, 2 * math.pi, segments + 1)
        rim = np.outer(np.cos(angles), u) + np.outer(np.sin(angles), v)
        start = len(self.points)
        self.points += list(a + rim * radii[0]) + list(b + rim * radii[1])
        girth = max(radii) * 2 * math.pi / tile
        for i in range(segments):
            s0, s1 = i / segments * girth, (i + 1) / segments * girth
            self._face((start + i, start + i + 1, start + segments + 2 + i, start + segments + 1 + i),
                       [(s0, 0), (s1, 0), (s1, length / tile), (s0, length / tile)], material, smooth=True)
        if caps:
            for centre, r, order in ((b, radii[1], 1), (a, radii[0], -1)):
                if r <= 1e-6:
                    continue
                start = len(self.points)
                ring = rim[:segments][::order]
                self.points += list(centre + ring * r)
                self._face(range(start, start + segments),
                           [(p @ u * r / tile, p @ v * r / tile) for p in ring], cap_material or material)

    def ball(self, material, centre, radius, segments=20):
        centre = np.asarray(centre, float)
        rings = segments // 2
        start = len(self.points)
        for j in range(rings + 1):
            lat = -math.pi / 2 + math.pi * j / rings
            for i in range(segments + 1):
                lon = 2 * math.pi * i / segments
                self.points.append(centre + radius * np.array(
                    [math.cos(lat) * math.sin(lon), math.sin(lat), math.cos(lat) * math.cos(lon)]))
        for j in range(rings):
            for i in range(segments):
                p = start + j * (segments + 1) + i
                self._face((p, p + 1, p + segments + 2, p + segments + 1), [(0, 0)] * 4, material, smooth=True)

    def sweep(self, centre, profile, materials, segments=96, arc=(0.0, 2 * math.pi)):
        """Spin a closed profile of (radius, height) points, anticlockwise,
        around the vertical axis through `centre`. One material per edge; the
        result is smooth around the ring and creased between edges."""
        centre = np.asarray(centre, float)
        angles = np.linspace(arc[0], arc[1], segments + 1)
        out = np.stack([np.sin(angles), np.zeros_like(angles), np.cos(angles)], axis=1)
        for k, material in enumerate(materials):
            (r0, y0), (r1, y1) = profile[k], profile[(k + 1) % len(profile)]
            tile = TILE.get(material, 1.0)
            width = math.hypot(r1 - r0, y1 - y0) / tile
            start = len(self.points)
            self.points += list(centre + out * r0 + (0, y0, 0)) + list(centre + out * r1 + (0, y1, 0))
            for i in range(segments):
                s0, s1 = (angles[i] * max(r0, r1) / tile, angles[i + 1] * max(r0, r1) / tile)
                self._face((start + i, start + i + 1, start + segments + 2 + i, start + segments + 1 + i),
                           [(s0, 0), (s1, 0), (s1, width), (s0, width)], material, smooth=True)

    def greebles(self, rng, origin, across, up, count, size=(0.5, 3.5), depth=(0.15, 1.2),
                 materials=("hull", "hull_dark", "hull_dark", "truss")):
        """Scatter small boxes over a rectangle, standing out along across x up."""
        o, a, u = (np.asarray(v, float) for v in (origin, across, up))
        la, lu = np.linalg.norm(a), np.linalg.norm(u)
        a, u = a / la, u / lu
        out = np.cross(a, u)
        for _ in range(count):
            w = min(rng.uniform(*size), la * 0.6)
            h = min(rng.uniform(*size) * rng.choice([0.35, 1.0]), lu * 0.6)
            at = o + a * rng.uniform(0, la - w) + u * rng.uniform(0, lu - h)
            self.block(materials[rng.integers(len(materials))], at, a * w, u * h,
                       out * rng.uniform(*depth), z0=None)


def bay(s, rng):
    """The hangar: floor, roof and walls around a tunnel, then everything in it."""
    w, f, t, zi, zo, k = BAY_W, BAY_FLOOR, BAY_TOP, BAY_IN, BAY_OUT, BAY_SHELL
    s.box("hull", (-w - k, f - 9, zo), (w + k, f, zi), y1="deck")
    s.box("hull", (-w - k, t, zo), (w + k, t + 8, zi), y0="hull_dark")
    for side in (-1, 1):
        s.box("hull", (side * w, f, zo), (side * (w + k), t, zi), **{"x0" if side > 0 else "x1": "hull_dark"})
    # Outer hull: raised spine, side blisters, and clutter.
    s.box("hull", (-22, t + 8, zo + 12), (22, t + 13, zi - 14))
    s.box("hull_dark", (-14, t + 13, zo + 26), (14, t + 16, zi - 30))
    for side in (-1, 1):
        s.box("hull_dark", (side * (w + k), 1, zo + 20), (side * (w + k + 4), 11, zi - 24))
        s.greebles(rng, (side * (w + k), f - 9, zi if side > 0 else zo), (0, 0, -side * (zi - zo)), (0, t + 17 - f, 0), 320)
        for z in np.arange(zo + 8, zi - 4, 14.0):
            # Buttresses down the flanks.
            s.box("truss", (side * (w + k), f - 9, z), (side * (w + k + 1.6), t + 8, z + 1.8))
        for z in (zo + 18, zi - 22):
            s.tube("truss", (side * 26, t + 8, z), (side * 16, t + 26, TOWER_Z + (z - TOWER_Z) * 0.25), 1.5, 12)
    s.greebles(rng, (-w - k, t + 8, zi), (2 * (w + k), 0, 0), (0, 0, zo - zi), 420)
    s.greebles(rng, (-w - k, f - 9, zo), (2 * (w + k), 0, 0), (0, 0, zi - zo), 320)

    for z, face in ((zi, 1), (zo, -1)):
        # The end walls: clutter, a windowed bridge over the mouth, painted bands.
        across = (2 * (w + k), 0, 0) if face > 0 else (-2 * (w + k), 0, 0)
        corner = -(w + k) if face > 0 else (w + k)
        s.greebles(rng, (corner, t + 3, z), across, (0, 5, 0), 40, size=(0.5, 3.0))
        s.greebles(rng, (corner, f - 9, z), across, (0, 6, 0), 40, size=(0.5, 3.0))
        for side in (-1, 1):
            edge = side * (w + 3) if side * face > 0 else side * (w + k)
            s.greebles(rng, (edge, f, z), (face * (k - 3), 0, 0), (0, t - f, 0), 26, size=(0.4, 2.4))
        near, far = sorted((z, z + face * 3.2))
        s.box("hull", (-13, t + 3.4, near), (13, t + 7.4, far))
        s.box("windows", (-12.4, t + 4.0, far if face > 0 else near - 0.1), (12.4, t + 6.8, far + 0.1 if face > 0 else near))
        s.box("paint_yellow", (-w - k, f - 4.6, min(z, z + face * 0.08)), (w + k, f - 4.0, max(z, z + face * 0.08)))
        s.box("paint_white", (-w - k, f - 5.5, min(z, z + face * 0.08)), (w + k, f - 4.9, max(z, z + face * 0.08)))
        # Mouth frame, lit round its inner edge.
        lo, hi = sorted((z, z + face * 2.0))
        s.box("truss", (-w - 3, t, lo), (w + 3, t + 3, hi))
        s.box("truss", (-w - 3, f - 3, lo), (w + 3, f, hi))
        for side in (-1, 1):
            s.box("truss", (side * w, f, lo), (side * (w + 3), t, hi))
            s.box("light_cyan", (side * (w - 0.3), f + 0.4, hi - 0.25), (side * (w + 0.3), t - 0.4, hi + 0.1))
        s.box("light_cyan", (-w + 0.4, t - 0.3, hi - 0.25), (w - 0.4, t + 0.3, hi + 0.1))
        # Hazard blocks along the sill.
        for i in range(22):
            x = -w + i * 2 * w / 22
            s.box("paint_yellow" if i % 2 else "rubber", (x, f, z - face * 5), (x + 2 * w / 22, f + 0.05, z))
        # Beacons at the corners.
        for side in (-1, 1):
            s.box("light_red" if side < 0 else "light_green", (side * (w + 2.2) - 0.4, t + 1.2, hi), (side * (w + 2.2) + 0.4, t + 2.0, hi + 0.3 * face))

    # Approach booms reaching out from the entrance, studded with lights.
    for side in (-1, 1):
        for y in (f - 1.5, t + 1.5):
            s.box("truss", (side * (w + 1.5) - 0.6, y - 0.6, zi + 2), (side * (w + 1.5) + 0.6, y + 0.6, zi + 74))
            for i in range(12):
                z = zi + 8 + i * 6
                s.box("light_amber" if i % 3 else "light_white", (side * (w + 1.5) - 0.75, y - 0.3, z), (side * (w + 1.5) + 0.75, y + 0.3, z + 0.6))
        s.box("truss", (side * (w + 1.5) - 0.4, f - 1.5, zi + 40), (side * (w + 1.5) + 0.4, t + 1.5, zi + 41))

    # Ribs: a pillar each side with a light bar, and a beam across the roof.
    ribs = np.arange(zo + 7, zi - 6, RIB_SPACING)
    for z in ribs:
        s.box("truss", (-w, t - 1.2, z - 0.8), (w, t, z + 0.8))
        for side in (-1, 1):
            s.box("truss", (side * (w - 1.6), f, z - 0.8), (side * w, t - 1.2, z + 0.8))
            s.box("light_white", (side * (w - 1.75), 2.0, z - 0.15), (side * (w - 1.6), 11.0, z + 0.15))
    # Roof light panels between the ribs, crane rails, pipes.
    for z in ribs[:-1]:
        for x in (-12, -4, 4, 12):
            s.box("truss", (x - 1.25, t - 0.28, z + 2.0), (x + 1.25, t, z + RIB_SPACING - 2), y1=None)
            for dx in (-0.70,0,0.70):
                s.box("light_white", (x+dx-0.16,t-0.32,z+2.3),(x+dx+0.16,t-0.28,z+RIB_SPACING-2.3), y1=None)
    for side in (-1, 1):
        s.box("truss", (side * 17 - 0.4, t - 2.0, zo + 2), (side * 17 + 0.4, t - 1.2, zi - 2))
        for y, r in ((11.4, 0.35), (12.3, 0.25), (10.6, 0.18)):
            s.tube("truss" if r > 0.2 else "paint_yellow", (side * (w - 0.5), y, zo + 1), (side * (w - 0.5), y, zi - 1), r, 10, caps=False)
    s.box("paint_yellow", (-17.6, t - 2.9, -32), (17.6, t - 2.0, -29))
    s.box("truss", (-3.2, t - 3.6, -31.5), (-1.2, t - 2.9, -29.5))
    s.tube("rubber", (-2.2, t - 3.6, -30.5), (-2.2, t - 6.5, -30.5), 0.06, 6)
    s.box("paint_yellow", (-2.6, t - 7.0, -30.9), (-1.8, t - 6.5, -30.1))

    # Deck markings: centre line, lane edges, guide lights.
    for z in np.arange(zo + 4, zi - 4, 8.0):
        if abs(z + 2) > 9:
            s.box("paint_white", (-0.25, f, z), (0.25, f + 0.05, z + 4), y0=None)
    for side in (-1, 1):
        s.box("paint_yellow", (side * 13 - 0.15, f, zo + 1), (side * 13 + 0.15, f + 0.05, zi - 6), y0=None)
        for z in np.arange(zo + 3, zi - 2, 6.0):
            s.box("light_cyan", (side * 6.5 - 0.22, f, z), (side * 6.5 + 0.22, f + 0.12, z + 0.44), y0=None)
    # Landing pad: painted ring, cross and a circle of lamps.
    for i in range(96):
        angle = 2 * math.pi * i / 96
        radial = np.array([math.sin(angle), 0, math.cos(angle)])
        along = np.array([math.cos(angle), 0, -math.sin(angle)])
        s.block("paint_yellow", radial * 5.6 - along * 0.2 + (0, f, 0), along * 0.4, (0, 0.05, 0), radial * 0.5, y0=None)
        if i % 8 == 0:
            s.block("light_amber", radial * 7.0 - along * 0.2 + (0, f, 0), along * 0.4, (0, 0.14, 0), radial * 0.4, y0=None)
    s.box("paint_white", (-3.4, f, -0.135), (3.4, f + 0.006, 0.135), y0=None)
    s.box("paint_white", (-0.135, f, -3.4), (0.135, f + 0.007, 3.4), y0=None)
    # Flush tie-downs and embedded runway lamp frames give the pad a sense of scale.
    for x in (-4,-2,2,4):
        for z in (-5,-2.5,2.5,5):
            s.tube("truss",(x,f+0.004,z),(x,f+0.026,z),0.13,12)
            s.box("rubber",(x-0.078,f+0.026,z-0.043),(x+0.078,f+0.031,z+0.043),y0=None)
            s.box("truss",(x-0.019,f+0.031,z-0.050),(x+0.019,f+0.042,z+0.050),y0=None)
    for side in (-1,1):
        for z in np.arange(zo+3,zi-2,6.0):
            s.box("truss",(side*6.5-0.31,f+0.005,z-0.09),(side*6.5+0.31,f+0.085,z+0.53),y0=None)
        for z in (-39,29):
            # Station wayfinding plates sit proud of the interior pressure wall.
            x = side*(w-0.65)
            start = len(s.points)
            width = side*6.0
            s.points.extend([(x,5.4,z-width),(x,5.4,z+width),(x,8.4,z+width),(x,8.4,z-width)])
            s._face(range(start,start+4),[(0,0),(1,0),(1,1),(0,1)],"bay_sign")

    # Control room on the left wall, a catwalk on the right.
    s.box("hull", (-w, 5.6, -11), (-w + 3.6, 10.4, 13), x0=None)
    s.box("glass_warm", (-w + 3.6, 6.6, -10), (-w + 3.7, 9.6, 12), x0=None)
    for z in np.arange(-10, 12.1, 2.2):
        s.box("truss", (-w + 3.6, 6.5, z - 0.08), (-w + 3.82, 9.7, z + 0.08), x0=None)
    s.box("truss", (-w + 3.6, 5.6, -11), (-w + 4.0, 6.6, 13), x0=None)
    s.box("truss", (-w + 3.6, 9.6, -11), (-w + 4.0, 10.4, 13), x0=None)
    s.box("windows", (-w, 3.0, 20), (-w + 0.2, 9.0, 46), x0=None)
    s.box("windows", (-w, 3.0, -64), (-w + 0.2, 9.0, -24), x0=None)
    s.box("truss", (w - 2.6, 4.9, zo + 10), (w, 5.1, zi - 10))
    s.box("truss", (w - 2.66, 5.34, zo + 10), (w - 2.6, 5.4, zi - 10))
    for z in np.arange(zo + 10, zi - 9.9, 2.0):
        s.box("truss", (w - 2.65, 5.1, z - 0.04), (w - 2.57, 5.4, z + 0.04))
    for z in ribs:
        s.box("truss", (w - 2.6, f, z + 0.8), (w - 2.4, 4.9, z + 1.0))

    # Cargo along both walls, clear of the lane down the middle.
    crates = ("crate_orange", "crate_blue", "crate_grey", "crate_grey", "hull")
    for side in (-1, 1):
        for z in np.arange(zo + 9, zi - 12, 3.4):
            if rng.random() < 0.28 or (side < 0 and -14 < z < 16):
                continue
            x = side * rng.uniform(14.6, 18.6)
            for level in range(rng.integers(1, 5)):
                size = np.array([0.62, 0.62, rng.choice([1.5, 1.5, 3.0])])
                at = np.array([x + rng.uniform(-0.08, 0.08), f + level * 0.64, z + rng.uniform(-0.3, 0.3)])
                paint = crates[rng.integers(len(crates))]
                s.box(paint, at, at + size)
                for dz in (0.08,size[2]-0.14):
                    s.box("truss",at+(-0.025,-0.006,dz),at+size+(0.025,0.018,dz+0.055-size[2]))
                # Formed ribs and load-spreading sills on the corridor-facing wall.
                edge = at[0] + (size[0] if side < 0 else 0)
                for dz in np.arange(0.22,size[2]-0.14,0.23):
                    s.box(paint,(edge-0.036,at[1]+0.1,at[2]+dz),
                          (edge+0.036,at[1]+size[1]-0.08,at[2]+dz+0.065))
                s.box("truss",at+(-0.03,0.01,0.04),at+(size[0]+0.03,0.075,size[2]-0.04))
                if rng.random() < 0.6:
                    s.box(crates[rng.integers(len(crates))], at + (0.7, 0, 0), at + (0.7, 0, 0) + size)
    for side, z in ((1, 30), (1, -46), (-1, 34), (-1, -58)):
        # Fuel tanks on cradles.
        for i in range(3):
            x = side * (15.0 + i * 1.5)
            s.tube("paint_white", (x, f + 0.75, z), (x, f + 0.75, z + 4.5), 0.6, 14)
            s.box("truss", (x - 0.5, f, z + 0.6), (x + 0.5, f + 0.25, z + 0.9))
            s.box("truss", (x - 0.5, f, z + 3.6), (x + 0.5, f + 0.25, z + 3.9))
    for x, z in ((-9.5, 22), (10.5, -18), (9.0, 34)):
        # Service carts.
        s.box("paint_yellow", (x, f + 0.18, z), (x + 0.9, f + 0.5, z + 1.8))
        s.box("truss", (x + 0.1, f + 0.5, z + 1.1), (x + 0.8, f + 0.85, z + 1.7))
        for dx in (0.0, 0.9):
            for dz in (0.3, 1.5):
                s.tube("rubber", (x + dx - 0.06, f + 0.16, z + dz), (x + dx + 0.06, f + 0.16, z + dz), 0.16, 8)


def tower(s, rng):
    """The stack of drums above the bay, topped by a mast."""
    base = BAY_TOP + 8
    y = base
    for height, radius, material in ((16, 20, "hull_dark"), (16, 30, "windows"), (6, 24, "hull_dark"),
                                     (14, 34, "hull"), (14, 34.6, "windows"), (10, 34, "hull"),
                                     (6, 27, "hull_dark"), (22, 22, "windows"), (8, 25, "hull"),
                                     (20, 14, "hull_dark"), (6, 17, "hull")):
        s.tube(material, (0, y, TOWER_Z), (0, y + height, TOWER_Z), radius, 56, cap_material="hull_dark")
        s.tube("truss", (0, y - 0.4, TOWER_Z), (0, y + 0.4, TOWER_Z), radius + 0.9, 56)
        if material != "windows":
            # Clutter standing out from the drum.
            for _ in range(int(radius * height / 5)):
                angle = rng.uniform(0, 2 * math.pi)
                out = np.array([math.sin(angle), 0, math.cos(angle)])
                along = np.array([math.cos(angle), 0, -math.sin(angle)])
                wide, tall = rng.uniform(0.8, 4), rng.uniform(0.6, min(5, height * 0.7))
                at = np.array([0, y + rng.uniform(0, height - tall), TOWER_Z]) + out * (radius - 0.3) - along * wide / 2
                s.block(("hull", "hull_dark", "truss")[rng.integers(3)], at, along * wide, (0, tall, 0),
                        out * rng.uniform(0.5, 1.6), z0=None)
        y += height
    top = y
    s.tube("truss", (0, top, TOWER_Z), (0, top + 46, TOWER_Z), 1.6, 12)
    s.tube("truss", (0, top + 46, TOWER_Z), (0, top + 70, TOWER_Z), 0.5, 8)
    s.ball("light_red", (0, top + 70.5, TOWER_Z), 0.9, 10)
    for i, (height, reach) in enumerate(((10, 16), (22, 11), (34, 7))):
        s.box("truss", (-reach, top + height, TOWER_Z - 0.35), (reach, top + height + 0.7, TOWER_Z + 0.35))
        s.box("truss", (-0.35, top + height, TOWER_Z - reach), (0.35, top + height + 0.7, TOWER_Z + reach))
    for angle, tilt in ((0.6, 0.5), (2.5, 0.2), (4.4, 0.7)):
        # Dishes on stalks.
        out = np.array([math.sin(angle), 0, math.cos(angle)])
        foot = np.array([0, top - 2, TOWER_Z]) + out * 13
        aim = unit(out + (0, tilt, 0))
        s.tube("truss", foot, foot + (0, 7, 0), 0.4, 8)
        s.tube("hull", foot + (0, 7, 0), foot + (0, 7, 0) + aim * 2.4, 0.5, 20, end_radius=6.0, cap_material="hull_dark")
        s.tube("truss", foot + (0, 7, 0) + aim * 2.4, foot + (0, 7, 0) + aim * 6.5, 0.15, 6)

    # Solar wings on booms either side of the top drum.
    for side in (-1, 1):
        boom = np.array([side * 14.0, top - 16, TOWER_Z])
        s.box("truss", boom + (0, -1, -1), boom + (side * 150, 1, 1))
        for i in range(4):
            x0 = side * (30 + i * 34)
            for lower in (False, True):
                y0 = top - 16 + (-47 if lower else 3)
                lo = (x0, y0, TOWER_Z - 0.25)
                hi = (x0 + side * 30, y0 + 44, TOWER_Z + 0.25)
                s.box("truss", lo, hi, z0="solar", z1="solar")
        s.ball("light_green" if side > 0 else "light_red", boom + (side * 151, 0, 0), 1.0, 10)


def habitat_ring(s, rng):
    """The wheel: an eight-sided tube of decks, held by spokes."""
    centre = (0, RING_Y, TOWER_Z)
    r, half_w, half_h, c = RING_RADIUS, 11.0, 8.0, 3.0
    profile = [(r + half_w, -half_h + c), (r + half_w, half_h - c), (r + half_w - c, half_h),
               (r - half_w + c, half_h), (r - half_w, half_h - c), (r - half_w, -half_h + c),
               (r - half_w + c, -half_h), (r + half_w - c, -half_h)]
    s.sweep(centre, profile, ["windows", "hull_dark", "hull", "hull_dark", "windows", "hull_dark", "hull", "hull_dark"], 128)
    # A lit rail round the rim and a service trench on top.
    rail = [(r + half_w + 0.5, -0.4), (r + half_w + 0.5, 0.4), (r + half_w, 0.4), (r + half_w, -0.4)]
    s.sweep(centre, rail, ["light_cyan", "truss", "truss", "truss"], 128)
    trench = [(r + 4, half_h), (r + 4, half_h + 1.4), (r - 4, half_h + 1.4), (r - 4, half_h)]
    s.sweep(centre, trench, ["hull_dark", "hull", "hull_dark", "hull"], 128)
    for i in range(72):
        angle = 2 * math.pi * i / 72
        out = np.array([math.sin(angle), 0, math.cos(angle)])
        along = np.array([math.cos(angle), 0, -math.sin(angle)])
        for reach, depth in ((r + half_w, 1.0), (r - half_w - 1.0, 1.0)):
            s.block("truss", np.array(centre) + out * reach - along * 0.45 - (0, half_h - c, 0),
                    along * 0.9, (0, 2 * (half_h - c), 0), out * depth)
    for i in range(6):
        angle = math.pi / 6 + i * math.pi / 3
        out = np.array([math.sin(angle), 0, math.cos(angle)])
        hub = np.array(centre) + out * 33
        s.tube("hull", hub, np.array(centre) + out * (r - half_w + 0.5), 4.2, 20)
        for at, size in ((0.32, 7.5), (0.68, 6.2)):
            s.tube("hull_dark", hub + out * (r - 44) * at - out * 5, hub + out * (r - 44) * at + out * 5, size, 20)
        # Docking collar where the spoke meets the ring, and a pod outside it.
        s.tube("hull_dark", np.array(centre) + out * (r + half_w), np.array(centre) + out * (r + half_w + 7), 5.0, 18)
        s.tube("hull", np.array(centre) + out * (r + half_w + 7), np.array(centre) + out * (r + half_w + 9), 6.4, 18)
    for i in range(420):
        # Clutter on the ring's top and bottom faces.
        angle = rng.uniform(0, 2 * math.pi)
        out = np.array([math.sin(angle), 0, math.cos(angle)])
        along = np.array([math.cos(angle), 0, -math.sin(angle)])
        wide, deep = rng.uniform(1, 5), rng.uniform(1, 4.5)
        up = 1 if i % 2 else -1
        at = np.array(centre) + out * rng.uniform(r - 7, r + 7 - deep) - along * wide / 2 + (0, up * half_h, 0)
        if up > 0:
            s.block(("hull", "hull_dark", "truss")[rng.integers(3)], at, along * wide, (0, rng.uniform(0.4, 1.6), 0), out * deep, y0=None)
        else:
            s.block(("hull", "hull_dark", "truss")[rng.integers(3)], at - (0, rng.uniform(0.4, 1.6), 0), along * wide, (0, at[1] - (at[1] - 1), 0), out * deep)


def keel(s, rng):
    """Below the bay: reactor drum, radiator fins and fuel spheres."""
    y = BAY_FLOOR - 9
    s.tube("hull_dark", (0, y - 14, TOWER_Z), (0, y, TOWER_Z), 20, 48)
    s.tube("hull", (0, y - 44, TOWER_Z), (0, y - 14, TOWER_Z), 15, 48)
    s.tube("hull_dark", (0, y - 60, TOWER_Z), (0, y - 44, TOWER_Z), 15, 48, end_radius=7)
    s.tube("truss", (0, y - 86, TOWER_Z), (0, y - 60, TOWER_Z), 1.2, 10)
    s.ball("light_white", (0, y - 86.5, TOWER_Z), 0.8, 10)
    for i in range(8):
        angle = i * math.pi / 4
        out = np.array([math.sin(angle), 0, math.cos(angle)])
        along = np.array([math.cos(angle), 0, -math.sin(angle)])
        if i % 2:
            s.ball("paint_white", np.array([0, y - 30, TOWER_Z]) + out * 25, 9.0, 24)
            s.tube("truss", np.array([0, y - 30, TOWER_Z]) + out * 14, np.array([0, y - 30, TOWER_Z]) + out * 17, 2.0, 10)
        else:
            s.block("truss", np.array([0, y - 42, TOWER_Z]) + out * 15 - along * 0.3, along * 0.6, (0, 26, 0), out * 34)


# ------------------------------------------------------------------ textures
def tiling_noise(rng, falloff):
    """Noise that wraps at the edges, 0..1."""
    spectrum = np.fft.fft2(rng.standard_normal((TEX, TEX)))
    fy, fx = np.meshgrid(np.fft.fftfreq(TEX), np.fft.fftfreq(TEX), indexing="ij")
    f = np.hypot(fx, fy)
    f[0, 0] = 1
    field = np.real(np.fft.ifft2(spectrum / f ** falloff))
    return (field - field.min()) / (field.max() - field.min())


def split(rng, x0, y0, x1, y1, smallest, out):
    """Cut a rectangle into panels no finer than `smallest` pixels."""
    w, h = x1 - x0, y1 - y0
    if max(w, h) < smallest * 2 or (max(w, h) < smallest * 6 and rng.random() < 0.3):
        out.append((x0, y0, x1, y1))
    elif w >= h:
        cut = x0 + int(round(w * rng.uniform(0.3, 0.7) / 8)) * 8
        split(rng, x0, y0, cut, y1, smallest, out)
        split(rng, cut, y0, x1, y1, smallest, out)
    else:
        cut = y0 + int(round(h * rng.uniform(0.3, 0.7) / 8)) * 8
        split(rng, x0, y0, x1, cut, smallest, out)
        split(rng, x0, cut, x1, y1, smallest, out)


def blur(field, radius):
    for axis in (0, 1):
        field = sum(np.roll(field, shift, axis) for shift in range(-radius, radius + 1)) / (2 * radius + 1)
    return field


def normals(height, strength):
    """A tangent-space normal map from a height field that wraps."""
    dx = (np.roll(height, -1, 1) - np.roll(height, 1, 1)) * strength
    dy = (np.roll(height, -1, 0) - np.roll(height, 1, 0)) * strength
    n = np.stack([-dx, -dy, np.ones_like(dx)], axis=2)
    return n / np.linalg.norm(n, axis=2, keepdims=True) * 0.5 + 0.5


def paint_panels(rng, smallest, tones, accent, wear, roughness):
    """Plating: colour, normal and occlusion-roughness-metallic maps."""
    panels = []
    split(rng, 0, 0, TEX, TEX, smallest, panels)
    color = np.zeros((TEX, TEX, 3))
    height = np.zeros((TEX, TEX))
    rough = np.zeros((TEX, TEX))
    seam = np.zeros((TEX, TEX))
    for x0, y0, x1, y1 in panels:
        tone = accent if rng.random() < 0.035 else tones[rng.integers(len(tones))]
        color[y0:y1, x0:x1] = np.array(tone) * rng.uniform(0.95, 1.04)
        rough[y0:y1, x0:x1] = rng.uniform(*roughness)
        height[y0:y1, x0:x1] = rng.choice([0, 0, 0, 0.5, -0.4])
        for edge in (np.s_[y0:y0 + 2, x0:x1], np.s_[y1 - 2:y1, x0:x1], np.s_[y0:y1, x0:x0 + 2], np.s_[y0:y1, x1 - 2:x1]):
            seam[edge] = 1
        w, h = x1 - x0, y1 - y0
        if min(w, h) > 40 and rng.random() < 0.16:
            # A vent: a block of slots.
            for y in range(y0 + 10, y1 - 10, 7):
                height[y:y + 3, x0 + 10:x1 - 10] -= 0.8
                color[y:y + 3, x0 + 10:x1 - 10] *= 0.45
        elif min(w, h) > 24 and rng.random() < 0.5:
            # Bolts in the corners.
            for cx, cy in ((x0 + 7, y0 + 7), (x1 - 8, y0 + 7), (x0 + 7, y1 - 8), (x1 - 8, y1 - 8)):
                height[cy - 1:cy + 2, cx - 1:cx + 2] += 0.6
                color[cy - 1:cy + 2, cx - 1:cx + 2] *= 0.8
    height -= seam * 1.2
    grime = tiling_noise(rng, 1.5)
    streaks = blur(tiling_noise(rng, 0.6), 1)
    color *= (1 - 0.4 * seam)[..., None]
    color *= (1 - wear * (0.7 * grime + 0.3 * streaks))[..., None]
    rough = np.clip(rough + 0.25 * (grime - 0.5) + 0.2 * seam, 0.05, 1)
    orm = np.stack([1 - 0.5 * blur(seam, 2), rough, np.full_like(rough, 0.85) - 0.3 * seam], axis=2)
    return np.clip(color, 0, 1), normals(blur(height, 1), 1.6), np.clip(orm, 0, 1)


def paint_windows(rng):
    """Rows of cabin windows, some lit: colour, normal, ORM and emission maps."""
    color = np.full((TEX, TEX, 3), 0.20) * np.array([0.92, 0.96, 1.0])
    height = np.zeros((TEX, TEX))
    rough = np.full((TEX, TEX), 0.55)
    glow = np.zeros((TEX, TEX, 3))
    row_height = TEX // 16
    for row in range(16):
        y0 = row * row_height
        height[y0:y0 + 3] -= 1
        color[y0:y0 + 3] *= 0.5
        if row % 4 == 3:
            color[y0 + 3:y0 + row_height] *= 0.6   # a blank service deck
            continue
        lit_run = 0
        for x0 in range(8, TEX - 20, 32):
            if lit_run <= 0 and rng.random() < 0.25:
                lit_run = rng.integers(1, 7)
            window = np.s_[y0 + 22:y0 + 46, x0:x0 + 20]
            color[window] = (0.015, 0.02, 0.03)
            rough[window] = 0.12
            height[window] -= 0.7
            if lit_run > 0:
                lit_run -= 1
                warm = rng.random() < 0.7
                glow[window] = np.array((1.0, 0.82, 0.55) if warm else (0.62, 0.84, 1.0)) * rng.uniform(0.5, 1.0)
    color *= (1 - 0.25 * tiling_noise(rng, 1.5))[..., None]
    orm = np.stack([np.ones_like(rough), rough, np.where(rough < 0.2, 0.0, 0.8)], axis=2)
    return np.clip(color, 0, 1), normals(blur(height, 1), 1.4), orm, glow


def paint_solar(rng):
    color = np.zeros((TEX, TEX, 3))
    rough = np.full((TEX, TEX), 0.5)
    height = np.zeros((TEX, TEX))
    cell = TEX // 16
    for y in range(16):
        for x in range(16):
            area = np.s_[y * cell + 2:(y + 1) * cell - 2, x * cell + 2:(x + 1) * cell - 2]
            color[area] = np.array((0.012, 0.03, 0.11)) * rng.uniform(0.75, 1.25)
            rough[area] = 0.18
            height[area] = 0.5
            color[y * cell + cell // 2 - 1:y * cell + cell // 2 + 1, x * cell + 2:(x + 1) * cell - 2] = (0.25, 0.27, 0.3)
    color[color.sum(axis=2) == 0] = (0.32, 0.33, 0.35)
    orm = np.stack([np.ones_like(rough), rough, np.where(rough < 0.2, 0.3, 0.9)], axis=2)
    return color, normals(blur(height, 1), 1.2), orm


def image(name, data, srgb):
    """A Blender image from an array (bottom row first), saved so it exports."""
    h, w = data.shape[:2]
    rgba = np.ones((h, w, 4), np.float32)
    rgba[..., :3] = data
    img = bpy.data.images.new(name, w, h, alpha=False)
    img.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
    img.pixels.foreach_set(rgba.ravel())
    img.filepath_raw = os.path.join(bpy.app.tempdir, name + ".png")
    img.file_format = "PNG"
    img.save()
    return img


def textured(name, color, normal, orm, glow=None, glow_strength=1.0):
    mat = bpy.data.materials.new(name)
    if not mat.node_tree:
        mat.use_nodes = True
    mat.use_backface_culling = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")

    def texture(img):
        node = nt.nodes.new("ShaderNodeTexImage")
        node.image = img
        return node

    nt.links.new(texture(color).outputs["Color"], bsdf.inputs["Base Color"])
    bump = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(texture(normal).outputs["Color"], bump.inputs["Color"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    channels = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(texture(orm).outputs["Color"], channels.inputs["Color"])
    nt.links.new(channels.outputs["Green"], bsdf.inputs["Roughness"])
    nt.links.new(channels.outputs["Blue"], bsdf.inputs["Metallic"])
    if glow is not None:
        nt.links.new(texture(glow).outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = glow_strength
    return mat


def flat(name, color, roughness, metallic, glow):
    mat = bpy.data.materials.new(name)
    if not mat.node_tree:
        mat.use_nodes = True
    mat.use_backface_culling = True
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if glow:
        bsdf.inputs["Emission Color"].default_value = (*color, 1)
        bsdf.inputs["Emission Strength"].default_value = glow
    return mat


def materials(rng):
    light = [(0.60, 0.62, 0.65), (0.56, 0.58, 0.62), (0.63, 0.64, 0.66), (0.53, 0.56, 0.60)]
    dark = [(0.31, 0.32, 0.33), (0.28, 0.30, 0.31), (0.32, 0.33, 0.335), (0.26, 0.28, 0.30)]
    plates = [(0.38, 0.40, 0.405), (0.35, 0.36, 0.365), (0.39, 0.40, 0.41)]
    # The dark hull shares the light hull's panel layout, so it can share its normal map.
    hull_color, hull_normal, hull_orm = paint_panels(np.random.default_rng(5), 24, light, (0.62, 0.36, 0.14), 0.35, (0.35, 0.65))
    dark_color, _, _ = paint_panels(np.random.default_rng(5), 24, dark, (0.36, 0.38, 0.42), 0.35, (0.35, 0.65))
    deck_color, deck_normal, deck_orm = paint_panels(rng, 60, plates, (0.32,0.315,0.28), 0.25, (0.44, 0.72))
    # Service dollies leave thin paired rubber tracks crossing the plate joints.
    tracks = Image.new("L",(TEX,TEX))
    tread = ImageDraw.Draw(tracks)
    for x,y,r,angle in ((146,95,386,11),(715,872,413,188),(8,929,580,256)):
        for offset in (0,16):
            radius = r+offset
            tread.arc((x-radius,y-radius,x+radius,y+radius),angle,angle+48,fill=120,width=3)
    rub = np.asarray(tracks)/255.0
    deck_color *= (1.0-rub*0.31)[...,None]
    deck_orm[...,1] -= rub*0.21
    deck_orm[...,2] *= 0.56
    window_color, window_normal, window_orm, window_glow = paint_windows(rng)
    solar_color, solar_normal, solar_orm = paint_solar(rng)
    hull_normal_image = image("station_hull_normal", hull_normal, False)
    hull_orm_image = image("station_hull_orm", hull_orm, False)
    deck_normal_image = image("station_deck_normal", deck_normal, False)
    deck_orm_image = image("station_deck_orm", deck_orm, False)
    made = dict(
        hull=textured("hull", image("station_hull", hull_color, True), hull_normal_image, hull_orm_image),
        hull_dark=textured("hull_dark", image("station_hull_dark", dark_color, True), hull_normal_image, hull_orm_image),
        deck=textured("deck", image("station_deck", deck_color, True), deck_normal_image, deck_orm_image),
        windows=textured("windows", image("station_windows", window_color, True),
                         image("station_windows_normal", window_normal, False), image("station_windows_orm", window_orm, False),
                         image("station_windows_glow", window_glow, True), 3.0),
        solar=textured("solar", image("station_solar", solar_color, True), image("station_solar_normal", solar_normal, False),
                       image("station_solar_orm", solar_orm, False)),
    )
    for name, (color, roughness, metallic, glow) in FLAT.items():
        if name not in ("paint_yellow","paint_white"):
            made[name] = flat(name, color, roughness, metallic, glow)
    # Paint wears through to the pad where service equipment crosses a stripe.
    grit = tiling_noise(rng,0.28)
    traffic = tiling_noise(rng,1.45) + 0.29*grit
    chips = np.clip((traffic - 0.78)*5.0,0,1) * np.clip((grit-0.48)*7,0,1)
    for name in ("paint_yellow","paint_white"):
        pigment = np.array(FLAT[name][0])
        colour = pigment * (0.64 + 0.15*traffic[...,None])*(1-chips[...,None]) + deck_color*chips[...,None]
        made[name] = textured(name+"_worn", image(name+"_paint",colour,True),
                              deck_normal_image, deck_orm_image)
    sign = Image.new("RGB",(768,192),(42,53,57))
    pen = ImageDraw.Draw(sign)
    pen.rectangle((0,0,19,192),fill=(215,155,46))
    pen.text((42,12),"03",font=ImageFont.load_default(size=131),fill=(219,219,203))
    pen.text((255,37),"FLIGHT DECK",font=ImageFont.load_default(size=55),fill=(218,219,210))
    pen.line((257,112,698,112),fill=(191,152,80),width=4)
    pen.text((257,127),"PRESSURE BAY  /  OPERATIONS",font=ImageFont.load_default(size=19),fill=(184,191,181))
    sign_mat = flat("Enamel wayfinding plate",(1,1,1),0.64,0.16,0)
    nt = sign_mat.node_tree
    sign_tex = nt.nodes.new("ShaderNodeTexImage")
    sign_tex.image = image("station_bay_sign",(np.asarray(sign)[::-1]/255.0)**2.2,True)
    nt.links.new(sign_tex.outputs["Color"],nt.nodes.get("Principled BSDF").inputs["Base Color"])
    made["bay_sign"] = sign_mat
    return made


# -------------------------------------------------------------------- output
def to_blender(points):
    """Game (x, y, z) is Blender (x, -z, y): the exporter turns it back."""
    points = np.asarray(points, np.float32)
    return np.stack([points[:, 0], -points[:, 2], points[:, 1]], axis=1)


def make_object(shell, made):
    mesh = bpy.data.meshes.new("station")
    mesh.from_pydata(to_blender(shell.points), [], shell.faces)
    for name in shell.slots:
        mesh.materials.append(made[name])
    mesh.polygons.foreach_set("material_index", shell.materials)
    mesh.polygons.foreach_set("use_smooth", shell.smooth)
    uv = mesh.uv_layers.new(name="UVMap")
    uv.data.foreach_set("uv", np.asarray(shell.uvs, np.float32).ravel())
    mesh.update()
    obj = bpy.data.objects.new("station", mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.modifiers.new("Export triangles","TRIANGULATE")
    return obj


def render_views(out):
    os.makedirs(out, exist_ok=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    scene.world = bpy.data.worlds.new("space")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.004, 0.006, 0.012, 1)
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.0
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 4.0
    from mathutils import Vector
    sun.rotation_euler = Vector(to_blender([(0.456, -0.684, -0.570)])[0]).to_track_quat("-Z", "Y").to_euler()
    scene.collection.objects.link(sun)
    for z in np.arange(BAY_OUT + 13, BAY_IN, 24):
        lamp = bpy.data.objects.new("lamp", bpy.data.lights.new("lamp", "POINT"))
        lamp.data.energy = 30000
        lamp.data.color = (0.85, 0.93, 1.0)
        lamp.location = to_blender([(0, BAY_TOP - 3, z)])[0]
        scene.collection.objects.link(lamp)
    camera = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
    camera.data.clip_end = 5000
    scene.collection.objects.link(camera)
    scene.camera = camera
    views = dict(
        approach=((70, 20, 520), (0, 70, -10), 32), mouth=((-30, 6, 130), (0, 6, 40), 40),
        hangar=((9, 3.5, 16), (0, 2.5, -20), 24), side=((330, 110, 60), (0, 70, -10), 45),
    )
    for name, (eye, target, lens) in views.items():
        eye_b, target_b = to_blender([eye, target])
        camera.location = eye_b
        from mathutils import Vector
        camera.rotation_euler = (Vector(target_b) - Vector(eye_b)).to_track_quat("-Z", "Y").to_euler()
        camera.data.lens = lens
        scene.render.filepath = os.path.join(out, f"station-{name}.png")
        bpy.ops.render.render(write_still=True)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    renders = argv[argv.index("--renders") + 1] if "--renders" in argv else None
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)

    rng = np.random.default_rng(11)
    shell = Shell()
    bay(shell, rng)
    tower(shell, rng)
    habitat_ring(shell, rng)
    keel(shell, rng)
    station = make_object(shell, materials(rng))

    bpy.ops.object.select_all(action="DESELECT")
    station.select_set(True)
    bpy.context.view_layer.objects.active = station
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=OUT_PATH, export_format="GLB", use_selection=True,
                              export_apply=True, export_yup=True, export_tangents=True,
                              export_image_format="JPEG", export_image_quality=90)
    tris = sum(len(p.vertices) - 2 for p in station.data.polygons)
    print(f"[station] {tris} tris, {os.path.getsize(OUT_PATH) / 1e6:.1f} MB")
    if renders:
        render_views(renders)


main()
