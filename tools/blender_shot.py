"""Render one still with Blender (bpy) in its own process.   python tools/blender_shot.py <scene.json> <out.png>

GPL boundary: this is the only file that imports bpy; offsim never does. Schema: docs/BLENDER.md.
Flat (toon) look: emission shader whose colour steps by the angle to the key/rim lights, plus Freestyle ink lines.
Cycles CPU, denoiser off, fixed seed: same scene.json gives the same PNG on the same bpy build.
Frame: Z up, metres; asset heading is degrees about +Z from +x (the CAD frame of offsim.assets.cad).
"""
import json
import math
import sys
import time
from pathlib import Path

DEFAULT_PALETTE = {"sea": "#1d3b4f", "sky_top": "#2b4a63", "sky_bottom": "#c9b79c", "hull": "#c8c3b8",
                   "accent": "#d9822b", "steel": "#6b7178", "deck": "#8a8f93", "ink": "#101214"}


def srgb_to_lin(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]


def kelvin_rgb(k):  # Tanner Helland approximation, returned linear
    t = k / 100.0
    r = 255 if t <= 66 else 329.698727446 * (t - 60) ** -0.1332047592
    g = 99.4708025861 * math.log(t) - 161.1195681661 if t <= 66 else 288.1221695283 * (t - 60) ** -0.0755148492
    b = 255 if t >= 66 else (0 if t <= 19 else 138.5177312231 * math.log(t - 10) - 305.0447927307)
    c = [max(0, min(255, v)) / 255.0 for v in (r, g, b)]
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]


def main(scene_json, out_png):
    import bpy
    from mathutils import Vector

    spec = json.loads(Path(scene_json).read_text())
    pal = dict(DEFAULT_PALETTE, **spec.get("palette", {}))

    def col(tok):
        return srgb_to_lin(pal.get(tok, tok))

    t0 = time.time()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    res = spec.get("resolution", [960, 540])
    samples = int(spec.get("samples", 16))
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = False
    sc.cycles.seed = int(spec.get("seed", 0))
    sc.cycles.use_animated_seed = False
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = res[0], res[1], 100
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = str(out_png)

    lights = spec.get("lights", {})
    key = lights.get("key", {"dir": [-0.5, -0.6, 0.65], "kelvin": 5600})
    fill = lights.get("fill", {"dir": [0.6, 0.3, 0.3], "kelvin": 7500})
    rim = lights.get("rim", {"dir": [0.3, 0.9, 0.35], "kelvin": 4200})

    def unit(v):
        return Vector(v).normalized()

    kd, rd = unit(key["dir"]), unit(rim["dir"])
    kt, ft, rt = kelvin_rgb(key.get("kelvin", 5600)), kelvin_rgb(fill.get("kelvin", 7500)), kelvin_rgb(rim.get("kelvin", 4200))
    for nm, L, tint in (("key", key, kt), ("fill", fill, ft), ("rim", rim, rt)):
        ld = bpy.data.lights.new(nm, "SUN")
        ld.color = tint
        ld.energy = float(L.get("strength", 3.0))
        ob = bpy.data.objects.new(nm, ld)
        sc.collection.objects.link(ob)
        ob.rotation_euler = (-Vector(L["dir"])).to_track_quat("-Z", "Y").to_euler()  # "dir" points TO the light; a sun shines along its -Z

    # ---- sky: vertical gradient, no HDRI
    w = bpy.data.worlds.new("sky")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    tc, sep, mp, ramp, bg, outn = (nt.nodes.new(t) for t in (
        "ShaderNodeTexCoord", "ShaderNodeSeparateXYZ", "ShaderNodeMapRange", "ShaderNodeValToRGB", "ShaderNodeBackground", "ShaderNodeOutputWorld"))
    sky = spec.get("sky", {})
    mp.inputs["From Min"].default_value, mp.inputs["From Max"].default_value = -0.02, 0.3
    mp.clamp = True
    ramp.color_ramp.elements[0].color = (*col(sky.get("bottom", "sky_bottom")), 1)
    ramp.color_ramp.elements[1].color = (*col(sky.get("top", "sky_top")), 1)
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], mp.inputs["Value"])
    nt.links.new(mp.outputs["Result"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], outn.inputs["Surface"])

    # ---- toon material: emission whose colour steps with N.key (3 bands) and lifts on N.rim
    cache = {}

    def height_banded(token, hr):
        """Sea look for a displaced patch: flat bands by surface height (trough darker, crest lighter), emission only.
        Slopes of real waves are too gentle for the normal-banded toon shader to show them."""
        c = col(token)
        m = bpy.data.materials.new("sea_h")
        m.use_nodes = True
        n = m.node_tree
        n.nodes.clear()
        geo, sep = n.nodes.new("ShaderNodeNewGeometry"), n.nodes.new("ShaderNodeSeparateXYZ")
        mr, ramp = n.nodes.new("ShaderNodeMapRange"), n.nodes.new("ShaderNodeValToRGB")
        em, out = n.nodes.new("ShaderNodeEmission"), n.nodes.new("ShaderNodeOutputMaterial")
        mr.inputs["From Min"].default_value, mr.inputs["From Max"].default_value = -hr, hr
        ramp.color_ramp.interpolation = "CONSTANT"
        steps = [(0.0, 0.55), (0.30, 0.78), (0.52, 1.0), (0.72, 1.28), (0.9, 1.6)]
        e = ramp.color_ramp.elements
        while len(e) < len(steps):
            e.new(0.5)
        for el, (pos, k) in zip(sorted(e, key=lambda x: x.position), steps):
            el.position = pos
        for el, (pos, k) in zip(sorted(e, key=lambda x: x.position), steps):
            el.color = (min(c[0] * k, 1), min(c[1] * k, 1), min(c[2] * k, 1), 1)
        n.links.new(geo.outputs["Position"], sep.inputs[0])
        n.links.new(sep.outputs["Z"], mr.inputs["Value"])
        n.links.new(mr.outputs["Result"], ramp.inputs["Fac"])
        n.links.new(ramp.outputs["Color"], em.inputs["Color"])
        n.links.new(em.outputs["Emission"], out.inputs["Surface"])
        return m

    def toon(token):
        if token in cache:
            return cache[token]
        c = col(token)
        m = bpy.data.materials.new("toon_" + token)
        m.use_nodes = True
        n = m.node_tree
        n.nodes.clear()
        geo, d1, d2 = n.nodes.new("ShaderNodeNewGeometry"), n.nodes.new("ShaderNodeVectorMath"), n.nodes.new("ShaderNodeVectorMath")
        d1.operation = d2.operation = "DOT_PRODUCT"
        d1.inputs[1].default_value, d2.inputs[1].default_value = tuple(kd), tuple(rd)
        r1, r2 = n.nodes.new("ShaderNodeValToRGB"), n.nodes.new("ShaderNodeValToRGB")
        mix, em, out = n.nodes.new("ShaderNodeMix"), n.nodes.new("ShaderNodeEmission"), n.nodes.new("ShaderNodeOutputMaterial")
        mix.data_type, mix.blend_type = "RGBA", "ADD"
        r1.color_ramp.interpolation = "CONSTANT"
        e = r1.color_ramp.elements
        e[0].position, e[1].position = 0.0, 0.62  # dot -1..1 remapped below to 0..1
        e.new(0.5)
        shade = [[c[i] * ft[i] * 0.45 for i in range(3)], [c[i] * 0.78 for i in range(3)], [c[i] * kt[i] for i in range(3)]]
        # elements sorted by position: 0.0 shadow, 0.5 mid, 0.62 lit
        for el, s in zip(sorted(e, key=lambda x: x.position), shade):
            el.color = (*s, 1)
        r2.color_ramp.interpolation = "CONSTANT"
        r2.color_ramp.elements[0].position, r2.color_ramp.elements[1].position = 0.0, 0.8
        r2.color_ramp.elements[0].color = (0, 0, 0, 1)
        r2.color_ramp.elements[1].color = (*[0.35 * rt[i] * (0.4 + c[i]) for i in range(3)], 1)
        for dn, rn in ((d1, r1), (d2, r2)):
            mr = n.nodes.new("ShaderNodeMapRange")
            mr.inputs["From Min"].default_value, mr.inputs["From Max"].default_value = -1.0, 1.0
            n.links.new(geo.outputs["Normal"], dn.inputs[0])
            n.links.new(dn.outputs["Value"], mr.inputs["Value"])
            n.links.new(mr.outputs["Result"], rn.inputs["Fac"])
        mix.inputs["Factor"].default_value = 1.0
        n.links.new(r1.outputs["Color"], mix.inputs["A"])
        n.links.new(r2.outputs["Color"], mix.inputs["B"])
        n.links.new(mix.outputs["Result"], em.inputs["Color"])
        n.links.new(em.outputs["Emission"], out.inputs["Surface"])
        cache[token] = m
        return m

    def paint(objs, colours):
        for o in objs:
            if o.type != "MESH":
                continue
            tok = colours.get("default", "hull")
            for k, v in colours.items():
                if k != "default" and k in o.name:
                    tok = v
            o.data.materials.clear()
            o.data.materials.append(toon(tok))

    # ---- assets
    checks = []
    for a in spec.get("assets", []):
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=a["glb"])
        new = [o for o in bpy.data.objects if o not in before]
        meshes = [o for o in new if o.type == "MESH"]
        bpy.context.view_layer.update()
        pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
        lo = Vector(min(p[i] for p in pts) for i in range(3))
        hi = Vector(max(p[i] for p in pts) for i in range(3))
        size = [round(hi[i] - lo[i], 3) for i in range(3)]
        chk = {"asset": a.get("name", Path(a["glb"]).stem), "size_m": size}
        if "expect_size_m" in a:
            chk["expect_size_m"] = a["expect_size_m"]
            chk["max_rel_err"] = round(max(abs(size[i] - a["expect_size_m"][i]) / a["expect_size_m"][i] for i in range(3)), 5)
        checks.append(chk)
        root = bpy.data.objects.new("root_" + chk["asset"], None)
        sc.collection.objects.link(root)
        for o in new:
            if o.parent is None:
                o.parent = root
        s = float(a.get("scale", 1.0))
        root.scale = (s, s, s)
        root.rotation_euler = (0, 0, math.radians(a.get("heading_deg", 0.0)))
        root.location = a.get("position", (0, 0, 0))
        paint(meshes, a.get("colours", {"default": "hull"}))

    # ---- sea
    sea = spec.get("sea")
    sea_col = bpy.data.collections.new("sea")  # kept out of Freestyle: ink on a km-wide plane costs GBs and gains nothing
    sc.collection.children.link(sea_col)
    if sea is not None:
        size = float(sea.get("size_m", 4000.0))
        z = float(sea.get("level_m", 0.0))
        # far plane always; a displaced patch (jonswap grid) sits on top near the platform when a grid is given
        me = bpy.data.meshes.new("sea")
        h2 = size / 2
        me.from_pydata([(-h2, -h2, z), (h2, -h2, z), (h2, h2, z), (-h2, h2, z)], [], [(0, 1, 2, 3)])
        ob = bpy.data.objects.new("sea", me)
        sea_col.objects.link(ob)
        ob.data.materials.append(toon(sea.get("colour", "sea")))
        npy = sea.get("displacement_npy")
        if npy and Path(npy).exists():
            import numpy as np
            h = np.load(npy)
            n = h.shape[0]
            psize = float(sea.get("patch_m", 500.0))
            xs = np.linspace(-psize / 2, psize / 2, n)
            verts = [(xs[i], xs[j], z + float(h[j, i])) for j in range(n) for i in range(n)]
            faces = [(j * n + i, j * n + i + 1, (j + 1) * n + i + 1, (j + 1) * n + i) for j in range(n - 1) for i in range(n - 1)]
            pm = bpy.data.meshes.new("sea_patch")
            pm.from_pydata(verts, [], faces)
            pm.update()
            po = bpy.data.objects.new("sea_patch", pm)
            sea_col.objects.link(po)
            po.data.materials.append(height_banded(sea.get("colour", "sea"), float(sea.get("height_range_m", 2.0))))
            for poly in pm.polygons:
                poly.use_smooth = True

    # ---- camera (static)
    cam = spec["camera"]
    cd = bpy.data.cameras.new("cam")
    cd.lens = float(cam.get("lens_mm", 50))
    cd.sensor_width = float(cam.get("sensor_mm", 36))
    cd.clip_start, cd.clip_end = float(cam.get("clip_start_m", 0.1)), float(cam.get("clip_end_m", 20000.0))  # map shots 50-220 km out need clip_end_m
    co = bpy.data.objects.new("cam", cd)
    sc.collection.objects.link(co)
    co.location = cam["position"]
    look = Vector(cam["look_at"])
    co.rotation_euler = (look - co.location).to_track_quat("-Z", "Y").to_euler()
    if cam.get("dof_fstop"):
        cd.dof.use_dof = True
        cd.dof.aperture_fstop = float(cam["dof_fstop"])
        cd.dof.focus_distance = (look - co.location).length
    sc.camera = co

    # ---- Freestyle ink
    shading = spec.get("shading", {})
    if shading.get("mode", "flat") != "flat":
        raise SystemExit("only shading.mode == 'flat' is implemented")
    line_px = float(shading.get("line_px", 1.5))
    if line_px > 0:
        sc.render.use_freestyle = True
        sc.render.line_thickness_mode = "ABSOLUTE"
        sc.render.line_thickness = line_px
        vl = bpy.context.view_layer
        vl.use_freestyle = True
        fs = vl.freestyle_settings
        fs.crease_angle = math.radians(float(shading.get("crease_deg", 120)))
        ls = fs.linesets[0] if len(fs.linesets) else fs.linesets.new("ink")
        ls.select_silhouette = ls.select_border = ls.select_crease = True
        ls.select_by_visibility = True
        ls.select_by_image_border = False
        ls.select_by_collection, ls.collection, ls.collection_negation = True, sea_col, "EXCLUSIVE"
        st = ls.linestyle or bpy.data.linestyles.new("ink")
        ls.linestyle = st
        st.color = col("ink")
        st.thickness = line_px
        st.thickness_position = "CENTER"

    bpy.ops.render.render(write_still=True)
    rep = {"resolution": res, "samples": samples, "seed": sc.cycles.seed, "bbox_check": checks, "seconds": round(time.time() - t0, 2)}
    Path(out_png).with_suffix(".report.json").write_text(json.dumps(rep, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
