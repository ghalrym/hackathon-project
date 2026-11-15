"""Build the asteroid models used by the game.

    blender -b --factory-startup --python tools/build_asteroid_models.py [-- --renders DIR] [--only N]

Each rock is a sphere pushed around by noise, flat fracture planes and impact
craters. A dense version carries all the detail; it is baked down to a normal
map and a colour map on a game-resolution version, which is exported as GLB to
assets/models/asteroids/.
"""
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector, noise

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "assets", "models", "asteroids")

# ---------------------------------------------------------------- parameters
GAME_GRID = 40      # quads along each edge of the six sphere patches (19k tris)
DENSE_GRID = 224    # same, for the version the maps are baked from
TEX_W, TEX_H = 2048, 1024
GUTTER = 10 / 512   # empty border inside each patch's cell of the texture
SMALL_CRATER = 0.10  # craters narrower than this (radians) live in the normal map only

# (dark, light) surface tones, sRGB.
TAN = ((0.40, 0.34, 0.28), (0.66, 0.58, 0.49))
CHARCOAL = ((0.28, 0.28, 0.29), (0.50, 0.50, 0.51))
GREY = ((0.37, 0.37, 0.36), (0.64, 0.63, 0.60))

# squash: axis lengths. facets: flat fracture faces. craters: (large, medium, small).
ROCKS = [
    dict(seed=3, tones=TAN, squash=(1.0, 0.82, 0.70), facets=2, craters=(3, 14, 70)),
    dict(seed=8, tones=CHARCOAL, squash=(1.0, 0.74, 0.66), facets=4, craters=(2, 9, 50)),
    dict(seed=13, tones=GREY, squash=(1.0, 0.90, 0.80), facets=1, craters=(4, 16, 80)),
    dict(seed=21, tones=TAN, squash=(1.0, 0.68, 0.60), facets=5, craters=(2, 8, 40)),
    dict(seed=34, tones=CHARCOAL, squash=(1.0, 0.86, 0.76), facets=3, craters=(3, 12, 60)),
    dict(seed=55, tones=GREY, squash=(1.0, 0.78, 0.72), facets=3, craters=(3, 14, 70)),
]

# The six patches of a cube blown up into a sphere: (outward, across, up).
PATCHES = [
    ((1, 0, 0), (0, 0, -1), (0, 1, 0)), ((-1, 0, 0), (0, 0, 1), (0, 1, 0)),
    ((0, 1, 0), (1, 0, 0), (0, 0, -1)), ((0, -1, 0), (1, 0, 0), (0, 0, 1)),
    ((0, 0, 1), (1, 0, 0), (0, 1, 0)), ((0, 0, -1), (-1, 0, 0), (0, 1, 0)),
]


# --------------------------------------------------------------------- shape
def sphere_grid(n):
    """A unit sphere as six n x n quad patches. Returns welded directions, quads
    indexing them, and a UV per quad corner (each patch gets its own cell of a
    3 x 2 texture atlas)."""
    steps = np.tan(np.linspace(-1, 1, n + 1) * math.pi / 4)   # even angular spacing
    across, up = np.meshgrid(steps, steps)
    u, v = np.meshgrid(np.linspace(0, 1, n + 1), np.linspace(0, 1, n + 1))
    directions, uvs = [], []
    for i, (out, a, b) in enumerate(PATCHES):
        p = np.array(out) + across[..., None] * np.array(a) + up[..., None] * np.array(b)
        directions.append((p / np.linalg.norm(p, axis=-1, keepdims=True)).reshape(-1, 3))
        cell = np.stack([(i % 3 + GUTTER + u * (1 - 2 * GUTTER)) / 3,
                         (i // 3 + GUTTER + v * (1 - 2 * GUTTER)) / 2], -1)
        uvs.append(cell.reshape(-1, 2))
    directions, uvs = np.concatenate(directions), np.concatenate(uvs)

    corner = (np.arange(n)[:, None] * (n + 1) + np.arange(n)[None, :]).reshape(-1)
    quad = np.stack([corner, corner + 1, corner + n + 2, corner + n + 1], -1)
    quads = np.concatenate([quad + i * (n + 1) ** 2 for i in range(6)])

    _, first, welded = np.unique(np.round(directions, 5), axis=0,
                                 return_index=True, return_inverse=True)
    return directions[first], welded.reshape(-1)[quads], uvs[quads]


def fbm(points, octaves):
    return np.fromiter((noise.fractal(p, 1.0, 2.0, octaves) for p in points.tolist()),
                       np.float64, len(points))


def ridged(points, octaves):
    return np.fromiter((noise.ridged_multi_fractal(p, 1.0, 2.0, octaves, 1.0, 2.0)
                        for p in points.tolist()), np.float64, len(points))


def crater(t, depth, floor):
    """Height change at t crater-radii from the centre: a bowl with a raised lip."""
    bowl = np.where(t < 1, depth * (np.minimum(t, 1) ** floor - 1), 0.0)
    lip = 0.22 * depth * np.exp(-((t - 1) / 0.28) ** 2)
    return bowl + lip


class Rock:
    def __init__(self, spec):
        rng = np.random.default_rng(spec["seed"])

        def unit(count):
            v = rng.normal(size=(count, 3))
            return v / np.linalg.norm(v, axis=1, keepdims=True)

        large, medium, small = spec["craters"]
        self.spec = spec
        self.offset = rng.uniform(-40, 40, 3)          # where this rock sits in the noise
        self.facets = list(zip(unit(spec["facets"]), rng.uniform(0.70, 0.90, spec["facets"])))
        radii = np.concatenate([rng.uniform(0.30, 0.52, large),
                                rng.uniform(SMALL_CRATER, 0.24, medium),
                                rng.uniform(0.025, 0.09, small)])
        self.craters = list(zip(unit(len(radii)), radii, rng.uniform(0.75, 1.2, len(radii))))
        self.squash = np.array(spec["squash"])

    def surface(self, directions, fine):
        """Points on the rock for the given unit directions. Without `fine`, only
        the features a game-resolution mesh can hold."""
        r = 1 + 0.34 * fbm(directions * 1.1 + self.offset, 2)
        r += 0.10 * fbm(directions * 2.7 - self.offset, 2)
        # Distinct parent bodies: a contact binary, a laminated slab and a
        # breccia fragment broken off a larger mass.
        x, y, z = directions.T
        seed = self.spec["seed"]
        if seed == 3:
            r += 0.15 * x * x - 0.23 * np.exp(-((x + 0.16) / 0.32) ** 2)
        elif seed in (8, 21):
            bedding = z * 8.0 + 2.0 * y + fbm(directions * 2 + self.offset, 2)
            r += 0.043 * np.tanh(3 * np.sin(bedding)) - 0.07 * z * z
        elif seed == 55:
            r += 0.13 * np.abs(x - 0.5 * y) - 0.10 * np.abs(z + y)
        for normal, cut in self.facets:
            # Soft minimum with the plane, so fracture faces meet the rock in a bevel.
            plane = cut / np.maximum(directions @ normal, 0.05)
            r = -np.log(np.exp(-28 * r) + np.exp(-28 * plane)) / 28
        for centre, radius, strength in self.craters:
            if radius < SMALL_CRATER and not fine:
                continue
            t = np.arccos(np.clip(directions @ centre, -1, 1)) / radius
            near = t < 2.2
            r[near] += crater(t[near], 0.24 * radius * strength, 3.0 if radius > 0.25 else 2.0)
        r += 0.035 * fbm(directions * 6 + self.offset, 6 if fine else 2)
        if fine:
            r += 0.012 * (ridged(directions * 11 + self.offset, 4) - 1)
        return directions * r[:, None] * self.squash


def make_object(name, points, quads, uvs=None):
    mesh = bpy.data.meshes.new(name)
    mesh.vertices.add(len(points))
    mesh.vertices.foreach_set("co", points.ravel())
    mesh.loops.add(quads.size)
    mesh.loops.foreach_set("vertex_index", quads.ravel())
    mesh.polygons.add(len(quads))
    mesh.polygons.foreach_set("loop_start", np.arange(0, quads.size, 4))
    if uvs is not None:
        mesh.uv_layers.new(name="UVMap").data.foreach_set("uv", uvs.ravel())
    mesh.update()
    mesh.validate()
    mesh.polygons.foreach_set("use_smooth", np.ones(len(quads), bool))
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


# ----------------------------------------------------------------- materials
def linear(srgb, gain=1.0):
    return tuple(min(c * gain, 1.0) ** 2.2 for c in srgb) + (1.0,)


def source_material(rock):
    """Procedural surface for the dense mesh: what the maps are baked from."""
    dark, light = rock.spec["tones"]
    mat = bpy.data.materials.new("asteroid-source")
    if not mat.node_tree:
        mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")

    def node(kind, **props):
        n = nt.nodes.new(kind)
        for key, value in props.items():
            setattr(n, key, value)
        return n

    def link(a, b):
        nt.links.new(a, b)

    place = node("ShaderNodeMapping")
    place.inputs["Location"].default_value = Vector(rock.offset)
    link(node("ShaderNodeTexCoord").outputs["Object"], place.inputs["Vector"])

    def noise_tex(scale, detail, roughness=0.6):
        n = node("ShaderNodeTexNoise")
        n.inputs["Scale"].default_value = scale
        n.inputs["Detail"].default_value = detail
        n.inputs["Roughness"].default_value = roughness
        link(place.outputs["Vector"], n.inputs["Vector"])
        return n.outputs[0]

    def ramp(source, stops):
        n = node("ShaderNodeValToRGB")
        elements = n.color_ramp.elements
        while len(elements) < len(stops):
            elements.new(0.5)
        for element, (position, color) in zip(elements, stops):
            element.position, element.color = position, color
        link(source, n.inputs[0])
        return n.outputs[0]

    def mix(factor, a, b, blend="MIX"):
        n = node("ShaderNodeMix", data_type="RGBA", blend_type=blend)
        for socket, value in ((n.inputs[0], factor), (n.inputs[6], a), (n.inputs[7], b)):
            if isinstance(value, bpy.types.NodeSocket):
                link(value, socket)
            else:
                socket.default_value = value
        return n.outputs[2]

    def math_node(operation, a, b):
        n = node("ShaderNodeMath", operation=operation)
        for socket, value in zip(n.inputs, (a, b)):
            if isinstance(value, bpy.types.NodeSocket):
                link(value, socket)
            else:
                socket.default_value = value
        return n.outputs[0]

    # Colour: broad mineral patches, finer mottling, dust settled in the hollows
    # and paler rock exposed on ridges and crater lips.
    patches = ramp(noise_tex(1.4, 5), [(0.36, linear(dark)), (0.68, linear(light))])
    mottled = mix(ramp(noise_tex(8, 9, 0.7), [(0.35, (0, 0, 0, 1)), (0.7, (1, 1, 1, 1))]),
                  mix(1.0, patches, (0.72, 0.72, 0.72, 1), "MULTIPLY"), patches)
    relief = node("ShaderNodeNewGeometry").outputs["Pointiness"]
    dusty = mix(ramp(relief, [(0.44, (0, 0, 0, 1)), (0.50, (1, 1, 1, 1))]),
                linear(dark, 0.7), mottled)
    worn = mix(ramp(relief, [(0.52, (0, 0, 0, 1)), (0.60, (1, 1, 1, 1))]),
               dusty, linear(light, 1.25))
    fractures = node("ShaderNodeTexVoronoi", feature="DISTANCE_TO_EDGE")
    fractures.inputs["Scale"].default_value = 3.7
    link(place.outputs["Vector"], fractures.inputs["Vector"])
    broken = math_node("ADD", fractures.outputs["Distance"],
                       math_node("MULTIPLY", noise_tex(19, 3), 0.13))
    fissures = ramp(broken, [(0.057, (0, 0, 0, 1)), (0.085, (1, 1, 1, 1))])
    mineral = mix(fissures, linear(dark, 0.56), worn)
    specks = ramp(noise_tex(68, 2), [(0.63, (0, 0, 0, 1)), (0.74, (1, 1, 1, 1))])
    link(mix(specks, mineral, linear(light, 1.14)), bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.9

    # Bump: lumpy regolith, scattered pits, and fine grain.
    voronoi = node("ShaderNodeTexVoronoi")
    voronoi.inputs["Scale"].default_value = 34
    link(place.outputs["Vector"], voronoi.inputs["Vector"])
    pits = ramp(voronoi.outputs["Distance"], [(0.0, (0, 0, 0, 1)), (0.16, (1, 1, 1, 1))])
    height = math_node("ADD", noise_tex(26, 10, 0.62), math_node("MULTIPLY", pits, 0.5))
    height = math_node("ADD", height, math_node("MULTIPLY", noise_tex(120, 3), 0.22))
    height = math_node("ADD", height, math_node("MULTIPLY", fissures, 0.9))
    bump = node("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.4
    bump.inputs["Distance"].default_value = 0.03
    link(height, bump.inputs["Height"])
    link(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def game_material(name, color_image, normal_image, weathering):
    mat = bpy.data.materials.new(name)
    if not mat.node_tree:
        mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    maps = nt.nodes.new("ShaderNodeTexImage")
    maps.image = weathering
    channels = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(maps.outputs["Color"], channels.inputs[0])
    nt.links.new(channels.outputs["Green"], bsdf.inputs["Roughness"])
    nt.links.new(channels.outputs["Blue"], bsdf.inputs["Metallic"])
    color = nt.nodes.new("ShaderNodeTexImage")
    color.image = color_image
    nt.links.new(color.outputs["Color"], bsdf.inputs["Base Color"])
    normal = nt.nodes.new("ShaderNodeTexImage")
    normal.image = normal_image
    normal_map = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(normal.outputs["Color"], normal_map.inputs["Color"])
    nt.links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


# -------------------------------------------------------------------- baking
def use_gpu(scene):
    scene.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for kind in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
        try:
            prefs.compute_device_type = kind
        except TypeError:
            continue
        prefs.get_devices()
        devices = [d for d in prefs.devices if d.type == kind]
        if devices:
            for device in prefs.devices:
                device.use = device.type == kind
            scene.cycles.device = "GPU"
            return


def new_image(name, data):
    image = bpy.data.images.new(name, TEX_W, TEX_H, alpha=False)
    if data:
        image.colorspace_settings.name = "Non-Color"
    return image


def bake(kind, image, game, dense, samples, **options):
    """Bake one map from the dense mesh onto the game mesh's UVs."""
    scene = bpy.context.scene
    scene.cycles.samples = samples
    nt = game.active_material.node_tree
    target = nt.nodes.get("bake") or nt.nodes.new("ShaderNodeTexImage")
    target.name = "bake"
    target.image = image
    nt.nodes.active = target
    for obj in scene.objects:
        obj.select_set(obj in (game, dense))
    bpy.context.view_layer.objects.active = game
    bpy.ops.object.bake(type=kind, use_selected_to_active=True, cage_extrusion=0.1,
                        max_ray_distance=0.4, margin=12, **options)


def pixels(image):
    buf = np.empty(TEX_W * TEX_H * 4, np.float32)
    image.pixels.foreach_get(buf)
    return buf.reshape(TEX_H, TEX_W, 4)


def build(index, spec, renders):
    name = f"asteroid-{index + 1:02d}"
    rock = Rock(spec)

    directions, quads, uvs = sphere_grid(GAME_GRID)
    points = rock.surface(directions, fine=False)
    centre = points.mean(axis=0)
    size = np.linalg.norm(points - centre, axis=1).mean()   # normalise: mean radius 1
    game = make_object(name, (points - centre) / size, quads, uvs)

    directions, quads, _ = sphere_grid(DENSE_GRID)
    dense = make_object(name + "-dense", (rock.surface(directions, fine=True) - centre) / size, quads)
    dense.data.materials.append(source_material(rock))
    game.data.materials.append(bpy.data.materials.new(name + "-bake"))

    normal = new_image(name + "_normal", data=True)
    color = new_image(name + "_color", data=False)
    shade = new_image(name + "_occlusion", data=True)
    bake("NORMAL", normal, game, dense, samples=8)
    bake("DIFFUSE", color, game, dense, samples=4, pass_filter={"COLOR"})
    bake("AO", shade, game, dense, samples=96)

    # Fold the occlusion into the colour: craters and cracks read as shadowed
    # and dusty whatever the lighting.
    rgba = pixels(color)
    ao = pixels(shade)[..., 0]
    value = rgba[..., :3].mean(axis=2)
    # Fractured grains catch grazing light; recessed powder stays matte.
    grains = np.clip((value - np.quantile(value, 0.65)) / (value.std() * 3 + 1e-5), 0, 1)
    weathering = new_image(name + "_weathering", data=True)
    packed = np.ones_like(rgba)
    packed[..., 1] = np.clip(0.95 - 0.25 * grains + 0.04 * (1 - ao), 0, 1)
    packed[..., 2] = (0.15 if spec["seed"] in (8, 34) else 0.035) * grains**2
    weathering.pixels.foreach_set(packed.ravel())
    rgba[..., :3] *= (0.55 + 0.45 * ao[..., None]) ** (1 / 2.2)
    color.pixels.foreach_set(rgba.ravel())

    for image in (normal, color, weathering):
        image.filepath_raw = os.path.join(bpy.app.tempdir, image.name + ".png")
        image.file_format = "PNG"
        image.save()

    bpy.data.objects.remove(dense)
    game.data.materials.clear()
    game.data.materials.append(game_material(name, color, normal, weathering))
    for obj in bpy.context.scene.objects:
        obj.select_set(obj == game)
    bpy.context.view_layer.objects.active = game
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, name + ".glb")
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True,
                              export_apply=True, export_yup=True, export_tangents=True,
                              export_image_format="JPEG", export_image_quality=90)
    print(f"[asteroid] {name}: {len(game.data.polygons) * 2} tris, "
          f"{os.path.getsize(path) / 1e6:.1f} MB")
    if renders:
        render_views(game, renders)
    bpy.data.objects.remove(game)


# -------------------------------------------------------------------- output
def render_views(obj, out):
    os.makedirs(out, exist_ok=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.film_transparent = True
    scene.render.resolution_x, scene.render.resolution_y = 900, 900
    scene.view_settings.view_transform = "Standard"

    world = scene.world or bpy.data.worlds.new("preview")
    if not world.node_tree:
        world.use_nodes = True
    background = world.node_tree.nodes["Background"]
    background.inputs["Color"].default_value = (0.3, 0.4, 0.6, 1)
    background.inputs["Strength"].default_value = 0.08
    scene.world = world

    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 4.0
    sun.rotation_euler = (math.radians(55), 0, math.radians(-50))
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.lens = 85
    for extra in (sun, cam):
        scene.collection.objects.link(extra)
    scene.camera = cam
    for view, location in (("a", (5.5, -5.5, 3)), ("b", (-6, 4, -2.5))):
        cam.location = location
        cam.rotation_euler = (-Vector(location)).to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = os.path.join(out, f"{obj.name}-{view}.png")
        bpy.ops.render.render(write_still=True)
    for extra in (sun, cam):
        bpy.data.objects.remove(extra)
    scene.render.engine = "CYCLES"


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    renders = argv[argv.index("--renders") + 1] if "--renders" in argv else None
    only = int(argv[argv.index("--only") + 1]) if "--only" in argv else None

    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    scene = bpy.context.scene
    use_gpu(scene)
    scene.world = scene.world or bpy.data.worlds.new("bake")
    scene.world.light_settings.distance = 0.6          # occlusion reach, in rock radii

    for index, spec in enumerate(ROCKS):
        if only is None or only == index + 1:
            build(index, spec, renders)


main()
