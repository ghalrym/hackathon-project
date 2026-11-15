"""Break the triangle spaceship into the pieces a raider leaves when it is shot down.

    blender -b --factory-startup --python tools/build_wreck_model.py [-- --renders DIR]

The finished ship model is cut into cells around seeds spread over its plan
view, the way a pane of glass cracks. Each piece is closed over where it was
cut and keeps its origin at its own centre, placed where it sat on the ship,
so in game the pieces can start out as the whole ship before they fly apart.
The game paints them itself, so no material is exported. Output:
assets/models/raider-wreck.glb.
"""
import math
import os
import random
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHIP = os.path.join(ROOT, "assets", "models", "triangle-spaceship.glb")
OUT = os.path.join(ROOT, "assets", "models", "raider-wreck.glb")

# ---------------------------------------------------------------- parameters
PIECES = 12           # cells the ship breaks into
SEED = 7


def load_ship():
    bpy.ops.import_scene.gltf(filepath=SHIP)
    ship = next(o for o in bpy.context.scene.objects if o.type == "MESH")
    bm = bmesh.new()
    bm.from_mesh(ship.data)
    bm.transform(ship.matrix_world)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    return bm


def spread_seeds(bm, count, rng):
    """Seeds over the ship's plan view, as far from each other as they will go."""
    points = [Vector((v.co.x, v.co.y, 0.0)) for v in bm.verts]
    seeds = [rng.choice(points)]
    nearest = [(p - seeds[0]).length for p in points]
    while len(seeds) < count:
        far = max(range(len(points)), key=nearest.__getitem__)
        seeds.append(points[far])
        nearest = [min(d, (p - points[far]).length) for d, p in zip(nearest, points)]
    # Nudge them off the outline a little so cells are not all slivers.
    middle = sum(seeds, Vector()) / len(seeds)
    return [s.lerp(middle, rng.uniform(0.1, 0.3)) for s in seeds]


def cut_piece(ship, seeds, index):
    """The part of the ship nearer seeds[index] than any other seed, closed up."""
    bm = ship.copy()
    uv = bm.loops.layers.uv.active
    mine = seeds[index]
    for other in seeds:
        if other is mine:
            continue
        normal = (other - mine).normalized()
        cut = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
                                     plane_co=(mine + other) / 2, plane_no=normal,
                                     clear_outer=True)
        edges = [e for e in cut["geom_cut"] if isinstance(e, bmesh.types.BMEdge) and e.is_boundary]
        if edges:
            for face in bmesh.ops.holes_fill(bm, edges=edges, sides=0)["faces"]:
                # Put freshly exposed sandwich panels outside the paint atlas.
                # The raider shader reads these planar coordinates on the cuts.
                tangent = normal.orthogonal().normalized()
                bitangent = normal.cross(tangent)
                for loop in face.loops:
                    p = loop.vert.co
                    loop[uv].uv = (5.0 + p.dot(tangent)*0.35, 0.5 + p.dot(bitangent)*0.35)
    if not bm.faces:
        bm.free()
        return None
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return bm


def build(renders):
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    rng = random.Random(SEED)
    ship = load_ship()
    seeds = spread_seeds(ship, PIECES, rng)
    pieces = []
    for index in range(PIECES):
        bm = cut_piece(ship, seeds, index)
        if bm is None:
            continue
        lo = Vector((min(v.co[i] for v in bm.verts) for i in range(3)))
        hi = Vector((max(v.co[i] for v in bm.verts) for i in range(3)))
        centre = (lo + hi) / 2
        bm.transform(Matrix.Translation(-centre))
        mesh = bpy.data.meshes.new(f"wreck-{index:02d}")
        bm.to_mesh(mesh)
        bm.free()
        obj = bpy.data.objects.new(mesh.name, mesh)
        obj.location = centre
        bpy.context.scene.collection.objects.link(obj)
        pieces.append(obj)
        print(f"[wreck] {mesh.name}: {len(mesh.polygons)} tris, "
              f"{(hi - lo).x:.2f} x {(hi - lo).y:.2f} x {(hi - lo).z:.2f}")
    ship.free()

    bpy.ops.object.select_all(action="DESELECT")
    for obj in pieces:
        obj.select_set(True)
    bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True,
                              export_yup=True, export_tangents=True, export_materials="NONE")
    print(f"[wreck] {len(pieces)} pieces -> {OUT}")
    if renders:
        render_views(pieces, renders)


# -------------------------------------------------------------------- output
def render_views(pieces, out):
    """The pieces pulled apart a little, so the cuts show."""
    os.makedirs(out, exist_ok=True)
    for obj in pieces:
        obj.location *= 1.35
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.film_transparent = True
    scene.render.resolution_x, scene.render.resolution_y = 1000, 800
    scene.view_settings.view_transform = "Standard"
    world = scene.world or bpy.data.worlds.new("preview")
    if not world.node_tree:
        world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.3
    scene.world = world
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 4.0
    sun.rotation_euler = (math.radians(40), 0, math.radians(30))
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.lens = 50
    for extra in (sun, cam):
        scene.collection.objects.link(extra)
    scene.camera = cam
    for view, location in (("top", (0.01, 0.01, 9)), ("angle", (5, -6, 5))):
        cam.location = location
        cam.rotation_euler = (-Vector(location)).to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = os.path.join(out, f"wreck-{view}.png")
        bpy.ops.render.render(write_still=True)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    renders = argv[argv.index("--renders") + 1] if "--renders" in argv else None
    build(renders)


main()
