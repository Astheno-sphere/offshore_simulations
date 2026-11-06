"""Weather: particles (seeded, RK4, fixed respawn), Hs texture, scene block, PSV effect, subsetting (synthetic fields).

No network: fetch.subset is exercised on synthetic curvilinear xarray datasets shaped like the MET Norway ones
(names from metocean-api 1.1.14), through fetch._open."""
import base64
import io
import json
import math
import sys

import numpy as np
import pytest
xr = pytest.importorskip("xarray")  # weather extras (requirements-weather.txt); CI installs them
from PIL import Image
from shapely.geometry import box

from offsim.weather import effects, fetch, visual
from offsim.weather.visual import DEG, R_EARTH, Field

BBOX = (10.0, 59.2, 10.6, 59.8)


def grid(nt=4, step=3600.0, n=31, bbox=BBOX):
    lon = np.linspace(bbox[0], bbox[2], n)
    lat = np.linspace(bbox[1], bbox[3], n)
    return np.arange(nt) * step, lat, lon


def dataset(fn, names=("u10", "v10"), nt=4, n=31, bbox=BBOX):
    t, lat, lon = grid(nt, n=n, bbox=bbox)
    LL, LA = np.meshgrid(lon, lat)
    a, b = fn(LL, LA)
    shape = (nt, n, n)
    return xr.Dataset({names[0]: (("time", "lat", "lon"), np.broadcast_to(a, shape).copy()),
                       names[1]: (("time", "lat", "lon"), np.broadcast_to(b, shape).copy())},
                      coords={"time": t, "lat": lat, "lon": lon})


def uniform(u, v, **kw):
    return dataset(lambda x, y: (np.full_like(x, u), np.full_like(x, v)), **kw)


def hs_bump(nt=4, amp=4.0):
    t, lat, lon = grid(nt)
    LL, LA = np.meshgrid(lon, lat)
    z = amp * np.exp(-(((LL - 10.3) / 0.1) ** 2 + ((LA - 59.5) / 0.1) ** 2))
    return xr.Dataset({"hs": (("time", "lat", "lon"), np.repeat(z[None], nt, 0))}, coords={"time": t, "lat": lat, "lon": lon})


def scene(**kw):
    args = dict(bbox=BBOX, t0=0, t1=3600, seed=3, n_particles=300, ds_wind=uniform(5, 2), ds_wave=hs_bump(), ds_current=uniform(0.3, 0.1, names=("u", "v")))
    args.update(kw)
    return visual.weather_scene(**args)


# ---------------------------------------------------------------- seeds / determinism

LAND = box(10.2, 59.3, 10.4, 59.7)


def test_seeds_deterministic_in_box_and_off_land():
    a = visual.seed_particles(BBOX, 500, seed=7, land=LAND)
    b = visual.seed_particles(BBOX, 500, seed=7, land=LAND)
    assert a.shape == (500, 2) and np.array_equal(a, b)
    assert not np.array_equal(a, visual.seed_particles(BBOX, 500, seed=8, land=LAND))
    assert (a[:, 0] >= BBOX[0]).all() and (a[:, 0] <= BBOX[2]).all() and (a[:, 1] >= BBOX[1]).all() and (a[:, 1] <= BBOX[3]).all()
    assert not any(LAND.contains(__import__("shapely").geometry.Point(x, y)) for x, y in a)


def test_deck_style_land_polygons_accepted():
    ring = [list(c) for c in LAND.exterior.coords]
    assert not visual._land_geom([ring, [ring]]) is None
    pts = visual.seed_particles(BBOX, 100, 1, land=[ring])
    assert not any(LAND.contains(__import__("shapely").geometry.Point(x, y)) for x, y in pts)


def test_no_particle_starts_on_land_in_scene():
    sc = scene(land=LAND)
    assert sc["particles"]["trips"]
    import shapely
    first = np.array([d["path"][0] for d in sc["particles"]["trips"]])
    assert not shapely.contains_xy(LAND, first[:, 0], first[:, 1]).any()


def test_same_seed_byte_identical_json_and_seed_changes_it():
    a = json.dumps(scene(land=LAND), sort_keys=True)
    b = json.dumps(scene(land=LAND), sort_keys=True)
    assert a == b
    assert a != json.dumps(scene(land=LAND, seed=4), sort_keys=True)


# ---------------------------------------------------------------- RK4

def test_rk4_uniform_flow_is_exact():
    u, v, T = 3.0, -1.5, 1800.0
    ds = uniform(u, v, nt=2)
    seeds = np.array([[10.3, 59.5], [10.1, 59.3]])
    trips = visual.integrate_streamlines(ds, seeds, 0, T, dt_s=60, life_s=T, speedup=2.0, stagger=1, decimals=10)
    assert len(trips) == 2
    for tr, (lon0, lat0) in zip(sorted(trips, key=lambda d: d["i"]), seeds):
        lon, lat = tr["path"][-1]
        dx = (lon - lon0) / DEG * R_EARTH * math.cos(math.radians(lat0))
        dy = (lat - lat0) / DEG * R_EARTH
        assert dx == pytest.approx(u * 2 * T, abs=1e-3) and dy == pytest.approx(v * 2 * T, abs=1e-3)
        assert tr["speed"][0] == pytest.approx(math.hypot(u, v), abs=1e-3)      # speed stays physical
        assert tr["timestamps"][-1] == T


def test_rk4_vortex_stays_on_circle():
    lat_c, lon_c, omega = 59.5, 10.3, 2e-4        # period 2*pi/omega ~ 8.7 h; radius 8 km -> 1.6 m/s
    ck = math.cos(math.radians(lat_c))

    def vortex(LL, LA):
        x = (LL - lon_c) / DEG * R_EARTH * ck
        y = (LA - lat_c) / DEG * R_EARTH
        return -omega * y, omega * x

    ds = dataset(vortex, nt=2, n=61)
    r = 8000.0
    seed = np.array([[lon_c + r / (R_EARTH * ck) * DEG, lat_c]])
    T = 2 * math.pi / omega
    tr = visual.integrate_streamlines(ds, seed, 0, T, dt_s=60, life_s=T, stagger=1, out_dt_s=600, decimals=9)[0]
    xs = np.array([[(lon - lon_c) / DEG * R_EARTH * ck, (lat - lat_c) / DEG * R_EARTH] for lon, lat in tr["path"]])
    rad = np.hypot(xs[:, 0], xs[:, 1])
    assert np.abs(rad - r).max() < 0.01 * r          # 1 % (local-frame cos(lat) drift)
    ang = np.unwrap(np.arctan2(xs[:, 1], xs[:, 0]))
    assert ang[-1] - ang[0] == pytest.approx(2 * math.pi, rel=0.02)     # counter-clockwise, one turn


def test_field_time_interpolation_and_outside_is_calm():
    t, lat, lon = grid(2)
    ds = xr.Dataset({"u10": (("time", "lat", "lon"), np.stack([np.zeros((31, 31)), np.full((31, 31), 4.0)])),
                     "v10": (("time", "lat", "lon"), np.zeros((2, 31, 31)))}, coords={"time": t, "lat": lat, "lon": lon})
    f = Field.from_ds(ds)
    u, v = f.sample(1800.0, np.array([10.3, 9.0]), np.array([59.5, 59.5]))
    assert u[0] == pytest.approx(2.0) and u[1] == 0.0
    assert f.sample(99999.0, np.array([10.3]), np.array([59.5]))[0][0] == pytest.approx(4.0)   # clamped in time


# ---------------------------------------------------------------- respawn

def test_respawn_schedule_is_fixed_and_deterministic():
    ds = uniform(1.0, 0.5, nt=2)
    seeds = visual.seed_particles(BBOX, 40, 1)
    kw = dict(dt_s=60, life_s=900.0, stagger=5, out_dt_s=60)
    a = visual.integrate_streamlines(ds, seeds, 0, 3600, **kw)
    assert a == visual.integrate_streamlines(ds, seeds, 0, 3600, **kw)
    by_i = {}
    for tr in a:
        by_i.setdefault(tr["i"], []).append(tr)
    for i, trs in by_i.items():
        births = [tr["timestamps"][0] for tr in sorted(trs, key=lambda d: d["timestamps"][0])]
        assert births[0] == pytest.approx((i % 5) * 900.0 / 5)                 # t0 + (i mod K) * life / K
        assert np.allclose(np.diff(births), 900.0)                              # reborn every life_s
        for tr in trs:
            assert tr["path"][0] == [round(float(seeds[i][0]), 6), round(float(seeds[i][1]), 6)]   # at its seed
            assert tr["timestamps"][-1] <= 3600


def test_prewarm_fills_the_screen_from_t0():
    ds = uniform(1.0, 0.0, nt=2)
    seeds = visual.seed_particles(BBOX, 20, 1)
    cold = visual.integrate_streamlines(ds, seeds, 0, 900, life_s=900, stagger=5)
    warm = visual.integrate_streamlines(ds, seeds, 0, 900, life_s=900, stagger=5, prewarm=True)
    alive = lambda trips: {tr["i"] for tr in trips if tr["timestamps"][0] <= 0 <= tr["timestamps"][-1]}
    assert len(alive(warm)) == 20 and len(alive(cold)) < 20


# ---------------------------------------------------------------- Hs texture

def decode(tex):
    assert tex["image"].startswith("data:image/png;base64,")
    return Image.open(io.BytesIO(base64.b64decode(tex["image"].split(",", 1)[1]))).convert("RGBA")


def test_hs_texture_transparent_below_threshold_and_size_bounded():
    ds = hs_bump(amp=4.0)
    tex = visual.hs_texture(ds, 1800.0, threshold=1.5, bbox=BBOX, max_px=128)
    im = decode(tex)
    assert max(im.size) <= 128 and tex["bounds"] == list(BBOX)
    assert len(tex["image"]) < 60_000
    a = np.asarray(im)
    h, w = a.shape[:2]
    lon = BBOX[0] + (np.arange(w) + 0.5) / w * (BBOX[2] - BBOX[0])
    ym = visual._merc_y(BBOX[3]) - (np.arange(h) + 0.5) / h * (visual._merc_y(BBOX[3]) - visual._merc_y(BBOX[1]))
    LL, LA = np.meshgrid(lon, visual._lat_from_merc(ym))
    hs = 4.0 * np.exp(-(((LL - 10.3) / 0.1) ** 2 + ((LA - 59.5) / 0.1) ** 2))
    assert (a[..., 3][hs < 1.5 - 0.05] == 0).all()                 # transparent below the threshold
    assert a[..., 3].max() > 0 and (a[..., 3][hs > 3.0] > 100).all()
    assert a[h // 2, w // 2, 3] > 0                               # the bump centre is drawn


def test_hs_texture_fixed_ramp_endpoints_and_determinism():
    ds = hs_bump(amp=7.0)
    t1, t2 = visual.hs_texture(ds, 0, bbox=BBOX), visual.hs_texture(ds, 0, bbox=BBOX)
    assert t1 == t2
    px = np.asarray(decode(t1))
    peak = px[px.shape[0] // 2, px.shape[1] // 2]            # Hs 7 m (> vmax) at the bump centre
    assert tuple(peak[:3]) == (0xFF, 0x5B, 0x3A)                   # accent at vmax
    with pytest.raises(ValueError):
        visual.hs_texture(ds, 0, cmap="viridis")


# ---------------------------------------------------------------- arrows / legend / scene

def test_arrows_regular_grid_and_length_proportional_to_speed():
    slow = visual.arrows(uniform(0.3, 0.0), 0, 64, bbox=BBOX)
    fast = visual.arrows(uniform(0.6, 0.0), 0, 64, bbox=BBOX)
    assert len(slow) == len(fast) > 50 and all(len(a["path"]) == 5 for a in slow)
    L = lambda a: a["path"][1][0] - a["path"][0][0]
    assert L(fast[0]) == pytest.approx(2 * L(slow[0]), rel=1e-3)
    assert visual.arrows(uniform(0.0, 0.0), 0, 64, bbox=BBOX) == []


def test_legend_has_ramp_units_and_source():
    lg = visual.legend("hs", "m", 0.0, 6.0)
    assert lg["units"] == "m" and lg["ramp"][-1][1] == [0xFF, 0x5B, 0x3A] and "CC BY 4.0" in lg["source"]
    with pytest.raises(ValueError):
        visual.legend("rain", "mm", 0, 1)


def test_weather_scene_shape_and_json_size_limit():
    sc = scene(n_particles=1000, t1=3600)
    assert set(sc) == {"particles", "hs", "arrows", "legend", "credit"}
    assert set(sc["particles"]) == {"kind", "trips", "trail_s"} and sc["particles"]["kind"] == "wind"
    assert [f["t"] for f in sc["hs"]["frames"]] == [0.0, 3600.0] and sc["hs"]["bounds"] == list(BBOX)
    assert set(sc["arrows"][0]) == {"t", "paths"} and set(sc["legend"]) == {"hs", "particles", "arrows"}
    assert "MET Norway" in sc["credit"] and "CC BY 4.0" in sc["credit"]
    tr = sc["particles"]["trips"][0]
    assert set(tr) == {"i", "path", "timestamps", "speed"} and len(tr["path"]) == len(tr["timestamps"]) == len(tr["speed"])
    assert len(json.dumps(sc)) < 3_000_000
    assert len({d["i"] for d in sc["particles"]["trips"]}) == 1000


def test_weather_scene_limits_and_optional_inputs():
    with pytest.raises(ValueError):
        scene(n_particles=6001)
    only_wave = visual.weather_scene(BBOX, 0, 3600, ds_wave=hs_bump())
    assert only_wave["particles"]["trips"] == [] and only_wave["arrows"] == [] and only_wave["hs"]["frames"]
    cur = visual.weather_scene(BBOX, 0, 3600, n_particles=50, ds_current=uniform(0.5, 0.0, names=("u", "v")))
    assert cur["particles"]["kind"] == "current"
    with pytest.raises(ValueError):
        visual.weather_scene(BBOX, 0, 3600 * 24, n_particles=6000, ds_wind=uniform(1, 0), out_dt_s=60)


def test_datetime_time_axis_is_converted_to_scene_seconds():
    ds = uniform(1.0, 0.0)
    ds = ds.assign_coords(time=np.datetime64("2024-01-10T00:00") + (ds.time.values * 1e9).astype("timedelta64[ns]"))
    a = visual.weather_scene(BBOX, 0, 3600, n_particles=20, ds_wind=ds, ds_wave=hs_bump().assign_coords(time=ds.time))
    b = visual.weather_scene(BBOX, 0, 3600, n_particles=20, ds_wind=uniform(1.0, 0.0), ds_wave=hs_bump())
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# ---------------------------------------------------------------- PSV effect in the simulation

def test_apply_psv_weather_matches_bands():
    r = effects.apply_psv_weather([1000, 1000, 1000, 1000], [6.0, 6.0, 6.0, 6.0], [1.0, 3.0, 4.0, 5.0])
    assert r["service_s"] == [1000.0, 1200.0, 1300.0, 1000.0]
    assert r["wow"] == [False, False, False, True]
    assert r["speed_mps"][0] == 6.0 and r["speed_mps"][1] == 6.0
    assert r["speed_mps"][2] == pytest.approx(6.0 - 2 * effects.KN) and r["speed_mps"][3] == pytest.approx(6.0 - 3 * effects.KN)
    assert r["service_factor"] == [1.0, 1.2, 1.3, 1.0] and r["speed_delta_kn"] == [0.0, 0.0, -2.0, -3.0]
    # band edges: 2.5 and 3.5 and 4.5 belong to the heavier band
    e = effects.apply_psv_weather(100.0, 5.0, [2.4999, 2.5, 3.5, 4.5])
    assert e["service_s"] == pytest.approx([100.0, 120.0, 130.0, 100.0]) and e["wow"] == [False, False, False, True]
    assert effects.apply_psv_weather([10], [0.5], [4.0])["speed_mps"][0] >= 0.125       # floor at 25 % of planned
    with pytest.raises(ValueError):
        effects.apply_psv_weather([1, 2], [1], [1, 1])


# ---------------------------------------------------------------- fetch (synthetic MET-shaped datasets)

def curvilinear(ny=60, nx=70, d=0.01, rot=0.3, dims=("y", "x")):
    j, i = np.meshgrid(np.arange(ny), np.arange(nx), indexing="ij")
    lon = 10.0 + d * (np.cos(rot) * i - np.sin(rot) * j) * 1.0
    lat = 59.2 + d * 0.5 * (np.sin(rot) * i + np.cos(rot) * j)
    return lon, lat


def _times(n=24, start="2024-01-10T00:00"):
    return np.datetime64(start) + np.arange(n).astype("timedelta64[h]")


def fake_nora3_wave():
    lon, lat = curvilinear(dims=("rlat", "rlon"))
    hs = 2 + 1.5 * np.sin((lon - 10) * 6) * np.cos((lat - 59.2) * 8)
    t = _times(48, "2024-01-09T12:00")
    data = hs[None] + 0.01 * np.arange(48)[:, None, None]
    return xr.Dataset({"hs": (("time", "rlat", "rlon"), data), "tp": (("time", "rlat", "rlon"), data * 3),
                       "thq": (("time", "rlat", "rlon"), data * 0 + 270.0)},
                      coords={"time": t, "longitude": (("rlat", "rlon"), lon), "latitude": (("rlat", "rlon"), lat)}), hs


def fake_nora3_wind():
    lon, lat = curvilinear()
    shape = (24, 2, *lon.shape)
    return xr.Dataset({"wind_speed": (("time", "height", "y", "x"), np.full(shape, 10.0)),
                       "wind_direction": (("time", "height", "y", "x"), np.full(shape, 270.0))},   # from the west
                      coords={"time": _times(24, "2024-01-10T00:00"), "height": [10.0, 20.0],
                              "longitude": (("y", "x"), lon), "latitude": (("y", "x"), lat)})


def fake_norkyst():
    lon, lat = curvilinear(dims=("Y", "X"))
    shape = (24, 3, *lon.shape)
    u = np.full(shape, 0.1); u[:, 0] = 0.5
    v = np.full(shape, 0.2); v[:, 0] = 0.2
    u[:, :, :5, :5] = np.nan                       # land corner
    return xr.Dataset({"u_eastward": (("time", "depth", "Y", "X"), u), "v_northward": (("time", "depth", "Y", "X"), v)},
                      coords={"time": _times(24, "2024-01-10T00:00"), "depth": [0.0, 3.0, 10.0],
                              "lon": (("Y", "X"), lon), "lat": (("Y", "X"), lat)})


@pytest.fixture
def served(monkeypatch):
    served = {}
    monkeypatch.setattr(fetch, "_open", lambda url: served[next(k for k in served if k in url)].copy())
    return served


def test_datasets_flags_and_unverified_raise():
    assert fetch.DATASETS["wam800"]["verified"] is False
    for name in ("nora3_wind", "nora3_wave", "norkyst_v3"):
        d = fetch.DATASETS[name]
        assert d["verified"] is True and d["live_checked"] is False and "metocean-api" in d["source"]
    with pytest.raises(NotImplementedError, match="unverified"):
        fetch.subset("wam800", BBOX, "2024-01-10T00:00", 6, "/tmp/never.nc")
    with pytest.raises(NotImplementedError, match="unverified"):
        fetch.subset("norkyst_v3", BBOX, "2026-03-01T00:00", 6, "/tmp/never.nc")      # beyond the verified range
    with pytest.raises(KeyError):
        fetch.subset("nope", BBOX, "2024-01-10T00:00", 6, "/tmp/never.nc")


def test_subset_wave_writes_scaled_regular_grid_with_manifest(served, tmp_path):
    ds, hs_fn = fake_nora3_wave()
    served["NORA3wave_sub_time_unlimited"] = ds
    out = tmp_path / "w.nc"
    bbox = (10.1, 59.25, 10.5, 59.55)
    m = fetch.subset("nora3_wave", bbox, "2024-01-10T00:00", 6, str(out))
    assert m["licence"] == "CC BY 4.0 — MET Norway" and m["vars"] == ["hs", "tp", "thq"] and m["shape"][0] == 6
    assert m["url"].endswith("202401_NORA3wave_sub_time_unlimited.nc") and "thredds.met.no/thredds/dodsC/nora3_subset_wave" in m["url"]
    raw = xr.open_dataset(out, mask_and_scale=False)
    assert raw["hs"].dtype == np.int16 and "scale_factor" in raw["hs"].attrs
    with xr.open_dataset(out) as r:
        assert r.sizes["time"] == 6 and np.all(np.diff(r.lon) > 0) and np.all(np.diff(r.lat) > 0)
        assert r.lon.min() >= bbox[0] - 0.02 and r.lon.max() <= bbox[2] + 1e-9
        LL, LA = np.meshgrid(r.lon.values, r.lat.values)
        want = 2 + 1.5 * np.sin((LL - 10) * 6) * np.cos((LA - 59.2) * 8)
        got = r["hs"].isel(time=0).values - 0.01 * 12          # file starts at 12 h into the served series
        ok = np.isfinite(got)
        assert ok.mean() > 0.9 and np.abs(got - want)[ok].max() < 0.05
        assert r.attrs["licence"] == "CC BY 4.0 — MET Norway"


def test_subset_wind_converts_direction_to_components(served, tmp_path):
    served["arome3kmwind_1hr_202401"] = fake_nora3_wind()
    m = fetch.subset("nora3_wind", (10.1, 59.25, 10.5, 59.55), "2024-01-10T00:00", 4, str(tmp_path / "wi.nc"))
    assert m["vars"] == ["u10", "v10"]
    with xr.open_dataset(tmp_path / "wi.nc") as r:
        assert float(np.nanmean(r.u10)) == pytest.approx(10.0, abs=0.01) and abs(float(np.nanmean(r.v10))) < 0.01   # westerly: blows east


def test_subset_current_takes_shallowest_level_and_keeps_land_nan(served, tmp_path):
    served["norkyst800-20240110"] = fake_norkyst()
    served["norkyst800-20240111"] = fake_norkyst().assign_coords(time=_times(24, "2024-01-11T00:00"))
    m = fetch.subset("norkyst_v3", (10.0, 59.2, 10.5, 59.5), "2024-01-10T20:00", 8, str(tmp_path / "c.nc"))
    assert len(m["urls"]) == 2 and m["shape"][0] == 8 and m["vars"] == ["u", "v"]
    with xr.open_dataset(tmp_path / "c.nc") as r:
        assert float(np.nanmedian(r.u)) == pytest.approx(0.5, abs=0.01) and float(np.nanmedian(r.v)) == pytest.approx(0.2, abs=0.01)
        assert np.isnan(r.u.values).any()
    # the written file feeds the visual layer directly
    with xr.open_dataset(tmp_path / "c.nc") as r:
        sc = visual.weather_scene((10.0, 59.2, 10.5, 59.5), 0, 3600, n_particles=30, ds_current=r.load())
    assert sc["particles"]["kind"] == "current" and sc["arrows"]


def test_int16_encoding_roundtrip_error_within_one_step():
    ds = xr.Dataset({"a": (("time", "lat", "lon"), np.random.default_rng(0).uniform(-3, 9, (2, 5, 6)))},
                    coords={"time": [0, 1], "lat": np.arange(5.0), "lon": np.arange(6.0)})
    enc = fetch.int16_encoding(ds)
    step = enc["a"]["scale_factor"]
    packed = np.round((ds["a"].values - (enc["a"]["add_offset"])) / step)
    assert packed.min() >= -32767 and packed.max() <= 32767
    assert np.abs(packed * step + enc["a"]["add_offset"] - ds["a"].values).max() <= step / 2 + 1e-12


def test_point_series_needs_metocean_api(monkeypatch):
    monkeypatch.setitem(sys.modules, "metocean_api", None)
    with pytest.raises(NotImplementedError, match="metocean-api"):
        fetch.point_series("nora3_wave", 10.3, 59.5, "2024-01-10T00:00", "2024-01-11T00:00")
    with pytest.raises(NotImplementedError, match="unverified"):
        fetch.point_series("wam800", 10.3, 59.5, "2024-01-10T00:00", "2024-01-11T00:00")


def test_fetch_world_metocean_hook_collects_errors_without_failing(monkeypatch, tmp_path):
    from offsim.worlds import fetch_world

    def boom(name, bbox, start, hours, path):
        if name == "nora3_wave":
            raise OSError("thredds down")
        return {"dataset": name, "licence": fetch.LICENCE, "file": path}

    monkeypatch.setattr(fetch, "subset", boom)
    entries = fetch_world.metocean(BBOX, tmp_path, "2024-01-10T00:00", 6)
    assert [e["dataset"] for e in entries] == ["nora3_wind", "nora3_wave", "norkyst_v3"]
    assert "thredds down" in entries[1]["error"] and entries[0]["file"] == "metocean/20240110-00_6h_nora3_wind.nc"
    assert (tmp_path / "metocean").is_dir()
