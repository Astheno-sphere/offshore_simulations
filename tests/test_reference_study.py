"""tools/reference_study.py measures a film's grammar. The clip here is synthetic (ffmpeg lavfi): a moving scene on
the top 70 % of the frame, a static caption ground below, dimmed for seconds 2 to 4."""
import json
import shutil
import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="needs ffmpeg")
sys.path.insert(0, "tools")


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    p = tmp_path_factory.mktemp("ref") / "clip.mp4"
    vf = ("[0:v]eq=brightness=-0.35:enable='between(t,2,4)'[s];[s][1:v]vstack")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=200x140:r=10:d=6", "-f", "lavfi", "-i",
                    "color=c=0x321b23:s=200x60:r=10:d=6", "-filter_complex", vf, "-pix_fmt", "yuv420p", str(p)], check=True)
    return p


def test_measures_scene_share_acts_and_cuts(clip):
    import reference_study as rs
    m = rs.measure(clip)
    assert m["width"] == 200 and m["height"] == 200 and abs(m["duration_s"] - 6.0) < 0.2
    assert m["panels"] == 1
    assert abs(m["scene_share"] - 0.70) < 0.05, m["scene_share"]
    assert abs(m["scene_share"] + m["static_share"] - 1.0) < 1e-6
    assert [a["name"] for a in m["acts"]] == ["before", "event", "after"]
    assert m["acts"][1]["s"][0] in (2, 3) and m["acts"][1]["s"][1] in (4, 5)
    assert len(m["palette"]) == 6 and abs(sum(c["share"] for c in m["palette"]) - 1.0) < 0.01


def test_refuses_an_output_dir_outside_out(clip, tmp_path, capsys):
    import reference_study as rs
    assert rs.main([str(clip), "--out", str(tmp_path / "elsewhere")]) == 2
    assert "never committed" in capsys.readouterr().err
    assert rs.main(["missing.mp4", "--out", "out/reference/x"]) == 2


def test_cli_writes_measure_and_sheets(clip, tmp_path):
    import reference_study as rs
    out = tmp_path / "out" / "reference" / "t"
    assert rs.main([str(clip), "--out", str(out)]) == 0
    assert json.loads((out / "measure.json").read_text())["panels"] == 1
    assert (out / "sheet.jpg").stat().st_size > 0 and (out / "motion.jpg").stat().st_size > 0
