"""Storyboard -> shots -> one video. Motion graphics from data, with the narration gate built in.

    python -m offsim story offsim/papers/<id>/storyboard.yaml --dry-run   # plan, tool check, refs resolve
    python -m offsim story offsim/papers/<id>/storyboard.yaml             # render shots + assemble

Shot types
  equation  Manim: the model's maths (LaTeX lines written in sequence)          [needs manim + LaTeX]
  map       deck.gl: the validated run on the real coastline; camera keyframes   [needs Node, Chrome]
  card      HyperFrames: KPI count-up card (GSAP), values ONLY from report.json   [needs npx hyperframes]
Assembly    ffmpeg xfade between shots.

Refs: any card value is a reference like `report:kpis.distance_km` with an optional `fmt`; literal numbers
are refused. The storyboard is refused if the run's gates 0-3 did not pass.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
STYLE = json.loads((ROOT / "offsim/style.json").read_text())


def resolve(ref, report):
    if not (isinstance(ref, str) and ref.startswith("report:")):
        raise ValueError(f"card values must be report refs, got {ref!r}")
    node = report
    for k in ref[len("report:"):].split("."):
        node = node[k]
    return node


def tools():
    return {"manim": shutil.which("manim") is not None, "latex": shutil.which("latex") is not None,
            "node": shutil.which("node") is not None, "ffmpeg": shutil.which("ffmpeg") is not None,
            "chrome": any(Path(p).exists() for p in ("/usr/bin/google-chrome",)) or bool(shutil.which("chromium")),
            "hyperframes": (HERE / "node_modules/.bin/hyperframes").exists()}


NEEDS = {"equation": ("manim", "latex"), "map": ("node", "chrome"), "card": ("hyperframes", "chrome")}


def check(sb, report):
    """Narration gate + refs + tools. Returns a list of problems (empty = go)."""
    probs = []
    failed = [g for g, r in report["gates"].items() if g != "4_paper" and not r["pass"]]
    if failed:
        probs.append(f"run did not pass gates {failed}: no video")
    have = tools()
    for i, shot in enumerate(sb["shots"]):
        miss = [t for t in NEEDS.get(shot["type"], ()) if not have[t]]
        if miss:
            probs.append(f"shot {i} ({shot['type']}) needs {miss}")
        if shot["type"] == "card":
            for kpi in shot.get("kpis", []):
                try:
                    float(resolve(kpi["value"], report))
                except Exception as e:
                    probs.append(f"shot {i} kpi {kpi.get('label')}: {e}")
    return probs


def size(fmt):
    return STYLE["formats"][fmt]


def shot_equation(shot, fmt, out):
    W, H = size(fmt)
    tex = shot["latex"]
    code = ("from manim import *\nconfig.background_color = '#10161B'\nclass Eq(Scene):\n    def construct(self):\n"
            f"        lines = [MathTex(r'''{t}''', color='#E8E1CF') for t in {tex!r}]\n"
            "        g = VGroup(*lines).arrange(DOWN, buff=0.5).scale_to_fit_width(min(12, config.frame_width * 0.8))\n"
            "        for m in g: self.play(Write(m), run_time=1.0)\n"
            f"        self.wait({max(0.5, shot.get('seconds', 5) - len(tex))})\n")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "eq.py"
        src.write_text(code)
        subprocess.run(["manim", "-qh", "--disable_caching", "-r", f"{W},{H}", "--media_dir", tmp, "-o", "eq.mp4", str(src), "Eq"],
                       check=True, capture_output=True)
        shutil.copy(next(Path(tmp).rglob("eq.mp4")), out)


def map_scene(shot, sb, report, path):
    """Build (not render) the map shot's scene.json from the gated run."""
    import geopandas as gpd
    import pandas as pd

    from offsim.contract import validate
    from offsim.scene import build_scene, write

    run = ROOT / sb["run"]
    sc = yaml.safe_load((ROOT / sb["scenario"]).read_text())
    traj, agents = pd.read_csv(run / "trajectory.csv"), pd.read_csv(run / "agents.csv")
    land = None
    if sc.get("world") not in (None, "none"):
        land = gpd.read_file(ROOT / "data/worlds" / sc["world"] / "land.geojson").geometry.union_all()
    rep = validate(traj, agents, land=land)
    inst = sc["instance"]
    sites = [{"pos": [inst["base"]["lon"], inst["base"]["lat"]], "label": inst["base"].get("name", "base"), "height_m": 300}] + \
            [{"pos": [s["lon"], s["lat"]], "label": s["name"], "kind": s.get("kind")} for s in inst["stops"]]
    scene = build_scene(traj, agents, rep, land=land, sites=sites, accent=tuple(agents["agent_id"]),
                        seconds=shot.get("seconds", 12), trail_s=shot.get("trail_s"), land_relief_m=shot.get("land_relief_m", 60),
                        camera=shot["camera"], overlay={**shot.get("overlay", {}), "kicker": sc["story"]["question"]},
                        kpi_track=[[k["label"], [[0, (k.get("fmt") or "{}").format(resolve(k["value"], report))]]] for k in shot.get("kpis", [])])
    write(scene, path)
    return path


def render_cmd(shot, scene_path, fmt):
    cmd = ["python3", str(ROOT / "offsim/render_deck/render.py"), "--scene", str(scene_path), "--format", fmt]
    if shot.get("agents"):
        cmd += ["--agents", shot["agents"]]
    if shot.get("sites"):
        cmd += ["--sites", shot["sites"]]
    return cmd


def shot_map(shot, sb, report, fmt, out):
    sp = map_scene(shot, sb, report, out.with_suffix(".scene.json"))
    subprocess.run(render_cmd(shot, sp, fmt) + ["--out", str(out), "--seconds", str(shot.get("seconds", 12))], check=True)


def card_project(shot, report, fmt, folder):
    """Write (not render) the HyperFrames card project into folder."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    W, H = size(fmt)
    html = (HERE / "templates" / shot.get("template", "kpi_card") / "index.html").read_text()
    kpi_html = "".join(
        f'<div class="kpi"><b data-value="{float(resolve(k["value"], report)) * k.get("scale", 1)}" data-decimals="{k.get("decimals", 0)}" '
        f'data-unit="{k.get("unit", "")}"></b><span>{k["label"]}</span></div>' for k in shot["kpis"])
    fields = {"W": W, "H": H, "DURATION": shot.get("seconds", 5), "KICKER": shot.get("kicker", ""), "TITLE": shot.get("title", ""),
              "KPI_HTML": kpi_html, "STATUS": report["status"], "SOURCE": shot.get("source", ""), "MARK": shot.get("mark", "OFFSHORE SIMULATIONS")}
    for k, val in fields.items():
        html = html.replace("{{" + k + "}}", str(val))
    (folder / "index.html").write_text(html)
    shutil.copy(HERE / "node_modules/gsap/dist/gsap.min.js", folder)
    (folder / "meta.json").write_text(json.dumps({"id": "card", "name": "card"}))
    return folder


def hyperframes(args, cwd):
    env = {**os.environ, "HYPERFRAMES_BROWSER_PATH": os.environ.get("HYPERFRAMES_BROWSER_PATH", "/usr/bin/google-chrome")}
    return subprocess.run([str(HERE / "node_modules/.bin/hyperframes"), *args], cwd=cwd, env=env, capture_output=True, text=True)


def shot_card(shot, sb, report, fmt, out):
    with tempfile.TemporaryDirectory() as tmp:
        card_project(shot, report, fmt, tmp)
        r = hyperframes(["render", "-q", "standard", "-o", str(out)], tmp)
        if r.returncode:
            raise RuntimeError(r.stdout[-800:] + r.stderr[-800:])


def assemble(parts, out, xfade=0.5):
    """ffmpeg xfade chain; durations probed from the files."""
    def dur(p):
        return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                                    capture_output=True, text=True, check=True).stdout)
    if len(parts) == 1:
        shutil.copy(parts[0], out)
        return
    inputs = sum((["-i", str(p)] for p in parts), [])
    f, last, offset = [], "[0:v]", 0.0
    for i in range(1, len(parts)):
        offset += dur(parts[i - 1]) - xfade
        tag = f"[v{i}]"
        f.append(f"{last}[{i}:v]xfade=transition=fade:duration={xfade}:offset={offset:.3f}{tag}")
        last = tag
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(f), "-map", last,
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)], check=True)


def build(storyboard, dry_run=False):
    sb = yaml.safe_load(Path(storyboard).read_text())
    report = json.loads((ROOT / sb["run"] / "report.json").read_text())
    fmt = sb.get("format", "square")
    probs = check(sb, report)
    print(f"storyboard {sb['id']}: {len(sb['shots'])} shots, format {fmt}, run status: {report['status']}")
    for i, s in enumerate(sb["shots"]):
        print(f"  {i}: {s['type']:8s} {s.get('seconds', '?')} s  {s.get('title') or s.get('agents') or ''}")
    print("tools:", {k: v for k, v in tools().items()})
    if probs:
        print("REFUSED:\n  " + "\n  ".join(probs))
        return 1
    if dry_run:
        # build every shot's source without rendering: scene.json (+ headless check) and card project (+ lint)
        work = ROOT / sb["run"] / "shots"
        for i, shot in enumerate(sb["shots"]):
            if shot["type"] == "map":
                sp = map_scene(shot, sb, report, work / f"{i:02d}_map.scene.json")
                r = subprocess.run(render_cmd(shot, sp, "draft") + ["--check"], capture_output=True, text=True)
                print(f"  map {i}: renderer check", "OK" if r.returncode == 0 else "FAIL\n" + r.stdout[-600:] + r.stderr[-600:])
                if r.returncode:
                    return 1
            if shot["type"] == "card":
                d = card_project(shot, report, fmt, work / f"{i:02d}_card")
                r = hyperframes(["lint"], d)
                ok = r.returncode == 0 and ("0 error(s)" in r.stdout or "0 errors" in r.stdout)
                print(f"  card {i}: hyperframes lint", "OK" if ok else "FAIL\n" + r.stdout[-600:])
                if not ok:
                    return 1
        print("dry run OK: refs resolve, gates pass, tools present, shots build and check (nothing rendered)")
        return 0
    out_dir = ROOT / sb["run"] / "shots"
    out_dir.mkdir(parents=True, exist_ok=True)
    parts = []
    for i, shot in enumerate(sb["shots"]):
        p = out_dir / f"{i:02d}_{shot['type']}.mp4"
        {"equation": lambda: shot_equation(shot, fmt, p), "map": lambda: shot_map(shot, sb, report, fmt, p),
         "card": lambda: shot_card(shot, sb, report, fmt, p)}[shot["type"]]()
        parts.append(p)
    final = ROOT / sb["run"] / f"{sb['id']}_{fmt}.mp4"
    assemble(parts, final, sb.get("transition_s", 0.5))
    if sb.get("grade"):                       # one grade per film, applied once (offsim/cinema/look.py)
        from offsim.cinema.look import grade
        graded = final.with_name(final.stem + "_graded.mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(final), "-vf", grade(sb["grade"]),
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
                        "-movflags", "+faststart", str(graded)], check=True)
        graded.replace(final)
    print("wrote", final.relative_to(ROOT))
    return 0
