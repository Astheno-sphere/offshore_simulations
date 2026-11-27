// Stress-pair delta layer for the deck.gl renderer. Pure function of t (simulation seconds, the same clock TripsLayer uses): no wall
// clock, no randomness, nothing that changes what is drawn.
//
//   import {deltaLayers} from './layers/delta.js';   // layers = [...base, ...deltaLayers(S.delta, t, st)]
//
// `delta` is the block offsim.motion.delta.delta_block put in scene.json, already verified in Python (sidecar SHA-256s are checked where
// the report lives; this file only draws): variant_names [candidate, baseline], rung_t/pa/pb (the paired positions a(t_i)-b(t_i) on the
// union time grid), track_a/track_b {path, ts}, t_star_s, t_star_connector, style {ribbon_alpha, track_px}. null/undefined -> no layers.
//
// What is drawn: the ribbon between the two tracks up to t (one polygon, so overlapping alphas never compound), the two tracks up to t
// (candidate in the accent, baseline in paper: colour is the identity, there is no dash here because dashes need a deck.gl extension
// this renderer does not depend on), and, once t >= t_star_s, the connector between the two tracks at the moment of largest divergence
// in the accent with end dots. The ribbon's width at any moment is the divergence at that moment; no number is printed by this layer.
import {PathLayer, ScatterplotLayer, SolidPolygonLayer} from '@deck.gl/layers';

const hex = (h, a = 255) => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16), a];
const lerp2 = (p, q, f) => [p[0] + (q[0] - p[0]) * f, p[1] + (q[1] - p[1]) * f];

// index of the last element <= t (binary search), -1 when t is before the first
function lastLE(ts, t) {
  if (!ts.length || t < ts[0]) return -1;
  let lo = 0, hi = ts.length - 1;
  if (t >= ts[hi]) return hi;
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (ts[m] <= t) lo = m; else hi = m; }
  return lo;
}

// the track's done part at t: every point with time <= t, then the interpolated position at t while it is still under way
function doneTrack(tr, t) {
  const i = lastLE(tr.ts, t);
  if (i < 0) return [];
  const pts = tr.path.slice(0, i + 1).map((p) => [p[0], p[1]]);
  if (i < tr.ts.length - 1) {
    const f = (t - tr.ts[i]) / (tr.ts[i + 1] - tr.ts[i]);
    pts.push(lerp2(tr.path[i], tr.path[i + 1], f));
  }
  return pts;
}

// The geometry at t, as numbers (exported so it can be checked against offsim.motion.delta.delta_geometry without a browser).
// Rungs with rung_t <= min(t, window end) plus a front rung at t: both tracks are linear between consecutive rungs, so interpolating the
// rung positions linearly IS the exact front.
export function deltaGeometryAt(delta, t) {
  const rt = delta.rung_t, n = rt.length;
  let pa = [], pb = [];
  if (n && t >= rt[0]) {
    const tc = Math.min(t, rt[n - 1]);
    const k = lastLE(rt, tc);
    pa = delta.pa.slice(0, k + 1).map((p) => [p[0], p[1]]);
    pb = delta.pb.slice(0, k + 1).map((p) => [p[0], p[1]]);
    if (rt[k] < tc) {
      const f = (tc - rt[k]) / (rt[k + 1] - rt[k]);
      pa.push(lerp2(delta.pa[k], delta.pa[k + 1], f));
      pb.push(lerp2(delta.pb[k], delta.pb[k + 1], f));
    }
  }
  return {pa, pb, trackA: doneTrack(delta.track_a, t), trackB: doneTrack(delta.track_b, t),
          connector: t >= delta.t_star_s ? delta.t_star_connector : null};
}

export function deltaLayers(delta, t, style) {
  if (!delta) return [];
  const g = deltaGeometryAt(delta, t);
  const accent = hex(style.accent), paper = hex(style.paper), s = delta.style;
  const ring = g.pa.concat(g.pb.slice().reverse());
  const layers = [];
  // annotation, not terrain: no depth test, so the hillshade mesh never hides or tints it, and the accent fill is low-alpha
  const over = {depthTest: false};
  if (g.pa.length >= 2) {
    layers.push(new SolidPolygonLayer({id: 'delta-ribbon', data: [{polygon: ring}], getPolygon: (d) => d.polygon, filled: true,
      getFillColor: hex(style.accent, Math.round(255 * s.ribbon_alpha)), parameters: over}));
    layers.push(new PathLayer({id: 'delta-ribbon-edge', data: [{path: ring.concat([ring[0]])}], getPath: (d) => d.path,
      getColor: hex(style.accent, 120), widthMinPixels: 1, jointRounded: true, parameters: over}));
  }
  if (g.trackB.length >= 2) layers.push(new PathLayer({id: 'delta-track-b', data: [{path: g.trackB}], getPath: (d) => d.path, getColor: paper,
    widthMinPixels: s.track_px, capRounded: true, jointRounded: true, parameters: over}));
  if (g.trackA.length >= 2) layers.push(new PathLayer({id: 'delta-track-a', data: [{path: g.trackA}], getPath: (d) => d.path, getColor: accent,
    widthMinPixels: s.track_px, capRounded: true, jointRounded: true, parameters: over}));
  if (g.connector) {
    layers.push(new PathLayer({id: 'delta-connector', data: [{path: g.connector}], getPath: (d) => d.path, getColor: accent,
      widthMinPixels: s.track_px * 1.5, capRounded: true, parameters: over}));
    layers.push(new ScatterplotLayer({id: 'delta-connector-ends', data: g.connector.map((p, i) => ({pos: p, c: i ? paper : accent})),
      getPosition: (d) => d.pos, getFillColor: (d) => d.c, radiusUnits: 'pixels', getRadius: 4, parameters: over}));
  }
  return layers;
}
