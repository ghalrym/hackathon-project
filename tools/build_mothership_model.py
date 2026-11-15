"""Build the broadside carrier used by the mothership encounter.

    blender -b --factory-startup --python tools/build_mothership_model.py

The bow points along Blender +Y (Godot -Z). The prow lens is the beam origin.
"""
from math import pi, cos, sin
from pathlib import Path
from tempfile import TemporaryDirectory
import sys

import bpy
import bmesh
from mathutils import Vector
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parent))
from airframe_finish import apply_maps, file_image, finish_atlas


def material(name, color, metallic=0.32, glow=0):
    mat = bpy.data.materials.new(name)
    rgb = [int(color[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    rgba = [((c + 0.055) / 1.055) ** 2.4 if c > 0.04045 else c / 12.92 for c in rgb] + [1]
    mat.diffuse_color = rgba
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = rgba
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = 0.43
    if glow:
        bsdf.inputs["Emission Color"].default_value = rgba
        bsdf.inputs["Emission Strength"].default_value = glow
    return mat


bpy.ops.wm.read_factory_settings(use_empty=True)
navy = material("Midnight enamel", "465975")
steel = material("Titanium armour", "99a6b5")
bone = material("Ceramic plates", "d5d9ce", 0.18)
carbon = material("Recessed machinery", "273443")
copper = material("Copper markings", "db7844", 0.18)
windows = material("Bridge and bay lights", "ffbd62", 0.08, 2.1)
ion = material("Drive apertures", "74d7ff", 0.12, 3.4)


def box(name, center, size, paint):
    bpy.ops.mesh.primitive_cube_add(size=1, location=center)
    obj = bpy.context.object
    obj.name = name
    for vertex in obj.data.vertices:
        for axis in range(3):
            vertex.co[axis] *= size[axis]
    obj.data.materials.append(paint)


def hull(name, x, stations, deck, shoulder, flank):
    """A continuous chamfered hull from (fore/aft, half-beam, keel, deck) stations."""
    profile = [(-0.72, 1), (-1, 0.75), (-1, 0.28), (-0.69, 0),
               (0.69, 0), (1, 0.28), (1, 0.75), (0.72, 1)]
    verts = [(x + u * width, y, low + (high - low) * v)
             for y, width, low, high in stations for u, v in profile]
    faces, paints = [], []
    for i in range(len(stations) - 1):
        for j, paint in enumerate((shoulder, flank, carbon, carbon, carbon, flank, shoulder, deck)):
            a, b = i * 8 + j, i * 8 + (j + 1) % 8
            faces.append((a, a + 8, b + 8, b))
            paints.append(paint)
    faces += [tuple(range(8)), tuple(reversed(range(len(verts) - 8, len(verts))))]
    paints += [carbon, shoulder]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    for mat in dict.fromkeys(paints):
        mesh.materials.append(mat)
    for poly, paint in zip(mesh.polygons, paints):
        poly.material_index = mesh.materials.find(paint.name)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)


def barrel(name, y, radius, depth, paint):
    bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=radius, depth=depth,
                                        location=(0, y, 0.74), rotation=(pi / 2, 0, 0))
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(paint)


def conduit(name, a, b, radius, paint, end_radius=None):
    a,b = Vector(a),Vector(b)
    bpy.ops.mesh.primitive_cone_add(vertices=12, radius1=radius, radius2=end_radius or radius,
                                    depth=(b-a).length, location=(a+b)/2)
    obj = bpy.context.object
    obj.name = name
    obj.rotation_euler = (b-a).to_track_quat("Z","Y").to_euler()
    obj.data.materials.append(paint)


# A heavy keel between two projecting flight decks. The gaps at the bow
# and the layered engine banks distinguish it from the single-seat fighters.
hull("Keel", 0, [(-12.6, 2.8, -2.2, 0.9), (-9, 4.7, -2.5, 1.6),
                 (2, 5.0, -2.1, 1.5), (8.1, 3.3, -1.6, 1.3),
                 (11.5, 1.4, -0.75, 0.8)], navy, steel, carbon)
for side in (-1, 1):
    x = 4.7 * side
    hull("Flight deck", x, [(-11.8, 1.35, -1.15, 1.0), (-8.4, 2.2, -1.35, 1.7),
                             (4.0, 2.35, -0.85, 1.6), (10.7, 1.4, -0.55, 1.3),
                             (14.7, 0.48, 0.02, 0.65)], steel, navy, carbon)
    for i, y in enumerate((-7.25, -4.48, -1.71, 1.06, 3.83)):
        hull("Segmented armour", x, [(y, 1.57, 1.43, 1.80), (y + 0.32, 1.72, 1.47, 1.99),
                                      (y + 2.52, 1.48, 1.44, 1.89)], bone if i in (1, 4) else steel, navy, carbon)
        box("Recessed broadside bay", (side * 6.94, y + 1, 0.28), (0.24, 2.28, 0.86), carbon)
        box("Bay guide light", (side * 7.08, y + 1, 0.62), (0.065, 1.72, 0.12), windows)
        for j in range(3):
            box("Bay shutter", (side * 7.08, y + 0.13 + 0.64 * j, 0.10), (0.08, 0.10, 0.48), steel)
    hull("Prow flashing", x, [(6.4, 0.96, 1.27, 1.60), (10.4, 0.83, 1.19, 1.40),
                              (13.2, 0.31, 0.72, 0.93)], copper, bone, navy)
    for nx in (x - 0.67, x + 0.67):
        hull("Engine bell", nx, [(-12.56, 0.67, -0.95, 0.84), (-11.15, 0.8, -1.08, 1.0)], carbon, steel, navy)
        box("Blue exhaust", (nx, -12.59, -0.04), (0.88, 0.11, 1.03), ion)
        for i in range(12):
            angle = pi*i/6
            dx,dz = 0.61*cos(angle),0.69*sin(angle)
            conduit("Drive bell stave",(nx+dx,-12.1,dz),(nx+dx*1.09,-12.95,dz*1.04),0.10,steel,0.075)
    # Exposed heat exchangers sit in the trench between each deck and the keel.
    for y in (-4.2,-0.6,3.0,6.6):
        cx = side*2.65
        box("Heat exchanger bed",(cx,y,1.55),(0.86,2.95,0.36),carbon)
        for j in range(9):
            box("Radiator fin",(cx,y-1.23+j*0.30,1.84),(0.78,0.11,0.39),steel)
        for dx in (-0.48,0.48):
            conduit("Coolant return",(cx+dx,y-1.53,1.65),(cx+dx,y+1.53,1.65),0.095,copper)
    for y in (-5.8,-2.8,0.2,3.2):
        conduit("Outer pressure line",(side*6.9,y,-0.25),(side*6.9,y+2.8,-0.25),0.13,steel)
    for y in (-9.8, -8.9):
        box("Stern stripe", (x, y, 1.58), (2.25, 0.30, 0.16), copper)

hull("Raised command spine", 0, [(-10, 2.1, 0.7, 2.8), (-7, 2.7, 0.7, 3.6),
                                 (-3.4, 1.8, 1.0, 3.3), (-1.4, 1.3, 1.1, 2.2)], navy, steel, carbon)
hull("Bridge glazing", 0, [(-7.7, 2.05, 3.11, 3.86), (-5.15, 1.78, 3.13, 3.76)], windows, windows, carbon)
hull("Bridge visor", 0, [(-7.92, 2.20, 3.72, 4.04), (-5.0, 1.9, 3.68, 3.92)], bone, navy, steel)
for x in (-1.2, 0, 1.2):
    box("Bridge mullion", (x, -7.72, 3.58), (0.14, 0.12, 0.58), navy)
for x, height in ((-0.8, 1.67), (0.7, 1.0)):
    box("Aerial mast", (x, -7.0, 4.0 + height / 2), (0.12, 0.18, height), steel)
    box("Navigation lamp", (x, -7.0, 4.03 + height), (0.22, 0.2, 0.14), windows)
    for y in (-7.65,-6.35):
        conduit("Antenna stay",(x,y,3.96),(x,-7.0,4+height*.78),0.048,steel)
for y, width in ((-10.2, 2.9), (-11.1, 2.5), (-12, 1.85)):
    box("Stern heat sink", (0, y, 1.3), (width, 0.38, 0.54), carbon)
hull("Projector spine", 0, [(0.2, 1.51, 1.14, 1.95), (5.1, 1.38, 0.8, 1.86),
                            (10.1, 1.14, 0.04, 1.60), (13.8, 0.85, 0.04, 1.47)], navy, steel, carbon)
for y in (2.6, 4.0, 5.4, 6.8):
    box("Projector heat sink", (0, y, 1.75), (2.2, 0.39, 0.39), steel)
barrel("Projector shroud", 13.9, 0.89, 2.45, carbon)
barrel("Copper collar", 15.02, 1.00, 0.48, copper)
barrel("Projector aperture", 15.28, 0.83, 0.16, carbon)
barrel("Lens", 15.38, 0.56, 0.08, windows)

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.join()
model = bpy.context.object
model.name = "Carrier"
bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
bpy.context.scene.cursor.location = (0, 0, 0)
bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
bm = bmesh.new()
bm.from_mesh(model.data)
bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
bm.to_mesh(model.data)
bm.free()
uv = model.data.uv_layers.active or model.data.uv_layers.new()
for face in model.data.polygons:
    n = face.normal
    major = max(range(3), key=lambda i: abs(n[i]))
    for i in face.loop_indices:
        x,y,z = model.data.vertices[model.data.loops[i].vertex_index].co
        a,b = ((y,z),(x,z),(x,y))[major]
        uv.data[i].uv = (a/12.0+0.5,b/12.0+0.5)
with TemporaryDirectory() as temp:
    wear, normal, coating = finish_atlas("carrier",temp,Image.new("L",(1024,1024),250),
                                          72,[(146,290,"CV 47",57),(746,700,"BAY 4",23)])
    color = file_image(temp,"carrier-plating",wear*248)
    for mat in (navy,steel,bone,carbon,copper):
        apply_maps(mat,normal,coating["alloy" if mat in (steel,carbon,copper) else "paint"])
        nt = mat.node_tree
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs[0].default_value = 1
        mix.inputs[6].default_value = mat.diffuse_color
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = color
        nt.links.new(tex.outputs["Color"],mix.inputs[7])
        nt.links.new(mix.outputs[2],nt.nodes.get("Principled BSDF").inputs["Base Color"])
bevel = model.modifiers.new("Rolled plate edges","BEVEL")
bevel.width = 0.052
bevel.segments = 2
bevel.harden_normals = True
model.modifiers.new("Face normals","WEIGHTED_NORMAL")
model.modifiers.new("Export triangles","TRIANGULATE")
muzzle = bpy.data.objects.new("Emitter", None)
muzzle.location = (0, 15.47, 0.74)
bpy.context.collection.objects.link(muzzle)
out = Path(__file__).resolve().parents[1] / "assets/models/mothership.glb"
bpy.ops.export_scene.gltf(filepath=str(out), export_animations=False, export_apply=True, export_tangents=True)
