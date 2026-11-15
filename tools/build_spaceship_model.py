"""Build the triangle spaceship game model from the concept art.

    blender -b --factory-startup --python tools/build_spaceship_model.py [-- --renders DIR]

The concept image is treated as a top-down map: feature outlines traced from it
(in image pixels) are triangulated, lifted to 3D with height functions, and the
image itself is projected back on as the texture. Outputs go to assets/models/.
"""
import math
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import bpy
import numpy as np
from mathutils import Vector
from mathutils.geometry import delaunay_2d_cdt
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).resolve().parent))
from airframe_finish import apply_maps, finish_atlas

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONCEPT = os.path.join(ROOT, "assets", "concepts", "triangle-spaceship.png")
OUT_DIR = os.path.join(ROOT, "assets", "models")
NAME = "triangle-spaceship"

# ---------------------------------------------------------------- parameters
CX = 656.5               # symmetry axis of the concept, in pixels
IMG_W = 1312             # concept width; the atlas is square, concept on top
ATLAS = 2048
UNITS_PER_PX = 1 / 300   # wingspan comes out at ~4 units
Z_SCALE = 2.1
SNAP = 1.5               # merge feature points closer than this (px)

WT = 24                  # leading-edge trim width
ZT, S_TOP = 12, 0.11     # top: trim height, wing slope per px from leading edge
ZBT, S_BOT = 8, 0.045    # belly: same, shallower

# Feature outlines, left half only, in concept pixels (y down). Centre-spanning
# shapes run from their top-centre point to their bottom-centre point.
RTOP = [(165, 1073), (385, 1022), (438, 996), (585, 996), (627, 1040),
        (CX, 1040)]                                   # top edge of rear faces
FUSELAGE = [(CX, 166), (640, 172), (617, 238), (603, 300), (562, 460),
            (564, 545), (545, 600), (548, 650), (590, 705), (598, 745),
            (618, 865), (627, 1000), (627, 1160), (CX, 1160)]
FUSELAGE_W = 18
FUSELAGE_RISE = [(166, 12), (270, 22), (770, 22), (795, 14), (1160, 14)]
GLASS = [(CX, 300), (645, 300), (600, 452), (608, 470), (638, 570), (CX, 570)]
FRAME_W = 9                                           # canopy frame around the glass
CREST = [(CX, 316), (637, 428), (641, 558), (CX, 558)]
CREST_H = [7, 24, 9, 9]
CREST_RIDGE = ((CX, 426), 26)
NACELLE = [(548, 886), (468, 930), (438, 996), (438, 1160), (627, 1160),
           (627, 1000), (618, 865)]
NACELLE_W = 15
INTAKE = [(480, 792), (542, 762), (545, 842), (462, 878), (456, 862)]
NOZZLE = [(447, 1068), (563, 1068), (578, 1082), (578, 1105), (560, 1120),
          (450, 1120), (437, 1105), (437, 1082)]

# Regions of the concept that glow (left half; x0, y0, x1, y1).
GLOW_BOXES = [(425, 1058, 590, 1142), (478, 998, 552, 1020),
              (574, 484, 602, 548), (644, 812, CX, 898)]
BELLY_COLOR = (0.16, 0.17, 0.20)
BELLY_UV = (0.5, 0.04)   # inside the flat strip under the concept in the atlas


# ------------------------------------------------------------------ 2D utils
def mirror(pts):
    return [(2 * CX - x, y) for x, y in pts]


def full_poly(left):
    return left + [p for p in mirror(left)[::-1] if abs(p[0] - CX) > 1e-6]


def seg_dist(px, py, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    ll = dx * dx + dy * dy
    t = 0.0 if ll == 0 else max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / ll))
    return math.hypot(px - a[0] - t * dx, py - a[1] - t * dy)


def line_dist(px, py, pts, closed):
    n = len(pts)
    return min(seg_dist(px, py, pts[i], pts[(i + 1) % n])
               for i in range(n if closed else n - 1))


def inside(px, py, poly):
    hit = False
    n = len(poly)
    for i in range(n):
        (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % n]
        if (y0 > py) != (y1 > py) and px < x0 + (py - y0) * (x1 - x0) / (y1 - y0):
            hit = not hit
    return hit


def plateau(px, py, poly, w):
    """0 outside poly, ramping to 1 once w pixels inside it."""
    if not inside(px, py, poly):
        return 0.0
    return min(line_dist(px, py, poly, True) / w, 1.0)


def interp(pts, x):
    """Piecewise-linear lookup in points sorted by their first coordinate."""
    if x <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[-1][1]


def simplify(pts, tol):
    """Ramer-Douglas-Peucker."""
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i0, i1 = stack.pop()
        best, best_i = tol, None
        for i in range(i0 + 1, i1):
            d = seg_dist(pts[i][0], pts[i][1], pts[i0], pts[i1])
            if d > best:
                best, best_i = d, i
        if best_i is not None:
            keep[best_i] = True
            stack += [(i0, best_i), (best_i, i1)]
    return [p for p, k in zip(pts, keep) if k]


def offset_points(pts, w, closed):
    """Mitre-offset a polyline to its left (the inside of a CCW polygon)."""
    n = len(pts)
    lines = []
    for i in range(n if closed else n - 1):
        (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % n]
        ex, ey = x1 - x0, y1 - y0
        ll = math.hypot(ex, ey)
        nx, ny = -ey / ll, ex / ll
        lines.append(((x0 + nx * w, y0 + ny * w), (ex, ey)))
    out = []
    for i in range(n):
        if not closed and i == 0:
            out.append(lines[0][0])
            continue
        if not closed and i == n - 1:
            (ox, oy), (ex, ey) = lines[-1]
            out.append((ox + ex, oy + ey))
            continue
        (p, d), (q, e) = lines[i - 1], lines[i]
        cross = d[0] * e[1] - d[1] * e[0]
        if abs(cross) < 1e-9:
            out.append(q)
            continue
        t = ((q[0] - p[0]) * e[1] - (q[1] - p[1]) * e[0]) / cross
        out.append((p[0] + d[0] * t, p[1] + d[1] * t))
    return out


def signed_area(poly):
    return 0.5 * sum(poly[i][0] * poly[(i + 1) % len(poly)][1]
                     - poly[(i + 1) % len(poly)][0] * poly[i][1]
                     for i in range(len(poly)))


def ccw(poly):
    return poly if signed_area(poly) > 0 else poly[::-1]


def inset_runs(poly, w):
    """Inset poly by w; return the stretches that really sit w inside it."""
    poly = ccw(poly)
    pts = offset_points(poly, w, True)
    ok = [inside(x, y, poly) and line_dist(x, y, poly, True) >= w - 0.5 for x, y in pts]
    n = len(pts)
    return [(pts[i], pts[(i + 1) % n]) for i in range(n) if ok[i] and ok[(i + 1) % n]]


# ------------------------------------------------------------- concept image
def load_concept():
    img = bpy.data.images.load(CONCEPT)
    w, h = img.size
    buf = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(buf)
    px = buf.reshape(h, w, 4)[::-1].copy()          # row 0 = top of the image
    right = np.arange(int(CX) + 1, w)
    px[:, right] = px[:, w - right]                  # make it exactly symmetric
    return px


def erode(mask, n):
    for _ in range(n):
        m = mask.copy()
        m[1:] &= mask[:-1]
        m[:-1] &= mask[1:]
        m[:, 1:] &= mask[:, :-1]
        m[:, :-1] &= mask[:, 1:]
        mask = m
    return mask


def trace_outline(px):
    """Left half of the silhouette: leading edge (nose -> wing tip), rear edge
    (wing tip -> tail centre)."""
    mask = erode(px[..., 3] >= 0.5, 2)
    h = mask.shape[0]
    rows = np.nonzero(mask.any(axis=1))[0]
    x_left = mask.argmax(axis=1)
    apex = int(rows[0])
    tip_row = int(min(rows, key=lambda r: (x_left[r], r)))
    tip_col = int(x_left[tip_row])
    leading = [(CX, apex + 0.5)]
    leading += [(x_left[r] + 0.5, r + 0.5) for r in range(apex + 1, tip_row + 1)]
    rear = []
    for c in range(tip_col, int(CX)):
        rear.append((c + 0.5, h - 1 - int(mask[::-1, c].argmax()) + 0.5))
    rear.append((CX, rear[-1][1]))
    leading = simplify([(float(x), float(y)) for x, y in leading], 1.0)
    rear = simplify([(float(x), float(y)) for x, y in rear], 1.0)
    if rear[0] == leading[-1]:
        rear = rear[1:]
    return leading, rear


def dilate_colors(px, iters=40):
    """Bleed hull colours into the transparent surround so texture filtering
    never pulls in background at the silhouette."""
    valid = px[..., 3] >= 0.9
    rgb = px[..., :3] * valid[..., None]
    for _ in range(iters):
        acc = np.zeros_like(rgb)
        cnt = np.zeros(valid.shape, np.float32)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx or dy:
                    acc += np.roll(rgb, (dy, dx), (0, 1))
                    cnt += np.roll(valid, (dy, dx), (0, 1))
        new = ~valid & (cnt > 0)
        rgb[new] = acc[new] / cnt[new][:, None]
        valid |= new
    rgb[~valid] = BELLY_COLOR
    return rgb


def resize(a, nw, nh):
    h, w = a.shape[:2]
    xs = np.clip((np.arange(nw) + 0.5) * w / nw - 0.5, 0, w - 1)
    ys = np.clip((np.arange(nh) + 0.5) * h / nh - 0.5, 0, h - 1)
    x0, y0 = np.floor(xs).astype(int), np.floor(ys).astype(int)
    x1, y1 = np.minimum(x0 + 1, w - 1), np.minimum(y0 + 1, h - 1)
    fx, fy = (xs - x0)[None, :, None], (ys - y0)[:, None, None]
    top = a[y0][:, x0] * (1 - fx) + a[y0][:, x1] * fx
    bot = a[y1][:, x0] * (1 - fx) + a[y1][:, x1] * fx
    return top * (1 - fy) + bot * fy


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def build_textures(px):
    h, w = px.shape[:2]
    rgb = dilate_colors(px)

    glow = np.zeros((h, w), np.float32)
    for x0, y0, x1, y1 in GLOW_BOXES:
        glow[int(y0):int(y1), int(x0):int(x1)] = 1
    glow = np.maximum(glow, glow[:, ::-1][:, np.arange(w) - 1])  # mirror about CX
    r, b = rgb[..., 0], rgb[..., 2]
    glow *= smoothstep(0.15, 0.4, b - r) * smoothstep(0.35, 0.7, b)
    emit = rgb * glow[..., None]

    scale_h = round(h * ATLAS / w)
    base = np.empty((ATLAS, ATLAS, 3), np.float32)
    base[:] = BELLY_COLOR
    base[:scale_h] = resize(rgb, ATLAS, scale_h)
    emis = np.zeros((ATLAS, ATLAS, 3), np.float32)
    emis[:scale_h] = resize(emit, ATLAS, scale_h)

    # Preserve the hand-painted markings and machine the service panels into
    # the opaque skin. The pressure canopy is a separate polished substrate.
    canopy = Image.new("L", (ATLAS, ATLAS))
    ImageDraw.Draw(canopy).polygon([(round(x*ATLAS/w), round(y*ATLAS/w)) for x,y in full_poly(GLASS)], fill=255)
    glass = np.asarray(canopy, dtype=np.float32)/255
    alloy = np.clip(1.0 - np.max(base, axis=2)*2.6, 0, 1)
    labels = [(639, 576, "DW / 01", 19), (296, 584, "ACCESS", 12), (484, 497, "RESCUE", 9)]
    with TemporaryDirectory() as temp:
        wear, normal, coating = finish_atlas(NAME, temp, Image.new("L",(ATLAS,ATLAS),252),
                                              17, labels, 1-glass, (glass,alloy))
    base *= wear[...,None]
    base *= 1 - glass[..., None] * 0.60
    os.makedirs(OUT_DIR, exist_ok=True)
    images = []
    for suffix, data in (("basecolor", base), ("emissive", emis)):
        img = bpy.data.images.new(f"{NAME}_{suffix}", ATLAS, ATLAS, alpha=False)
        rgba = np.ones((ATLAS, ATLAS, 4), np.float32)
        rgba[..., :3] = np.clip(data, 0, 1)
        img.pixels.foreach_set(rgba[::-1].ravel())
        img.filepath_raw = os.path.join(OUT_DIR, f"{NAME}_{suffix}.png")
        img.file_format = "PNG"
        img.save()
        images.append(img)
    return images, normal, coating["paint"]


# ------------------------------------------------------------ height fields
class Hull:
    """Heights are in concept pixels and evaluated on the left half (x <= CX)."""

    def __init__(self, leading, rear):
        self.leading = leading
        self.rear = rear
        self.outline = full_poly(leading + rear)
        self.rtop = [leading[-1]] + RTOP
        self.fuselage = full_poly(FUSELAGE)
        self.glass = full_poly(GLASS)
        self.frame = offset_points(ccw(self.glass), -FRAME_W, True)
        self.crest = {self.key(*p): h for p, h in zip(CREST, CREST_H)}
        self.crest[self.key(*CREST_RIDGE[0])] = CREST_RIDGE[1]

    @staticmethod
    def key(x, y):
        return (round(x, 2), round(y, 2))

    def wedge(self, x, y, edge_h, slope):
        d = line_dist(x, y, self.leading, False)
        return edge_h * min(d / WT, 1.0) + slope * max(d - WT, 0.0)

    def deck(self, x, y):
        """Top surface ahead of the rear faces."""
        z = self.wedge(x, y, ZT, S_TOP)
        z += interp(FUSELAGE_RISE, y) * plateau(x, y, self.fuselage, FUSELAGE_W)
        z += 14 * plateau(x, y, NACELLE, NACELLE_W)
        z -= 8 * plateau(x, y, INTAKE, 7)
        z += 5 * plateau(x, y, self.frame, FRAME_W)
        return z + self.crest.get(self.key(x, y), 0.0)

    def belly(self, x, y):
        z = -self.wedge(x, y, ZBT, S_BOT)
        z -= 12 * plateau(x, y, self.fuselage, FUSELAGE_W)
        z -= 22 * plateau(x, y, NACELLE, NACELLE_W)
        return z

    def top(self, x, y):
        y_top = interp(self.rtop, x)
        if y <= y_top:
            return self.deck(x, y)
        y_sil = interp(self.rear, x)
        t = max(0.0, min(1.0, (y - y_top) / max(y_sil - y_top, 1e-6)))
        z = self.deck(x, y_top) * (1 - t) + self.belly(x, y_sil) * t
        return z - 10 * plateau(x, y, NOZZLE, 6)

    def front_runs(self, a, b):
        """Split segment a-b at the rear faces: the stretches ahead of them,
        and the points where it reaches them."""
        def ahead(t):
            x, y = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
            return interp(self.rtop, CX - abs(x - CX)) - y >= -1e-6

        def at(t):
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)

        steps = max(1, int(math.hypot(b[0] - a[0], b[1] - a[1]) / 8))
        runs, hits, start = [], [], 0.0 if ahead(0.0) else None
        for i in range(steps):
            t0, t1 = i / steps, (i + 1) / steps
            if ahead(t0) == ahead(t1):
                continue
            was_ahead = ahead(t0)
            for _ in range(30):
                tm = (t0 + t1) / 2
                if ahead(tm) == was_ahead:
                    t0 = tm
                else:
                    t1 = tm
            hits.append(at(t0))
            if was_ahead:
                runs.append((at(start), at(t0)))
                start = None
            else:
                start = t1
        if start is not None:
            runs.append((at(start), b))
        return runs, hits


# ------------------------------------------------------------- triangulation
class Net:
    """Constraint edges for the triangulation, with nearby points merged."""

    def __init__(self):
        self.verts, self.edges = [], set()

    def v(self, p):
        centre = abs(p[0] - CX) < 1e-6
        for i, q in enumerate(self.verts):
            if (not centre or abs(q.x - CX) < 1e-6) and \
                    math.hypot(q.x - p[0], q.y - p[1]) < SNAP:
                return i
        self.verts.append(Vector((p[0], p[1])))
        return len(self.verts) - 1

    def edge(self, a, b):
        ia, ib = self.v(a), self.v(b)
        if ia != ib:
            self.edges.add((min(ia, ib), max(ia, ib)))

    def chain(self, pts, closed=False):
        for i in range(len(pts) if closed else len(pts) - 1):
            self.edge(pts[i], pts[(i + 1) % len(pts)])

    def both(self, pts, closed=False):
        self.chain(pts, closed)
        self.chain(mirror(pts), closed)


def clip_left(pts):
    """Keep the part of a polyline with x <= CX."""
    out = []
    for a, b in zip(pts, pts[1:]):
        if a[0] <= CX:
            out.append(a)
        if (a[0] - CX) * (b[0] - CX) < 0:
            t = (CX - a[0]) / (b[0] - a[0])
            out.append((CX, a[1] + (b[1] - a[1]) * t))
    if pts[-1][0] <= CX:
        out.append(pts[-1])
    return out


def triangulate(hull):
    net = Net()
    net.chain(hull.outline, True)
    net.chain(hull.glass, True)
    net.chain(full_poly(CREST), True)
    net.both([CREST[1], CREST_RIDGE[0]])
    net.both([CREST[1], GLASS[2]])
    net.both([CREST[2], GLASS[4]])
    net.chain(hull.frame, True)
    net.both(hull.rtop)

    columns = [x for x, _ in RTOP[1:-1]]

    def front(pts, sided, closed=False, column=True):
        for i in range(len(pts) if closed else len(pts) - 1):
            runs, hits = hull.front_runs(pts[i], pts[(i + 1) % len(pts)])
            for run in runs:
                (net.both if sided else net.chain)(list(run))
            if column:
                columns.extend(CX - abs(x - CX) for x, _ in hits)

    def plateau_edges(poly, w, sided):
        front(poly, sided, closed=True)
        for run in inset_runs(poly, w):
            front(list(run), sided)

    trim = offset_points(hull.leading, WT, False)
    if trim[1][0] < hull.leading[1][0]:              # offset went outward
        trim = offset_points(hull.leading, -WT, False)
    front(clip_left(trim), True, column=False)

    plateau_edges(hull.fuselage, FUSELAGE_W, False)
    plateau_edges(NACELLE, NACELLE_W, True)
    plateau_edges(INTAKE, 7, True)
    net.both(NOZZLE, True)
    for run in inset_runs(NOZZLE, 6):
        net.both(list(run))

    for y, _ in FUSELAGE_RISE[1:-1]:                 # creases where the spine steps
        x = next(a[0] + (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1])
                 for a, b in zip(FUSELAGE, FUSELAGE[1:]) if a[1] <= y < b[1])
        net.chain([(x, y), (2 * CX - x, y)])

    placed = []
    for x in sorted(columns):                        # creases down the rear faces
        if x < CX - SNAP and all(abs(x - p) > SNAP for p in placed):
            placed.append(x)
            net.both([(x, interp(hull.rtop, x)), (x, interp(hull.rear, x))])

    centre = sorted((v for v in net.verts if abs(v.x - CX) < 1e-6), key=lambda v: v.y)
    net.chain([tuple(v) for v in centre])

    verts, _, faces, *_ = delaunay_2d_cdt(net.verts, [list(e) for e in net.edges],
                                          [], 0, 1e-3)
    pts = [(v.x, v.y) for v in verts]
    tris = []
    for f in faces:
        cx = sum(pts[i][0] for i in f) / 3
        cy = sum(pts[i][1] for i in f) / 3
        if inside(cx, cy, hull.outline):
            tris.append(tuple(f))
    return pts, tris


# ---------------------------------------------------------------------- mesh
def build_mesh(hull, pts, tris):
    o = hull.outline
    n = len(o)
    y0 = sum((o[i][1] + o[(i + 1) % n][1])
             * (o[i][0] * o[(i + 1) % n][1] - o[(i + 1) % n][0] * o[i][1])
             for i in range(n)) / (6 * signed_area(o))    # area centroid

    def place(p, z):                                 # nose toward -Y, Z up
        return ((CX - p[0]) * UNITS_PER_PX, (p[1] - y0) * UNITS_PER_PX,
                z * UNITS_PER_PX * Z_SCALE)

    def uv(p):
        return (p[0] / IMG_W, 1 - p[1] / IMG_W)

    used = sorted({i for t in tris for i in t})
    verts, top_of, bot_of = [], {}, {}
    for i in used:
        x, y = pts[i]
        hx = CX - abs(x - CX)
        zb = hull.belly(hx, y)
        on_edge = line_dist(x, y, o, True) < 0.02
        top_of[i] = len(verts)
        verts.append(place(pts[i], zb if on_edge else hull.top(hx, y)))
        if on_edge:
            bot_of[i] = top_of[i]
        else:
            bot_of[i] = len(verts)
            verts.append(place(pts[i], zb))

    faces, uvs = [], []
    for t in tris:
        a, b, c = (Vector(verts[top_of[i]]) for i in t)
        if (b - a).cross(c - a).z < 0:
            t = (t[0], t[2], t[1])
        faces.append([top_of[i] for i in t])
        uvs += [uv(pts[i]) for i in t]

        cx = sum(pts[i][0] for i in t) / 3
        cy = sum(pts[i][1] for i in t) / 3
        dark = inside(cx, cy, hull.fuselage) or inside(CX - abs(cx - CX), cy, NACELLE)
        t = t[::-1]
        faces.append([bot_of[i] for i in t])
        uvs += [(pts[i][0]/IMG_W, 0.018 + pts[i][1]/IMG_W*0.046) if dark else uv(pts[i]) for i in t]

    # Turn the illustrated exhausts into deep, scalloped bells. Every face
    # samples the original atlas, which also lets raiders retain their livery.
    for side in (-1,1):
        cx = side*0.491
        steps = 24
        rings = []
        for rear, rx, rz in ((0.88,.246,.223),(1.06,.256,.211),(1.27,.235,.191),
                             (1.29,.198,.154),(1.21,.164,.126)):
            start = len(verts)
            for j in range(steps):
                a = j*math.tau/steps
                petal = 1.0 if j%2==0 else 0.963
                verts.append((cx+rx*math.cos(a)*petal,rear,-0.117+rz*math.sin(a)*petal))
            rings.append(start)
        for k,(a,b) in enumerate(zip(rings,rings[1:])):
            for j in range(steps):
                n = (j+1)%steps
                faces.append([a+j,b+j,b+n,a+n])
                # Machined lips surround darker refractory outer petals.
                x,y = (474,701) if k==2 or (k==1 and j%3==1) else (640,1248)
                uvs.extend(uv((x+dx,y+dy)) for dx,dy in ((0,0),(6,0),(6,8),(0,8)))
        centre = len(verts)
        verts.append((cx,1.21,-0.117))
        for j in range(steps):
            n = (j+1)%steps
            faces.append([centre,rings[-1]+n,rings[-1]+j])
            uvs.append(uv((510,1093)))
            for index in (n,j):
                a = index*math.tau/steps
                uvs.append(uv((510+54*math.cos(a),1093+14*math.sin(a))))

    me = bpy.data.meshes.new(NAME)
    me.from_pydata(verts, [], faces)
    me.uv_layers.new(name="UVMap").data.foreach_set("uv", [c for p in uvs for c in p])
    me.polygons.foreach_set("use_smooth", [True] * len(faces))
    me.set_sharp_from_angle(angle=math.radians(32))
    me.update()
    me.validate()
    return me


def build_material(base_img, emis_img):
    mat = bpy.data.materials.new(NAME)
    mat.use_backface_culling = True                  # closed hull: single-sided
    if not mat.node_tree:
        mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Metallic"].default_value = 0.0
    bsdf.inputs["Roughness"].default_value = 0.55
    bsdf.inputs["Emission Strength"].default_value = 1.0
    for img, socket, y in ((base_img, "Base Color", 300), (emis_img, "Emission Color", -100)):
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        tex.location = (-400, y)
        nt.links.new(tex.outputs["Color"], bsdf.inputs[socket])
    return mat


# -------------------------------------------------------------------- output
def render_views(out):
    os.makedirs(out, exist_ok=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.film_transparent = True
    scene.render.resolution_x, scene.render.resolution_y = 1400, 1050
    scene.view_settings.view_transform = "Standard"

    world = bpy.data.worlds.new("preview")
    if not world.node_tree:
        world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.55, 0.6, 0.7, 1)
    bg.inputs["Strength"].default_value = 0.7
    scene.world = world

    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 3.0
    sun.rotation_euler = (math.radians(40), math.radians(-25), math.radians(30))
    scene.collection.objects.link(sun)

    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.lens = 60
    target = Vector((0, 0.15, 0))

    def shoot(name, loc, ortho=None, top_down=False):
        cam.data.type = "ORTHO" if ortho else "PERSP"
        if ortho:
            cam.data.ortho_scale = ortho
        cam.location = loc
        cam.rotation_euler = (0, 0, math.pi) if top_down else \
            (target - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = os.path.join(out, name + ".png")
        bpy.ops.render.render(write_still=True)

    shoot("top", (0, -0.54, 10), ortho=5.2, top_down=True)
    shoot("front34", (4.2, -6.0, 3.4))
    shoot("rear34", (-3.8, 6.2, 2.6))
    shoot("rear_low", (1.5, 7.5, 0.9))
    shoot("side", (9, 0.15, 0.4), ortho=4.6)
    shoot("front", (0, -9, 0.5), ortho=4.6)
    shoot("belly34", (3.6, -5.0, -3.6))


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    renders = argv[argv.index("--renders") + 1] if "--renders" in argv else None

    for block in (bpy.data.objects, bpy.data.meshes, bpy.data.materials,
                  bpy.data.lights, bpy.data.cameras):
        for item in list(block):
            block.remove(item)

    px = load_concept()
    hull = Hull(*trace_outline(px))
    pts, tris = triangulate(hull)
    mesh = build_mesh(hull, pts, tris)
    (base_img, emis_img), normal, coating = build_textures(px)
    paint = build_material(base_img, emis_img)
    apply_maps(paint, normal, coating)
    mesh.materials.append(paint)

    obj = bpy.data.objects.new(NAME, mesh)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    dims = obj.dimensions
    thin = sum(1 for p in mesh.polygons if p.area < 2e-6)
    print(f"[ship] verts {len(mesh.vertices)}, tris {len(mesh.polygons)} "
          f"({thin} near-degenerate), size {dims.x:.2f} x {dims.y:.2f} x {dims.z:.2f}")

    for img in (base_img, emis_img):
        img.pack()
    bpy.context.preferences.filepaths.save_version = 0   # no .blend1 backups
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT_DIR, NAME + ".blend"),
                                compress=True)
    bpy.ops.export_scene.gltf(filepath=os.path.join(OUT_DIR, NAME + ".glb"),
                              export_format="GLB", use_selection=True,
                              export_apply=True, export_yup=True, export_tangents=True,
                              export_image_format="JPEG", export_image_quality=90)
    if renders:
        render_views(renders)


main()
