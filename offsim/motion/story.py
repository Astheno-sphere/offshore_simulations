"""Storyboard -> shots -> one video. Motion graphics from data, with the narration gate built in.

    python -m offsim story offsim/papers/<id>/storyboard.yaml --dry-run   # plan, tool check, refs resolve
    python -m offsim story offsim/papers/<id>/storyboard.yaml             # render shots + assemble

Shot types
  equation  Manim: the model's maths (LaTeX lines written in sequence)          [needs manim + LaTeX]
  map       deck.gl: the validated run on the real coastline; camera keyframes   [needs Node, Chrome]
  card      HyperFrames: KPI count-up card (GSAP), values ONLY from report.json   [needs npx hyperframes]
  section   PIL + numpy: vertical sea section (2D air, JONSWAP sea, line-art vessel) + optional real-layers map;
            deck text chosen from the measured values by `narration:` rules (offsim/motion/section.py)
            `diptych` is accepted as an alias for a section shot that has a map.
  findings  PIL: what the ensemble says (kind fan | paired | state_gantt), only from report["ensemble"] / the run's
            trajectory, spread and status word always on screen (offsim/motion/findings.py)
Assembly    ffmpeg xfade between shots.

Narration: any on-screen sentence in a section / findings shot (and optionally a card title) is a `narration:` list of
{when, text} rules (offsim/motion/narrate.py) evaluated over measured values; never a literal claim.

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


NEEDS = {"equation": ("manim", "latex"), "map": ("node", "chrome"), "card": ("hyperframes", "chrome"),
         "section": ("ffmpeg",), "findings": ("ffmpeg",)}
ALIASES = {"diptych": "section"}
SHOT_TYPES = ("equation", "map", "card", "section", "findings")


def shot_type(shot):
    return ALIASES.get(shot.get("type"), shot.get("type"))


def normalize(shot):
    """Resolve aliases (diptych -> section)."""
    return {**shot, "type": shot_type(shot)} if shot.get("type") in ALIASES else shot


def load_traj(sb):
    """(trajectory, agents) of the storyboard's run, or (None, None)."""
    import pandas as pd
    run = ROOT / sb.get("run", "")
    t, a = run / "trajectory.csv", run / "agents.csv"
    return (pd.read_csv(t) if t.exists() else None), (pd.read_csv(a) if a.exists() else None)


def load_weather(shot):
    import pandas as pd
    return pd.read_csv(ROOT / shot["weather_csv"]) if shot.get("weather_csv") else None


def check(sb, report):
    """Narration gate + refs + tools. Returns a list of problems (empty = go)."""
    probs = []
    failed = [g for g, r in report["gates"].items() if g != "4_paper" and not r["pass"]]
    if failed:
        probs.append(f"run did not pass gates {failed}: no video")
    try:
        from offsim.cinema.camera import shot_plan
        for v in shot_plan(sb, tuple(size(sb.get("format", "square")))):
            probs.append(f"shot_plan: {v}")
    except Exception as e:                       # a follow shot needs its trajectory; reported, not fatal
        probs.append(f"shot_plan could not run: {e}")
    have = tools()
    for i, shot in enumerate(sb["shots"]):
        st = shot_type(shot)
        if st not in SHOT_TYPES:
            probs.append(f"shot {i}: unknown type {shot.get('type')!r}; have {list(SHOT_TYPES)}")
            continue
        miss = [t for t in NEEDS.get(st, ()) if not have[t]]
        if miss:
            probs.append(f"shot {i} ({shot['type']}) needs {miss}")
        if st == "card":
            for kpi in shot.get("kpis", []):
                try:
                    float(resolve(kpi["value"], report))
                except Exception as e:
                    probs.append(f"shot {i} kpi {kpi.get('label')}: {e}")
            if shot.get("narration"):
                from offsim.motion import narrate
                probs += [f"shot {i} (card): {p}" for p in narrate.validate_rules(shot["narration"], set(narrate.flatten(report)))]
        elif st == "section":
            from offsim.motion import section
            sh = normalize(shot)
            probs += [f"shot {i} (section): {p}" for p in section.problems(sh, report)]
            if shot["type"] == "diptych" and not shot.get("map"):
                probs.append(f"shot {i} (diptych): needs a map {{world, run, agent}}")
            m = shot.get("map")
            if isinstance(m, dict) and m.get("run") and (ROOT / m["run"] / "report.json").exists():
                mrep = json.loads((ROOT / m["run"] / "report.json").read_text())
                bad = [g for g, r in mrep.get("gates", {}).items() if g.startswith(("0", "1", "2", "3")) and not r["pass"]]
                if bad:
                    probs.append(f"shot {i} (section): map run {m['run']} did not pass gates {bad}: never map it")
        elif st == "findings":
            from offsim.motion import findings
            traj, _ = load_traj(sb) if shot.get("kind") == "state_gantt" else (None, None)
            probs += [f"shot {i} (findings): {p}" for p in findings.problems(shot, report, traj is not None)]
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


def map_scene(shot, sb, report, path, fmt=None, fps=30):
    """Build (not render) the map shot's scene.json from the gated run: per-frame camera track, display-only vessel
    tracks, terrain (if data/worlds/<world>/depth/<tier> exists) and weather (if a weather block or metocean files exist)."""
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
    fmt = fmt or sb.get("format", "square")
    viewport = tuple(size(fmt))
    seconds = shot.get("seconds", 12)
    t0, t1 = float(traj["t"].min()), float(traj["t"].max())
    from offsim.cinema.camera import camera_track
    track = camera_track(shot["camera"], t0, t1, seconds, fps, viewport, traj=traj) if shot["camera"].get("keys") or shot["camera"].get("follow") else None
    display = None
    if shot.get("vessel_motion", True):
        from offsim.cinema.vessel import display_agents
        display = display_agents(traj, agents, seed=shot.get("seed", 0))
    terrain = None
    tier = shot.get("terrain_tier", "fjord")
    if sc.get("world") not in (None, "none"):
        from offsim.scene import load_terrain
        terrain = load_terrain(ROOT / "data/worlds" / sc["world"] / "depth" / tier)
    weather = None
    if shot.get("weather"):
        from offsim.weather.visual import weather_scene
        w = shot["weather"]
        lon, lat = traj["lon"], traj["lat"]
        bbox = w.get("bbox") or [float(lon.min()) - 0.1, float(lat.min()) - 0.1, float(lon.max()) + 0.1, float(lat.max()) + 0.1]
        ds = {}
        mdir = ROOT / "data/worlds" / sc.get("world", "none") / "metocean"
        if mdir.exists():
            import xarray as xr
            for kind in ("wind", "wave", "current"):
                f = sorted(mdir.glob(f"*{w.get(kind, '')}*.nc")) if w.get(kind) else []
                if f:
                    ds[f"ds_{kind}"] = xr.open_dataset(f[0])
        if ds:
            weather = weather_scene(bbox, t0, t1, land=land, seed=w.get("seed", 0), n_particles=w.get("particles", 2500), **ds)
    scene = build_scene(traj, agents, rep, land=land, sites=sites, accent=tuple(agents["agent_id"]),
                        display=display, terrain=terrain, weather=weather, camera_track=track,
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
    sp = map_scene(shot, sb, report, out.with_suffix(".scene.json"), fmt)
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
    title = shot.get("title", "")
    if shot.get("narration"):                     # the title is chosen from the measured values, never hand-written
        import html as _html

        from offsim.motion import narrate
        title = _html.escape(narrate.choose(shot["narration"], narrate.flatten(report)))
    fields = {"W": W, "H": H, "DURATION": shot.get("seconds", 5), "KICKER": shot.get("kicker", ""), "TITLE": title,
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


def shot_section(shot, sb, report, fmt, out, fps=30):
    from offsim.motion.section import render_section_shot
    return render_section_shot(normalize(shot), sb, out, fps, report, size=tuple(size(fmt)), strict_map=True)


def shot_findings(shot, sb, report, fmt, out, fps=30):
    from offsim.motion.findings import render_findings_shot
    traj, agents = load_traj(sb)
    return render_findings_shot(shot, sb, out, fps, report, traj, load_weather(shot), agents, size=tuple(size(fmt)))


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
                sp = map_scene(shot, sb, report, work / f"{i:02d}_map.scene.json", fmt)
                r = subprocess.run(render_cmd(shot, sp, "draft") + ["--check"], capture_output=True, text=True)
                print(f"  map {i}: renderer check", "OK" if r.returncode == 0 else "FAIL\n" + r.stdout[-600:] + r.stderr[-600:])
                if r.returncode:
                    return 1
            if shot_type(shot) == "section":      # one frame, short spin-up: narration shown is indicative only
                from offsim.motion.section import run_section
                res = run_section({**normalize(shot), "seconds": 0.2}, sb, work / f"{i:02d}_section", 30, report,
                                  tuple(size(fmt)), 0, strict_map=False, spinup_steps=40, log=lambda *_: None)
                print(f"  section {i}: 1 frame OK ({res['frames'][0]}), map {'on' if res['map'] else 'absent'}, "
                      f"indicative deck: {' '.join(res['deck'])}")
            if shot_type(shot) == "findings":
                from offsim.motion.findings import run_findings
                traj, agents = load_traj(sb)
                res = run_findings(shot, report, work / f"{i:02d}_findings", 30, traj, load_weather(shot), agents,
                                   tuple(size(fmt)), -1, log=lambda *_: None)
                print(f"  findings {i}: {shot['kind']} 1 frame OK ({res['frames'][0]}), deck: {' '.join(res['deck'])}")
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
        p = out_dir / f"{i:02d}_{shot_type(shot)}.mp4"
        {"equation": lambda: shot_equation(shot, fmt, p), "map": lambda: shot_map(shot, sb, report, fmt, p),
         "card": lambda: shot_card(shot, sb, report, fmt, p), "section": lambda: shot_section(shot, sb, report, fmt, p),
         "findings": lambda: shot_findings(shot, sb, report, fmt, p)}[shot_type(shot)]()
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
