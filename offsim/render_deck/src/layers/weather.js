// Weather layers for the deck.gl renderer. Pure function of t: no clocks, no randomness, no state that changes
// what is drawn (the colour cache below only memoises a pure computation).
//
//   import {weatherLayers} from './layers/weather.js';   // layers = [...base, ...weatherLayers(S.weather, t, st)]
//
// `weather` is the block built by offsim.weather.visual.weather_scene (null/undefined -> no layers):
//   particles {kind, trips[{path, timestamps, speed}], trail_s}   hs {frames[{t, image}], bounds}
//   arrows [{t, paths[{path, speed}]}]                            legend {particles, arrows, hs}
import {BitmapLayer, PathLayer} from '@deck.gl/layers';
import {TripsLayer} from '@deck.gl/geo-layers';

// colour of a speed on a legend ramp [[fraction, [r,g,b], alpha], ...] between vmin and vmax
export function rampColour(ramp, vmin, vmax, v, alphaScale = 1) {
  const f = Math.min(1, Math.max(0, (v - vmin) / ((vmax - vmin) || 1)));
  let i = 1;
  while (i < ramp.length - 1 && ramp[i][0] < f) i++;
  const [f0, c0, a0] = ramp[i - 1];
  const [f1, c1, a1] = ramp[i];
  const w = f1 > f0 ? Math.min(1, Math.max(0, (f - f0) / (f1 - f0))) : 0;
  const m = (x, y) => x + (y - x) * w;
  return [Math.round(m(c0[0], c1[0])), Math.round(m(c0[1], c1[1])), Math.round(m(c0[2], c1[2])), Math.round(255 * alphaScale * m(a0, a1))];
}

// index of the frame at or before t, and blend weight towards the next frame; clamped at both ends
export function bracket(times, t) {
  const n = times.length;
  if (n === 0) return null;
  if (n === 1 || t <= times[0]) return {i0: 0, i1: 0, w: 0};
  if (t >= times[n - 1]) return {i0: n - 1, i1: n - 1, w: 0};
  let i = 0;
  while (i + 1 < n && times[i + 1] <= t) i++;
  return {i0: i, i1: i + 1, w: (t - times[i]) / (times[i + 1] - times[i])};
}

const tripColours = new WeakMap();   // trips array -> (trip -> rgba, mean speed on the legend ramp)
function coloursFor(trips, legend) {
  let c = tripColours.get(trips);
  if (!c) {
    c = new WeakMap();
    for (const d of trips) {
      const s = d.speed || [];
      const mean = s.length ? s.reduce((a, b) => a + b, 0) / s.length : 0;
      c.set(d, rampColour(legend.ramp, legend.vmin, legend.vmax, mean));
    }
    tripColours.set(trips, c);
  }
  return c;
}

export function weatherLayers(weather, t, style) {
  if (!weather) return [];
  const layers = [];

  // Hs: two BitmapLayers cross-fading between the bracketing hourly frames (ids per frame so textures persist)
  const hs = weather.hs;
  if (hs && hs.frames && hs.frames.length) {
    const b = bracket(hs.frames.map((f) => f.t), t);
    const parts = b.i0 === b.i1 ? [[b.i0, 1]] : [[b.i0, 1 - b.w], [b.i1, b.w]];
    for (const [i, op] of parts)
      layers.push(new BitmapLayer({id: `hs-${i}`, image: hs.frames[i].image, bounds: hs.bounds, opacity: op, pickable: false,
        parameters: {depthTest: false}}));
  }

  // current arrows: same 5-vertex topology in every frame, so blend vertex by vertex
  const frames = weather.arrows || [];
  const lg = (weather.legend || {}).arrows;
  if (frames.length && lg) {
    const b = bracket(frames.map((f) => f.t), t);
    const A = frames[b.i0].paths, B = frames[b.i1].paths;
    const data = A.map((p, k) => {
      const q = B[k] || p;
      const path = b.i0 === b.i1 ? p.path : p.path.map((v, j) => [v[0] + (q.path[j][0] - v[0]) * b.w, v[1] + (q.path[j][1] - v[1]) * b.w]);
      return {path, speed: p.speed + (q.speed - p.speed) * b.w};
    });
    layers.push(new PathLayer({id: 'weather-arrows', data, getPath: (d) => d.path,
      getColor: (d) => rampColour(lg.ramp, lg.vmin, lg.vmax, d.speed), widthUnits: 'pixels', getWidth: style.line_px ?? 1.3,
      capRounded: true, jointRounded: true, parameters: {depthTest: false}}));
  }

  // particles: pre-integrated trips, drawn at currentTime = t (the only clock)
  const p = weather.particles;
  const pl = (weather.legend || {}).particles;
  if (p && p.trips && p.trips.length && pl) {
    const colours = coloursFor(p.trips, pl);
    layers.push(new TripsLayer({id: 'weather-particles', data: p.trips, getPath: (d) => d.path, getTimestamps: (d) => d.timestamps,
      currentTime: t, trailLength: p.trail_s, fadeTrail: true, widthUnits: 'pixels', getWidth: 1, widthMinPixels: style.particle_px ?? 1,
      capRounded: true, jointRounded: true, getColor: (d) => colours.get(d), parameters: {depthTest: false},
      updateTriggers: {getColor: [pl.vmax]}}));
  }
  return layers;
}
