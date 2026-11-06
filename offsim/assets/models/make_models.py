"""Our own low-poly glTF models (MIT, made here with Blender's bpy). Units: metres, +Y forward, Z up.

    python offsim/assets/models/make_models.py      # writes *.glb next to this file

Cartoony on purpose: few faces, flat colours from the house palette, exaggerated features (big
helideck, fat rotor hub) so they read at map scale. Size them in the scene with `sizeScale`.
"""
from pathlib import Path

import bpy

OUT = Path(__file__).resolve().parent
PAL = {"paper": (0.91, 0.88, 0.81, 1), "accent": (1.0, 0.36, 0.23, 1), "steel": (0.42, 0.47, 0.52, 1),
       "dark": (0.10, 0.13, 0.16, 1), "yellow": (0.95, 0.76, 0.31, 1), "white": (0.96, 0.96, 0.96, 1),
       "blue": (0.62, 0.76, 0.84, 1)}


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def mat(name):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = PAL[name]
    bsdf.inputs["Roughness"].default_value = 0.8
    return m


def box(size, loc, colour, name="part"):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.object
    o.scale = size
    o.name = name
    o.data.materials.append(mat(colour))
    return o


def cyl(r, h, loc, colour, verts=8, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=h, location=loc, rotation=rot)
    o = bpy.context.object
    o.data.materials.append(mat(colour))
    return o


def export(name):
    for o in bpy.context.scene.objects:
        o.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    bpy.ops.export_scene.gltf(filepath=str(OUT / f"{name}.glb"), export_format="GLB", export_yup=True)
    print("wrote", name)


def psv():
    reset()
    box((16, 76, 7), (0, 0, 3.5), "white", "hull")
    box((16.2, 30, 1.2), (0, 0, 1.0), "accent", "boottop")
    box((14, 14, 10), (0, 26, 12), "white", "bridge")
    box((14.5, 3, 2.5), (0, 33.4, 15), "dark", "windows")
    box((14, 44, 0.6), (0, -12, 7.3), "steel", "deck")
    cyl(1.4, 10, (4, 22, 22), "yellow")
    export("psv")


def ferry():
    reset()
    box((20, 90, 8), (0, 0, 4), "white", "hull")
    box((20.4, 90, 1.5), (0, 0, 1.2), "accent", "band")
    box((16, 60, 9), (0, 0, 12.5), "white", "superstructure")
    box((16.5, 58, 2), (0, 0, 14), "blue", "windows")
    cyl(2.2, 8, (0, -8, 21), "accent")
    export("ferry")


def platform():
    reset()
    for x in (-18, 18):
        for y in (-18, 18):
            cyl(2.5, 40, (x, y, 0), "steel")
    box((50, 50, 6), (0, 0, 23), "steel", "cellar_deck")
    box((46, 46, 8), (0, 0, 30), "paper", "modules")
    box((16, 16, 14), (-12, 10, 41), "yellow", "living_quarters")
    cyl(9, 1.2, (-12, 10, 48.6), "accent", verts=12)            # helideck
    cyl(1.5, 45, (14, -12, 56), "steel", verts=6)                # flare/derrick
    box((4, 4, 4), (14, -12, 80), "accent", "flare_tip")
    export("platform")


def wind_turbine():
    reset()
    cyl(3.5, 20, (0, 0, -2), "yellow", verts=10)                 # transition piece
    cyl(2.5, 110, (0, 0, 63), "white", verts=10)                 # tower
    box((5, 14, 5), (0, -2, 120), "white", "nacelle")
    cyl(2.2, 4, (0, 6, 120), "white", verts=10, rot=(1.5708, 0, 0))
    import math
    for k in range(3):
        a = k * 2 * math.pi / 3
        b = box((3, 1, 70), (0, 8, 120), "white", f"blade{k}")
        b.location = (35 * math.sin(a), 8, 120 + 35 * math.cos(a))
        b.rotation_euler = (0, a, 0)
    export("wind_turbine")


if __name__ == "__main__":
    psv(); ferry(); platform(); wind_turbine()
