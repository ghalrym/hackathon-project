"""Build Delta Warp's three alternate hulls and four menu icons.

    blender -b --factory-startup --python tools/build_fleet.py

Models are authored at flight scale, nose along +Y. Each one carries a marker
at the starboard exhaust so the game can seat its two animated engine plumes.
"""
from pathlib import Path
from math import cos, pi, sin
from tempfile import TemporaryDirectory
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).resolve().parent))
from airframe_finish import apply_maps, finish_atlas

ASSETS = Path(__file__).resolve().parents[1] / "assets"
FLEET = ASSETS / "ships"


def material(name, hex_color, metal=0.35, rough=0.38, glow=0):
    rgb = [int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    rgba = [((c + 0.055) / 1.055) ** 2.4 if c > 0.04045 else c / 12.92 for c in rgb] + [1]
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = rgba
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = rgba
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if glow:
        bsdf.inputs["Emission Color"].default_value = rgba
        bsdf.inputs["Emission Strength"].default_value = glow
    return mat


steel = material("Brushed titanium", "838e9e")
white = material("Ceramic armour", "d1dbe0", 0.16)
silver = material("Machined edges", "b1c2cb", 0.55)
dark = material("Carbon underframe", "242d39")
seam = material("Panel recess", "111a23", 0.1)
glass = material("Canopy glass", "173d59", 0.22, 0.16)
glass_edge = material("Canopy facets", "376680", 0.25, 0.2)
for pane in (glass, glass_edge):
    bsdf = pane.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Alpha"].default_value = 0.45
    bsdf.inputs["Coat Weight"].default_value = 0.72
    bsdf.inputs["Coat Roughness"].default_value = 0.12
    pane.use_backface_culling = True
amber = material("Signal ochre", "f4a531", 0.18)
teal = material("Petrol enamel", "238684", 0.22)
indigo = material("Indigo enamel", "505a83", 0.22)
light = material("Ion blue", "64daff", 0.1, glow=2.8)
core = material("Ion core", "b6f7ff", 0.05, glow=3.5)
heat = material("Oxidised nozzle alloy", "736254", 0.77, 0.39)
brass = material("Service couplings","c59357",0.69,0.41)


def texture_image(pixels, path):
    Image.fromarray(pixels).save(path)
    image = bpy.data.images.load(str(path))
    image.pack()
    return image


def apply_finish(name, obj, directory):
    """Project airframe-specific panel joints and service markings onto the paint."""
    size = 1024
    rng = np.random.default_rng(42)
    noise = rng.normal(242, 2.6, (size, size)) + rng.normal(0, 0.9, (size, 1))
    plate = Image.fromarray(noise.clip(0, 255).astype("uint8"))
    draw = ImageDraw.Draw(plate)

    def pixel(x, y):
        return (round((0.5 + x / 3.3) * size), round((0.5 - y / 3.3) * size))

    def joint(points):
        # Engraved seam, with a narrow worn lip on the light-facing edge.
        for side in (-1, 1):
            pts = [pixel(side * x, y) for x, y in points]
            draw.line([(x + 1, y + 1) for x, y in pts], fill=255, width=2)
            draw.line(pts, fill=98, width=2)
            for x, y in (pts[0], pts[-1]):
                draw.ellipse((x - 2, y + 4, x, y + 6), fill=89)

    def stencil(x, y, length):
        # Short identification bars over a longer service stencil.
        for side in (-1, 1):
            for i, fraction in enumerate((1, 0.57, 0.72)):
                draw.line([pixel(side * x, y - i * 0.012),
                           pixel(side * (x + length * fraction), y - i * 0.012)],
                          fill=64, width=2)

    if name == "kestrel":
        joint([(0.035, 1.06), (0.11, 0.94), (0.12, 0.81)])
        joint([(0.08, 0.69), (0.17, 0.59), (0.20, 0.37)])
        joint([(0.31, -0.14), (0.53, -0.30), (0.62, -0.31), (0.85, -0.49)])
        joint([(0.65, -0.57), (0.73, -0.495), (0.86, -0.55), (1.05, -0.73)])
        joint([(0.04, -0.18), (0.11, -0.25), (0.12, -0.52), (0.06, -0.61)])
        stencil(0.54, -0.44, 0.11)
        stencil(0.14, 0.09, 0.055)
    elif name == "manta":
        joint([(0.06, 0.67), (0.23, 0.53), (0.32, 0.35)])
        joint([(0.28, -0.02), (0.35, -0.09), (0.43, -0.09), (0.46, -0.22)])
        joint([(0.77, 0.20), (0.88, 0.08), (1.09, 0.22), (1.22, 0.41)])
        joint([(0.81, -0.46), (0.97, -0.34), (1.01, -0.20), (1.18, -0.01)])
        joint([(1.15, 0.35), (1.25, 0.39), (1.36, 0.57)])
        stencil(0.85, -0.18, 0.13)
        stencil(0.23, -0.32, 0.055)
    else:
        joint([(0.42, 0.95), (0.48, 0.88), (0.58, 0.88), (0.65, 0.75)])
        joint([(0.36, 0.47), (0.42, 0.37), (0.42, 0.23), (0.49, 0.15), (0.68, 0.15)])
        joint([(0.34, 0.03), (0.43, -0.08), (0.69, -0.08), (0.76, -0.20)])
        joint([(0.05, -0.58), (0.18, -0.51), (0.28, -0.52), (0.35, -0.47)])
        joint([(0.67, -0.65), (0.8, -0.60), (0.89, -0.63), (1.02, -0.63)])
        stencil(0.52, 0.03, 0.12)
        stencil(0.47, 0.78, 0.07)

    registrations = {
        "kestrel": [(619, 594, "KT-17", 17), (337, 635, "LIFT", 9)],
        "manta": [(690, 553, "MA-08", 22), (274, 552, "RESCUE", 10)],
        "gemini": [(638, 485, "G / 02", 17), (305, 491, "G / 01", 16)],
    }
    wear, relief, coatings = finish_atlas(name, directory, plate, len(name)*13,
                                          registrations[name])
    paint_image = texture_image(np.uint8(np.clip(np.asarray(plate)*wear, 0, 255)), directory / f"{name}-plating.jpg")
    metallics = {steel, silver, white, teal, indigo, amber, dark}
    for mat in metallics:
        apply_maps(mat, relief, coatings["alloy" if mat in (steel, silver, dark) else "paint"])
        nodes = mat.node_tree.nodes
        bsdf = nodes.get("Principled BSDF")
        tex = nodes.get("Plating") or nodes.new("ShaderNodeTexImage")
        tex.name = "Plating"
        tex.image = paint_image
        mix = nodes.get("Finish") or nodes.new("ShaderNodeMix")
        mix.name = "Finish"
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs[0].default_value = 1
        mix.inputs[6].default_value = mat.diffuse_color
        mat.node_tree.links.new(tex.outputs["Color"], mix.inputs[7])
        mat.node_tree.links.new(mix.outputs[2], bsdf.inputs["Base Color"])

    # The opaque glazing picks up the same ice-blue sky reflection as the Delta cockpit.
    if not glass.node_tree.nodes.get("Glazing"):
        v, u = np.mgrid[0:1:192j, -1:1:192j]
        sheen = 0.72 * np.exp(-((v - 0.36 - u * 0.17) / 0.22) ** 2)
        sheen += 0.44 * np.exp(-((u + 0.58) / 0.13) ** 2) * (1 - v)
        sheen += 0.27 * np.exp(-((v - 0.43 - u * 0.39) / 0.021) ** 2)
        # Laminated smoked glass: canopy colour is subtle; the bay and the sky
        # provide the moving specular reflection.
        shade = np.array([19, 36, 44]) + sheen[..., None] * np.array([33, 49, 61])
        glazing = texture_image(shade.clip(0, 255).astype("uint8"), directory / "fleet-glazing.jpg")
        for mat in (glass, glass_edge):
            tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
            tex.name = "Glazing"
            tex.image = glazing
            mat.node_tree.links.new(tex.outputs["Color"], mat.node_tree.nodes.get("Principled BSDF").inputs["Base Color"])

    data = obj.data
    uv = data.uv_layers.new(name="Finish")
    glazed = [p for p in data.polygons if data.materials[p.material_index] in (glass, glass_edge)]
    pane = [data.vertices[i].co for p in glazed for i in p.vertices]
    left, right = min(v.x for v in pane), max(v.x for v in pane)
    aft, fore = min(v.y for v in pane), max(v.y for v in pane)
    for poly in data.polygons:
        windshield = data.materials[poly.material_index] in (glass, glass_edge)
        for index in poly.loop_indices:
            v = data.vertices[data.loops[index].vertex_index].co
            uv.data[index].uv = ((v.x - left) / (right - left), (v.y - aft) / (fore - aft)) if windshield else (
                0.5 + v.x / 3.3, 0.5 + v.y / 3.3)


def mesh(name, vertices, faces, paints):
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    for mat in dict.fromkeys(paints):
        data.materials.append(mat)
    for poly, mat in zip(data.polygons, paints):
        poly.material_index = data.materials.find(mat.name)
    bm = bmesh.new()
    bm.from_mesh(data)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(data)
    bm.free()
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    return obj


def loft(name, sections, deck, shoulder=None, flank=dark):
    """Chamfered longitudinal body. Sections are (x, y, half-width, bottom, top)."""
    vertices, faces, paints = [], [], []
    cross = [(-0.56, 1), (0.56, 1), (0.93, 0.77), (1, 0.38),
             (0.74, 0), (-0.74, 0), (-1, 0.38), (-0.93, 0.77)]
    bands = [deck, shoulder or deck, flank, dark, dark, dark, flank, shoulder or deck]
    for x, y, width, low, high in sections:
        vertices.extend((x + u * width, y, low + v * (high - low)) for u, v in cross)
    for i in range(len(sections) - 1):
        for j, mat in enumerate(bands):
            a = 8 * i + j
            b = 8 * i + (j + 1) % 8
            faces.append((a, b, b + 8, a + 8))
            paints.append(mat)
    faces += [tuple(range(8)), tuple(range(len(vertices) - 8, len(vertices)))]
    return mesh(name, vertices, faces, paints + [flank, flank])


def spine(name, x, sections, deck, shoulder=None, flank=dark):
    return loft(name, [(x, *s) for s in sections], deck, shoulder, flank)


def canopy(x, y, length, width, base, height):
    # A shallow tub carries the seat, shoulder restraints and instrument combing
    # under a laminated canopy. Leave the area above the sill free of armour.
    spine("Flight seat", x, [(y-0.34*length,width*.50,base,base+height*.48),
                              (y-0.22*length,width*.63,base,base+height*.74),
                              (y+0.10*length,width*.5,base,base+height*.21)],dark)
    spine("Head restraint", x, [(y-0.32*length,width*.38,base+height*.45,base+height*.77),
                                 (y-0.20*length,width*.38,base+height*.52,base+height*.79)],seam)
    for side in (-1,1):
        cx = x+side*width*.28
        spine("Harness webbing",cx,[(y-.26*length,width*.055,base+height*.67,base+height*.75),
                                    (y+.01*length,width*.055,base+height*.27,base+height*.32)],amber)
    spine("Instrument combing",x,[(y+.10*length,width*.69,base,base+height*.39),
                                  (y+.24*length,width*.54,base,base+height*.32)],dark)
    for name, scale, floor, rise, top, edge in [
        ("Canopy sill", 1.18, -0.030, 0.22, silver, steel),
        ("Pressure seal", 1.08, -0.009, 0.18, seam, dark),
        ("Armoured glass", 1.0, 0, 1.0, glass, glass_edge),
    ]:
        spine(name, x, [(y + k * length * scale, w * width * scale, base + floor,
                         base + floor + height * rise * h)
                        for k, w, h in [(-0.5, 0.57, 0.31), (-0.29, 1, 0.91),
                                        (0.12, 0.86, 1), (0.5, 0.16, 0.13)]], top, edge)


def engine(x, rear, width, height, z, shroud):
    """A recessed throat with alternating refractory petals and an injector grid."""
    spine("Engine cowl", x, [(rear + 0.065, width * 1.16, z - height, z + height * 1.2),
                              (rear + 0.22, width * 1.24, z - height, z + height * 1.65),
                              (rear + 0.53, width * 0.71, z - height * 0.66, z + height * 1.28)],
          shroud, steel)
    def point(angle, depth, scale):
        return (x + width*scale*cos(angle), rear+depth, z+height*scale*sin(angle))

    for i in range(16):
        a = i * 2*pi / 16
        vertices = [point(angle,offset,scale) for offset,scale in
                    ((0.17,1.04),(0.04,1.10),(-0.052,0.98),(-0.050,0.83),(0.054,0.52))
                    for angle in (a-0.198, a+0.198)]
        faces = [(j,j+1,j+3,j+2) for j in range(0,8,2)]
        mesh("Refractory petal",vertices,faces,
             [steel,heat if i%3 else dark,silver,heat if i%3==1 else dark])
        # The luminous throat is visible between dark vanes, behind the bell lip.
        mesh("Injector",[(x,rear+0.056,z),point(a-0.174,0.055,0.54),point(a+0.174,0.055,0.54)],
             [(0,1,2)],[light if i%2 else core])


def wing(side, sections, plates, stripe):
    """Spanwise wing stations. Paint and narrow sunken seams follow the airfoil."""
    # Chord fractions, starting at the cutting edge.
    chord = [0, 0.065, 0.22, 0.255, 0.67, 0.68, 0.94, 1]
    heights = [0.0, 0.55, 0.96, 1.0, 0.85, 0.84, 0.28, 0.05]
    vertices, faces, paints = [], [], []
    # Leave a fine graphite seam between adjacent sections of upper armour.
    stations = []
    for i, section in enumerate(sections):
        if 0 < i < len(sections) - 1:
            prev = sections[i - 1]
            stations.append(tuple(v + (p - v) * 0.018 for v, p in zip(section, prev)))
        stations.append(section)
    for x, front, rear, z, thickness in stations:
        vertices.extend((side * x, front + (rear - front) * t, z + thickness * h)
                        for t, h in zip(chord, heights))
        vertices.extend([(side * x, rear, z - thickness * 0.43),
                         (side * x, front, z - thickness * 0.43)])
    for i in range(len(stations) - 1):
        slit = stations[i + 1][0] - stations[i][0] < 0.017
        segment = sum(stations[i][0] >= station[0] for station in sections) - 1
        plate = plates[min(segment, len(plates) - 1)]
        bands = [silver, plate, stripe, plate, seam, steel, dark, dark, dark, steel]
        for j, paint in enumerate(bands):
            a, b = i * 10 + j, i * 10 + (j + 1) % 10
            faces.append((a, b, b + 10, a + 10))
            paints.append(seam if slit else paint)
    faces += [tuple(range(10)), tuple(range(len(vertices) - 10, len(vertices)))]
    mesh("Articulated wing panels", vertices, faces, paints + [dark, silver])


def fin(side, x, y, base):
    # Canted twin tails, with separate painted tips and a stepped leading edge.
    sections = [(0, 0, 0.028, 0.32), (0.18, 0.13, 0.023, 0.25),
                (0.30, 0.22, 0.012, 0.11), (0.36, 0.26, 0.006, 0.065)]
    vertices, faces, paints = [], [], []
    for h, sweep, w, chord in sections:
        cx = side * (x + h * 0.65)
        vertices.extend([(cx - w, y - sweep - chord, base + h),
                         (cx + w, y - sweep - chord, base + h),
                         (cx + w * 0.32, y - sweep + chord, base + h),
                         (cx - w * 0.32, y - sweep + chord, base + h)])
    for i, paint in enumerate((steel, white, amber)):
        for j in range(4):
            a, b = i * 4 + j, i * 4 + (j + 1) % 4
            faces.append((a, b, b + 4, a + 4))
            paints.append(paint)
    faces += [(0, 1, 2, 3), (12, 13, 14, 15)]
    mesh("Canted stabiliser", vertices, faces, paints + [dark, amber])


def vents(x, y, z, width, count):
    spine("Recessed cooling duct", x, [(y - 0.024, width, z - 0.018, z),
                                       (y + 0.048 * count, width, z - 0.018, z)], seam)
    for i in range(count):
        at = y + i * 0.048
        spine("Cooling louvre", x, [(at, width * 0.91, z, z + 0.012),
                                     (at + 0.022, width * 0.91, z, z + 0.025)], steel)


def rod(a,b,r,paint):
    a,b = Vector(a),Vector(b)
    axis = (b-a).normalized()
    u = axis.orthogonal().normalized()*r
    v = axis.cross(u)
    verts = [p + u*cos(i*pi/4) + v*sin(i*pi/4) for p in (a,b) for i in range(8)]
    faces = [(i,(i+1)%8,(i+1)%8+8,i+8) for i in range(8)]
    mesh("Service hardware",verts,faces + [tuple(reversed(range(8))),tuple(range(8,16))],[paint]*10)


def kestrel():
    spine("Needle fuselage", 0, [(-0.77, 0.22, -0.12, 0.11), (-0.38, 0.28, -0.17, 0.16),
                                 (0.26, 0.215, -0.14, 0.19), (0.74, 0.145, -0.10, 0.13),
                                 (1.49, 0.012, -0.016, 0.015)], white, steel)
    canopy(0, 0.34, 0.70, 0.145, 0.161, 0.134)
    vents(0, -0.50, 0.161, 0.062, 4)
    spine("Painted nose cap", 0, [(0.76, 0.081, 0.085, 0.135),
                                   (1.49, 0.012, -0.014, 0.018)], amber)
    for side in (-1, 1):
        wing(side, [(0.12, 0.52, -0.68, -0.045, 0.12), (0.42, 0.14, -0.70, -0.05, 0.085),
                    (0.76, -0.22, -0.63, -0.06, 0.068), (1.12, -0.67, -0.97, -0.035, 0.055)],
             [white, white, amber], dark)
        x = side * 0.26
        engine(x, -0.86, 0.16, 0.11, -0.035, white)
        spine("Dorsal intake", x, [(-0.61, 0.132, 0.04, 0.158),
                                   (-0.30, 0.14, 0.055, 0.18), (0.055, 0.094, 0.012, 0.12)], amber, white)
        vents(x, -0.46, 0.18, 0.071, 3)
        # Twin pressure lines tucked between the intake and the fuselage.
        for dx in (0.114,0.143):
            line = x+side*dx
            rod((line,-0.70,0.087),(line,-0.33,0.121),0.012,heat)
            rod((line,-0.62,0.094),(line,-0.58,0.098),0.017,brass)
        # A mass balance on the swept wing tip.
        rod((side*1.09,-0.87,0.010),(side*1.09,-0.53,0.013),0.022,dark)
        fin(side, 0.47, -0.41, 0.012)
    return (0.26, -0.87, -0.035)


def manta():
    # Broad arched centre, paired swept-forward crescents, engines embedded in the shoulders.
    spine("Lenticular centre hull", 0, [(-0.66, 0.26, -0.095, 0.145), (-0.42, 0.59, -0.16, 0.176),
                                        (0.14, 0.57, -0.16, 0.16), (0.55, 0.34, -0.08, 0.11),
                                        (0.83, 0.065, -0.022, 0.03)], teal, steel)
    canopy(0, 0.24, 0.64, 0.27, 0.134, 0.133)
    for side in (-1, 1):
        wing(side, [(0.23, 0.62, -0.57, -0.022, 0.158), (0.55, 0.37, -0.78, -0.033, 0.12),
                    (0.81, 0.36, -0.69, -0.044, 0.10), (1.12, 0.56, -0.37, -0.09, 0.08),
                    (1.35, 0.83, 0.11, -0.11, 0.052), (1.47, 1.00, 0.67, -0.068, 0.025)],
             [teal, white, teal, white, dark], white)
        x = side * 0.62
        engine(x, -0.83, 0.18, 0.098, -0.026, teal)
        spine("Shoulder fairing", x, [(-0.54, 0.19, 0.005, 0.13),
                                       (-0.18, 0.152, 0.004, 0.155), (0.33, 0.067, -0.01, 0.08)], teal, white)
        vents(x, -0.41, 0.151, 0.091, 4)
        # Five canted cooling gills in the crescent wing roots.
        for j in range(5):
            at = -0.26+j*.084
            rod((side*.75,at,0.062),(side*.91,at+.055,0.051),0.015,dark)
        spine("Navigation strip", side * 0.33, [(-0.45, 0.016, 0.166, 0.182),
                                                 (-0.18, 0.017, 0.166, 0.182)], light)
    vents(0, -0.49, 0.179, 0.136, 5)
    return (0.62, -0.84, -0.026)


def gemini():
    # Two full-length hulls tied together at the stern, with open space between the prows.
    spine("Cockpit bridge", 0, [(-0.81, 0.31, -0.12, 0.06), (-0.53, 0.65, -0.12, 0.14),
                                (-0.18, 0.65, -0.07, 0.15), (0.07, 0.30, -0.05, 0.12),
                                (0.23, 0.14, -0.05, 0.07)], steel, indigo)
    canopy(0, -0.20, 0.57, 0.215, 0.132, 0.16)
    spine("Split windshield mullion", 0, [(-0.49, 0.012, 0.16, 0.188), (-0.365, 0.014, 0.26, 0.282),
                                          (-0.132, 0.014, 0.28, 0.296), (0.087, 0.008, 0.144, 0.157)], silver)
    for side in (-1, 1):
        x = side * 0.55
        loft("Forked outrigger", [(x, -0.79, 0.21, -0.14, 0.12), (x, -0.46, 0.26, -0.15, 0.19),
                                   (x, 0.19, 0.24, -0.14, 0.175), (x, 0.69, 0.177, -0.11, 0.135),
                                   (x - side * 0.07, 1.31, 0.06, -0.045, 0.04),
                                   (x - side * 0.09, 1.47, 0.016, -0.02, 0.005)], white, indigo)
        spine("Forward armour inset", x, [(0.22, 0.14, 0.13, 0.179),
                                          (0.65, 0.103, 0.10, 0.148),
                                          (0.96, 0.044, 0.05, 0.101)], indigo)
        spine("Running light", x, [(0.31, 0.014, 0.165, 0.178),
                                    (0.72, 0.011, 0.13, 0.151)], light)
        engine(x, -0.94, 0.205, 0.128, -0.012, white)
        vents(x, -0.49, 0.193, 0.129, 6)
        # The fork exposes its hydraulic service trench on the inner face.
        for dz in (-0.060,0.005):
            line = x-side*0.225
            rod((line,-0.57,dz),(line,0.27,dz+0.04),0.016,heat)
            for at in (-0.37,-0.06,0.18):
                rise = (at+0.57)*0.048
                rod((line,at,dz+rise),(line,at+0.042,dz+rise+0.002),0.023,brass)
        wing(side, [(0.67, -0.14, -0.70, -0.042, 0.093),
                    (0.92, -0.35, -0.77, -0.054, 0.071),
                    (1.10, -0.58, -0.79, -0.057, 0.044)], [indigo, white], indigo)
    return (0.55, -0.95, -0.012)


def icon(name):
    scene = bpy.context.scene
    cam = bpy.data.objects.new("Plan view", bpy.data.cameras.new("Plan view"))
    bpy.context.collection.objects.link(cam)
    cam.location = (0, 0.12, 8)
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 3.3
    scene.camera = cam
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "SINGLE"
    scene.display.shading.single_color = (0.58, 0.78, 0.87)
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = "WORLD"
    scene.view_settings.view_transform = "Standard"
    scene.render.film_transparent = True
    scene.render.resolution_x = scene.render.resolution_y = 128
    scene.render.resolution_percentage = 100
    scene.render.filepath = str(FLEET / f"{name}-plan.png")
    bpy.ops.render.render(write_still=True)


def clear_objects():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


clear_objects()
bpy.ops.import_scene.gltf(filepath=str(ASSETS / "models/triangle-spaceship.glb"))
for obj in bpy.context.scene.objects:
    if obj.parent is None:
        obj.matrix_world = Matrix.Rotation(pi, 4, "Z") @ Matrix.Scale(0.60, 4) @ obj.matrix_world
icon("delta")

for name, build in [("kestrel", kestrel), ("manta", manta), ("gemini", gemini)]:
    clear_objects()
    nozzle = build()
    bpy.ops.object.select_all(action="SELECT")
    bpy.context.view_layer.objects.active = bpy.context.selected_objects[0]
    bpy.ops.object.join()
    bpy.context.object.name = "Airframe"
    exhaust = bpy.data.objects.new("Exhaust", None)
    bpy.context.collection.objects.link(exhaust)
    exhaust.location = nozzle
    with TemporaryDirectory() as scratch:
        apply_finish(name, bpy.context.object, Path(scratch))
        bevel = bpy.context.object.modifiers.new("Machined edge radius","BEVEL")
        bevel.width = 0.005
        bevel.segments = 2
        bevel.harden_normals = True
        bpy.context.object.modifiers.new("Panel normals","WEIGHTED_NORMAL")
        bpy.context.object.modifiers.new("Export triangles","TRIANGULATE")
        bpy.ops.export_scene.gltf(filepath=str(FLEET / f"{name}.glb"), export_format="GLB",
                                  export_animations=False, export_apply=True, export_yup=True, export_tangents=True)
    icon(name)
