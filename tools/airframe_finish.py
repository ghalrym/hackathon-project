"""Bake service hatches, engraved joints and rubbed metal into glTF material maps."""
from pathlib import Path

import bpy
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont


def file_image(directory, name, values, data=False):
    path = Path(directory) / (name + ".png")
    Image.fromarray(np.clip(values, 0, 255).astype(np.uint8)).save(path)
    image = bpy.data.images.load(str(path))
    if data:
        image.colorspace_settings.name = "Non-Color"
    image.pack()
    return image


def finish_atlas(name, directory, layout, seed, markings=(), mask=None, substrate=None):
    """Layout and masks use image coordinates. Share relief between bare and enamel finishes."""
    rng = np.random.default_rng(seed)
    size = layout.width
    u = size / 1024
    def px(v):
        return round(u * v)

    relief = layout.copy()
    h = ImageDraw.Draw(relief)
    ink = Image.new("L", layout.size, 255)
    d = ImageDraw.Draw(ink)
    # Offset successive rows to avoid four plates meeting at a single fastener.
    y = -24
    while y < 1024:
        height = int(rng.integers(80, 156))
        x = -int(rng.integers(0, 180))
        while x < 1024:
            width = int(rng.integers(86, 200))
            c = int(rng.integers(7, 18))
            edge = [(px(a), px(b)) for a,b in ((x,y+height), (x+width-c,y+height),
                                               (x+width,y+height-c), (x+width,y))]
            h.line(edge, fill=112, width=max(1, px(2)))
            d.line(edge, fill=166, width=max(1, px(2)))
            for a,b in ((x+7,y+height-7), (x+width-c-7,y+height-7)):
                a,b = px(a),px(b)
                h.ellipse((a-px(1),b-px(1),a+px(2),b+px(2)), fill=76)
            if rng.random() < 0.32:
                # Flush removable inspection cover with chamfered corners and captive screws.
                a,b,w,l = x+13,y+11,min(width-30,53),min(height-27,35)
                hatch = [(a+5,b),(a+w-5,b),(a+w,b+5),(a+w,b+l-5),
                         (a+w-5,b+l),(a+5,b+l),(a,b+l-5),(a,b+5),(a+5,b)]
                path = [(px(i),px(j)) for i,j in hatch]
                h.line(path, fill=90, width=px(2))
                d.line(path, fill=147, width=px(2))
                for i in (a+6,a+w-6):
                    for j in (b+5,b+l-5):
                        h.ellipse((px(i-1),px(j-1),px(i+1),px(j+1)), fill=51)
                d.line((px(a+9),px(b+7),px(a+21),px(b+7)), fill=112,width=px(2))
            x += width
        y += height

    for x,y,label,point_size in markings:
        font = ImageFont.load_default(size=px(point_size))
        d.text((px(x),px(y)), label, font=font, fill=52, stroke_width=0)
        d.line((px(x),px(y+point_size+2),px(x+18),px(y+point_size+2)),fill=82,width=px(2))

    grain = rng.normal(0, 1, layout.size).astype(np.float32)
    low = Image.fromarray(rng.integers(0, 255, (31, 31), dtype=np.uint8))
    low = (np.asarray(low.resize(layout.size, Image.Resampling.BICUBIC), dtype=np.float32)-127)/127
    joint = (255 - np.asarray(ink, dtype=np.float32)) / 255
    plane = np.asarray(relief.filter(ImageFilter.GaussianBlur(0.75*u)), dtype=np.float32) / 255
    coverage = 1.0 if mask is None else mask
    cavity = (1-plane) * coverage
    dy, dx = np.gradient((plane-1)*coverage + grain*0.008)
    n = np.stack((-dx*2.6*u, dy*2.6*u, np.ones_like(dx)), axis=2)
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    normal = file_image(directory, name+"-relief", 127.5*(1+n), True)
    modulation = np.clip(1 - coverage*(joint*0.58 + cavity*0.17 + 0.054*(low+1)) + 0.009*grain, 0.28, 1.02)
    maps = {}
    for finish, rough, metal in (("paint",0.43,0.13),("alloy",0.34,0.79)):
        r = rough+0.073*low+0.025*grain+0.2*cavity
        m = metal-0.07*cavity
        if substrate is not None:
            glass, exposed = substrate
            r = r*(1-glass) + 0.125*glass
            m = (m + exposed*0.61)*(1-glass) + glass*0.18
        packed = np.stack((np.ones_like(r), r, m+np.zeros_like(r)),axis=2)
        maps[finish] = file_image(directory,name+"-"+finish,packed*255,True)
        if substrate is not None:
            break
    return modulation, normal, maps


def apply_maps(material, normal, packed):
    nodes = material.node_tree.nodes
    link = material.node_tree.links.new
    bsdf = nodes.get("Principled BSDF")
    def sampler(name, image):
        tex = nodes.get(name) or nodes.new("ShaderNodeTexImage")
        tex.name = name
        tex.image = image
        return tex.outputs["Color"]
    bump = nodes.get("Engraving") or nodes.new("ShaderNodeNormalMap")
    bump.name = "Engraving"
    link(sampler("Surface relief",normal), bump.inputs["Color"])
    link(bump.outputs["Normal"], bsdf.inputs["Normal"])
    rgb = nodes.get("Coating channels") or nodes.new("ShaderNodeSeparateColor")
    rgb.name = "Coating channels"
    link(sampler("Coating",packed), rgb.inputs[0])
    link(rgb.outputs["Green"],bsdf.inputs["Roughness"])
    link(rgb.outputs["Blue"],bsdf.inputs["Metallic"])
