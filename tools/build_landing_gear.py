"""Build the folding oleo strut reused at the three hardpoints of each player hull."""
from pathlib import Path

import bpy
from mathutils import Vector

bpy.ops.wm.read_factory_settings(use_empty=True)


def finish(name, rgb, metal, rough):
    m = bpy.data.materials.new(name)
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1)
    bsdf.inputs["Metallic"].default_value = metal
    bsdf.inputs["Roughness"].default_value = rough
    return m


body = finish("Shot-peened leg", (0.20, 0.21, 0.19), 0.68, 0.40)
piston = finish("Piston chrome", (0.62, 0.66, 0.67), 0.95, 0.20)
foot = finish("Landing shoe", (0.085, 0.098, 0.108), 0.76, 0.50)
band = finish("Inspection band", (0.57, 0.29, 0.06), 0.26, 0.46)


def ram(a,b,r,material):
    a,b = Vector(a),Vector(b)
    bpy.ops.mesh.primitive_cylinder_add(vertices=16,radius=r,depth=(b-a).length,location=(a+b)/2)
    o = bpy.context.object
    o.rotation_euler = (b-a).to_track_quat("Z","Y").to_euler()
    o.data.materials.append(material)
    for face in o.data.polygons:
        face.use_smooth = len(face.vertices)==4


ram((0,0,0.04),(0,-0.065,-0.35),0.054,body)
ram((0,-0.052,-0.27),(0,-0.108,-0.55),0.031,piston)
ram((0,-0.055,-0.30),(0,-0.060,-0.326),0.057,band)
ram((-0.065,0,0),(0.065,0,0),0.061,foot)
ram((-0.092,-0.110,-0.56),(0.092,-0.110,-0.56),0.040,body)
for x in (-0.05,0.05):
    ram((x,-0.035,-0.11),(x,0.092,-0.34),0.019,body)
    ram((x,0.092,-0.34),(x,-0.105,-0.54),0.016,piston)
ram((-0.064,0.092,-0.34),(0.064,0.092,-0.34),0.027,foot)
# Bent ends on the load-bearing steel shoe.
stations=[(-0.29,0.067,-0.577),(-0.23,0.115,-0.605),(0.018,0.11,-0.605),(0.078,0.066,-0.578)]
verts=[(sx*w,y,z+dz) for y,w,z in stations for sx,dz in ((-1,0),(1,0),(1,0.031),(-1,0.031))]
faces=[(0,3,2,1),(12,13,14,15)]
for i in range(3):
    for j in range(4):
        p = 4*i
        faces.append((p+j,p+(j+1)%4,p+4+(j+1)%4,p+4+j))
mesh=bpy.data.meshes.new("Bent steel shoe")
mesh.from_pydata(verts,[],faces)
mesh.materials.append(foot)
obj=bpy.data.objects.new("Landing shoe",mesh)
bpy.context.collection.objects.link(obj)
bpy.ops.object.select_all(action="SELECT")
bpy.context.view_layer.objects.active=obj
bpy.ops.object.join()
bevel=obj.modifiers.new("Machined edges","BEVEL")
bevel.width=0.003
bevel.segments=2
obj.modifiers.new("Area weighted normals","WEIGHTED_NORMAL")
bpy.ops.export_scene.gltf(filepath=str(Path(__file__).resolve().parents[1]/"assets/ships/landing-strut.glb"),
                          export_animations=False,export_apply=True)
