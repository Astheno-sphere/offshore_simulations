// Frame-exact 2.5D renderer for a studio scene. render.py injects window.SCENE and calls
// window.draw(t) once per frame; nothing animates on its own, so every frame is reproducible.
import {Deck, WebMercatorViewport} from '@deck.gl/core';
import {PolygonLayer, ScatterplotLayer, ColumnLayer, PathLayer, TextLayer, IconLayer} from '@deck.gl/layers';
import {ScenegraphLayer} from '@deck.gl/mesh-layers';
import {GLTFLoader} from '@loaders.gl/gltf';
import {TripsLayer} from '@deck.gl/geo-layers';

const S = window.SCENE;
const st = S.style;
const hex = (h, a = 255) => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16), a];

document.body.style.background = st.water;
const root = document.documentElement.style;
for (const [k, v] of Object.entries({paper: st.paper, dim: st.dim, accent: st.accent, font: st.font, serif: st.serif, mono: st.mono}))
  root.setProperty(`--${k}`, v);
root.setProperty('--u', `${S.height / 60}px`);
const ov = document.getElementById('overlay');
ov.innerHTML = `
  <div class="kicker">${S.overlay.kicker || ''}</div>
  <div class="title">${S.overlay.title || ''}</div>
  <div class="clock" id="clock"></div>
  <div class="kpis" id="kpis"></div>
  <div class="legend">${(S.overlay.legend || []).map(([c, l]) => `<span><i style="background:${c}"></i>${l}</span>`).join('')}</div>
  <div class="source">${S.overlay.source || ''}</div>
  ${S.overlay.watermark ? `<div class="watermark">${S.overlay.watermark}</div>` : ''}`;

// position of every agent at time t: linear interpolation on its contract rows
function positions(t) {
  const out = [];
  for (const a of S.agents) {
    const ts = a.ts;
    if (t < ts[0]) continue;
    let i = 0, lo = 0, hi = ts.length - 1;
    if (t >= ts[hi]) i = hi; else { while (hi - lo > 1) { const m = (lo + hi) >> 1; if (ts[m] <= t) lo = m; else hi = m; } i = lo; }
    const j = Math.min(i + 1, ts.length - 1), f = ts[j] > ts[i] ? (t - ts[i]) / (ts[j] - ts[i]) : 0;
    const p = a.path[i], q = a.path[j];
    // heading from the leg being sailed (or the last one); degrees clockwise from north
    let k = j > i ? i : Math.max(0, i - 1), dx = 0, dy = 0;
    while (k < ts.length - 1 && dx === 0 && dy === 0) { dx = a.path[k + 1][0] - a.path[k][0]; dy = a.path[k + 1][1] - a.path[k][1]; if (!dx && !dy) k++; }
    if (!dx && !dy && a._heading !== undefined) { dx = Math.sin(a._heading * Math.PI / 180); dy = Math.cos(a._heading * Math.PI / 180); }
    const heading = Math.atan2(dx * Math.cos(p[1] * Math.PI / 180), dy) * 180 / Math.PI;
    a._heading = heading;
    out.push({id: a.id, cls: a.cls, accent: a.accent, state: a.states[i], heading,
              pos: [p[0] + (q[0] - p[0]) * f, p[1] + (q[1] - p[1]) * f, (p[2] || 0) + ((q[2] || 0) - (p[2] || 0)) * f]});
  }
  return out;
}

// camera.fit = [[west, south], [east, north]]: same extent in every output format; pitch/bearing on top
function view(cam) {
  if (!cam.fit) return cam;
  // keep the map clear of the title block (top) and legend/source (bottom)
  const p = cam.padding ?? 0.06, H = S.height, W = S.width;
  const pad = {top: Math.round(H * (0.22 + p)), bottom: Math.round(H * (0.12 + p)), left: Math.round(W * p), right: Math.round(W * (0.12 + p))};
  const {longitude, latitude, zoom} = new WebMercatorViewport({width: S.width, height: S.height}).fitBounds(cam.fit, {padding: pad});
  return {longitude, latitude, zoom: zoom + (cam.zoom_offset || 0), pitch: cam.pitch || 0, bearing: cam.bearing || 0};
}
const deck = new Deck({
  canvas: 'c', width: S.width, height: S.height, useDevicePixels: false, controller: false, _animate: false,
  initialViewState: view(S.camera),
});

const fmtClock = (s) => { const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60); return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`; };

function agentLayers(now, t) {
  const mode = st.agent_mode, sprites = S.assets.sprites || {}, models = S.assets.models || {};
  const dot = (data, id) => new ScatterplotLayer({id, data, getPosition: (d) => d.pos, radiusUnits: 'pixels', getRadius: st.agent_px,
    stroked: true, getLineColor: hex(st.ink), lineWidthMinPixels: 2, getFillColor: (d) => hex(d.accent ? st.accent : (st.cls[d.cls] || st.paper)),
    updateTriggers: {getPosition: t}});
  if (mode === 'model') {
    const layers = Object.entries(models).map(([cls, url]) => new ScenegraphLayer({id: `agent-${cls}`, data: now.filter((d) => d.cls === cls),
      scenegraph: url, loaders: [GLTFLoader], getPosition: (d) => d.pos, getOrientation: (d) => [0, -d.heading, 90],
      getScale: [st.agent_model_scale, st.agent_model_scale, st.agent_model_scale], _lighting: 'pbr', updateTriggers: {getPosition: t, getOrientation: t}}));
    return [...layers, dot(now.filter((d) => !models[d.cls]), 'agents-dot')];
  }
  if (mode === 'sprite') {
    // sprites face west; mirror for eastbound so the bow leads
    const icon = (d) => { const key = st.sprites[d.cls]; const side = d.heading > 0 && d.heading < 180 ? 'E' : 'W'; return key && sprites[`${key}_${side}`] ? `${key}_${side}` : null; };
    const withIcon = now.filter((d) => icon(d));
    return [
      new ScatterplotLayer({id: 'agent-ring', data: withIcon.filter((d) => d.accent), getPosition: (d) => d.pos, radiusUnits: 'pixels',
        getRadius: st.sprite_px * 0.62, filled: true, getFillColor: hex(st.accent, 70), stroked: true, getLineColor: hex(st.accent), lineWidthMinPixels: 2,
        updateTriggers: {getPosition: t}}),
      new IconLayer({id: 'agent-sprites', data: withIcon, getPosition: (d) => d.pos, sizeUnits: 'pixels', getSize: st.sprite_px,
        getIcon: (d) => ({id: icon(d), url: sprites[icon(d)], width: 256, height: 256, anchorY: 160}), billboard: true,
        updateTriggers: {getPosition: t, getIcon: t}}),
      dot(now.filter((d) => !icon(d)), 'agents-dot')];
  }
  return [dot(now, 'agents-dot')];
}

// textures and models load asynchronously: wait until every layer reports loaded before capture
const allLoaded = () => (deck.layerManager ? deck.layerManager.getLayers() : []).every((l) => l.isLoaded);
window.draw = (t) => new Promise((resolve) => {
  const now = positions(t);
  const layers = [
    new PolygonLayer({id: 'land', data: S.world.land || [], getPolygon: (d) => d, extruded: true, getElevation: S.land_relief_m ?? st.land_relief_m,
      getFillColor: hex(st.land), getLineColor: hex(st.paper, 140), stroked: true, lineWidthMinPixels: 1, material: {ambient: 0.6, diffuse: 0.5}}),
    new PathLayer({id: 'lanes', data: S.world.lanes || [], getPath: (d) => d, getColor: hex(st.faint_line), widthMinPixels: 1}),
    ...Object.entries(S.assets.models || {}).map(([kind, url]) => new ScenegraphLayer({id: `site-${kind}`,
      data: (S.world.sites || []).filter((d) => d.kind === kind), scenegraph: url, loaders: [GLTFLoader],
      getPosition: (d) => d.pos, getOrientation: (d) => [0, d.yaw || 0, 90],
      getScale: (d) => { const k = d.scale || st.site_model_scale; return [k, k, k]; }, _lighting: 'pbr'})),
    new ColumnLayer({id: 'sites', data: (S.world.sites || []).filter((d) => !(S.assets.models || {})[d.kind]), getPosition: (d) => d.pos, diskResolution: 6, radius: st.site_radius_m,
      extruded: true, getElevation: (d) => d.height_m || st.site_height_m, getFillColor: (d) => hex(d.accent ? st.accent : st.paper)}),
    new TextLayer({id: 'site-labels', data: (S.world.sites || []).filter((d) => d.label), getPosition: (d) => [d.pos[0], d.pos[1], (d.height_m || st.site_height_m) * 1.3],
      getText: (d) => d.label, getColor: hex(st.dim), getSize: st.label_px, fontFamily: st.font, getTextAnchor: 'start', getPixelOffset: [8, 0]}),
    new TripsLayer({id: 'trails', data: S.agents, getPath: (d) => d.path, getTimestamps: (d) => d.ts, currentTime: t,
      trailLength: S.trail_s, fadeTrail: true, capRounded: true, jointRounded: true, widthMinPixels: st.trail_px,
      getColor: (d) => hex(d.accent ? st.accent : (st.cls[d.cls] || st.paper))}),
    ...agentLayers(now, t),
    new ScatterplotLayer({id: 'halo', data: now.filter((d) => st.state[d.state]), getPosition: (d) => d.pos, radiusUnits: 'pixels',
      getRadius: st.agent_px * 2.2, filled: false, stroked: true, lineWidthMinPixels: 2, getLineColor: (d) => hex(st.state[d.state])}),
  ];
  document.getElementById('clock').textContent = fmtClock(t);
  const k = (S.overlay.kpi_track || []).map(([label, series]) => {
    let v = series[0][1]; for (const [ts, val] of series) { if (ts <= t) v = val; else break; } return `<div><b>${v}</b>${label}</div>`;
  });
  document.getElementById('kpis').innerHTML = k.join('');
  let tries = 0;
  deck.setProps({layers, onAfterRender: () => {
    if (allLoaded() || tries++ > 200) resolve(); else setTimeout(() => deck.redraw(true), 15);
  }});
  deck.redraw(true);
});
window.__layers = () => deck.layerManager.getLayers().map((l) => [l.id, l.isLoaded, (l.props.data || []).length]);
window.ready = true;
