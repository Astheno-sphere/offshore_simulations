"""Render a scene to MP4: headless Chrome (software WebGL, no GPU needed) + deck.gl + ffmpeg.

    python offsim/render_deck/render.py --scene out/scene.json --out out/video.mp4 --format square --seconds 30

Frames are drawn one at a time at exact simulation times (no wall-clock animation), so a render is
reproducible. Draft at `--format draft` here; final 1080p renders run in .github/workflows/render.yml.
"""
import argparse
import asyncio
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
STYLE = json.loads((HERE.parent / "style.json").read_text())


def build():
    """npm install + esbuild bundle, once."""
    if not (HERE / "node_modules").exists():
        subprocess.run(["npm", "ci" if (HERE / "package-lock.json").exists() else "install", "--no-audit", "--no-fund"],
                       cwd=HERE, check=True)
    subprocess.run(["npx", "esbuild", "src/app.js", "--bundle", "--minify", "--outfile=bundle.js", "--log-level=warning"],
                   cwd=HERE, check=True)


def inline_assets(style):
    """Sprites (mirrored E/W) and glTF models as data URLs, so the page needs no file or network access."""
    import base64
    import io

    from PIL import Image, ImageOps

    assets = HERE.parent / "assets"
    sprites = {}
    for key in sorted(set(style.get("sprites", {}).values())):
        img = Image.open(assets / "sprites" / f"{key}.png").convert("RGBA")
        for side, im in (("W", img), ("E", ImageOps.mirror(img))):
            buf = io.BytesIO()
            im.save(buf, "PNG")
            sprites[f"{key}_{side}"] = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    models = {kind: "data:model/gltf-binary;base64," + base64.b64encode((assets / "models" / f"{f}.glb").read_bytes()).decode()
              for kind, f in style.get("models", {}).items() if (assets / "models" / f"{f}.glb").exists()}
    return {"sprites": sprites, "models": models}


def chrome():
    for c in (os.environ.get("CHROME"), "/usr/bin/google-chrome", shutil.which("google-chrome"), shutil.which("chromium")):
        if c and Path(c).exists():
            return c
    return None  # fall back to Playwright's bundled Chromium


async def capture(scene, frames_dir, fps, seconds, still=False):
    from playwright.async_api import async_playwright

    t0, t1 = scene["t0"], scene["t1"]
    if still:  # one frame: at scene['still_t'] or the end
        t0 = t1 = scene.get("still_t", t1)
    n = int(fps * seconds)
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=chrome(),
                                    args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
        pg = await b.new_page(viewport={"width": scene["width"], "height": scene["height"]})
        errors = []
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errors.append(str(e)))
        await pg.add_init_script(f"window.SCENE = {json.dumps(scene)};")
        await pg.goto((HERE / "index.html").as_uri())
        await pg.wait_for_function("window.ready === true", timeout=60_000)
        # warm-up: sprites and glTF models load asynchronously after the first draw
        for _ in range(3):
            await pg.evaluate(f"window.draw({t0})")
            await pg.wait_for_timeout(700)
        for f in range(n):
            await pg.evaluate(f"window.draw({t0 + (t1 - t0) * f / max(n - 1, 1)})")
            await pg.screenshot(path=str(frames_dir / f"{f:05d}.png"))
        await b.close()
    if errors:
        raise RuntimeError("renderer errors:\n" + "\n".join(errors[:10]))
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--format", default="draft", choices=list(STYLE["formats"]))
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--seconds", type=float, default=None, help="video length; default scene['seconds']")
    ap.add_argument("--still", action="store_true", help="write only the last frame as PNG")
    ap.add_argument("--at", type=float, default=None, help="with --still: simulation time to draw (default: end)")
    ap.add_argument("--agents", choices=["sprite", "model", "dot"], help="override style agent_mode")
    a = ap.parse_args()
    scene = json.loads(Path(a.scene).read_text())
    scene["width"], scene["height"] = STYLE["formats"][a.format]
    scene["style"] = {**STYLE, **scene.get("style", {})}
    if a.agents:
        scene["style"]["agent_mode"] = a.agents
    scene["assets"] = inline_assets(scene["style"])
    seconds = a.seconds or scene.get("seconds", 20)
    build()
    with tempfile.TemporaryDirectory() as tmp:
        fdir = Path(tmp)
        if a.still:
            scene["still_t"] = a.at if a.at is not None else scene["t1"]
            scene["trail_s"] = scene["still_t"] - scene["t0"] if a.at is None else scene["trail_s"]
        n = asyncio.run(capture(scene, fdir, 1 if a.still else a.fps, 1 if a.still else seconds, still=a.still))
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        if a.still:
            shutil.copy(fdir / f"{n - 1:05d}.png", a.out)
        else:
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(a.fps), "-i", str(fdir / "%05d.png"),
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                            "-movflags", "+faststart", a.out], check=True)
    print(f"wrote {a.out} ({n} frames, {scene['width']}x{scene['height']})")


if __name__ == "__main__":
    main()
