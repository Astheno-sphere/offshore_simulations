"""Shot 1: the JONSWAP sea is the real hour's sea, the camera is the dolly start."""
import numpy as np

from tools.shot1_helideck import HOOK_HS_M, HOOK_SEED, HOOK_TP_S, build_scene


def test_sea_matches_the_hour(tmp_path):
    res = build_scene(tmp_path / "shot1")
    assert abs(res["sea_hs_m"] - HOOK_HS_M) < 0.01  # spectrum reproduces the hour's Hs
    meta = res["spec"]["meta"]
    assert meta["hour"] == "2011-12-18T01:00" and meta["tp_s"] == HOOK_TP_S
    assert meta["seed"] == HOOK_SEED


def test_scene_has_platform_helicopter_and_sea(tmp_path):
    res = build_scene(tmp_path / "shot1")
    names = [a["name"] for a in res["spec"]["assets"]]
    assert names == ["platform_jacket", "s92", "sea_crest", "sea_trough"]
    assert res["spec"]["sea"]["level_m"] == -3.0  # flat sea below the troughs
    assert res["spec"]["camera"]["lens_mm"] == 40


def test_camera_is_the_dolly_start(tmp_path):
    res = build_scene(tmp_path / "shot1")
    cam = np.array(res["spec"]["camera"]["position"], float)
    look = np.array(res["spec"]["camera"]["look_at"], float)
    assert abs(np.linalg.norm(cam - look) - 38.0) < 0.5  # SHOTBOOK: dolly 38 -> 30 m
    assert res["spec"]["resolution"] == [540, 675]  # 4:5
