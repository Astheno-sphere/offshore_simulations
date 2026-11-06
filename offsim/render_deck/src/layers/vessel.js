// Display-only vessel pose and wake. Pure functions of t (no Date.now, no state): frame-exact for window.draw(t).
// Input agents are the DISPLAY copy from offsim.cinema.vessel.display_agents:
//   {id, cls, accent, path: [[lon, lat, z]], ts, states, heading, roll, pitch, heave}
// Agents without the extra arrays (a plain scene agent) fall back to heading-from-leg and zero roll/pitch/heave.
// Constants mirror offsim/cinema/rules.py VESSEL (kept in sync by tests/test_vessel.py).
import {PathLayer} from '@deck.gl/layers';

export const KELVIN_HALF_ANGLE_DEG = 19.47;
export const WAKE_LEN_SHIPS = [8, 12];
export const WAKE_REF_MPS = 7.0;
export const WAKE_ALPHA_MAX = 0.6;
const EARTH_R = 6371008.8, RAD = Math.PI / 180;

const hex = (h, a = 255) => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16), a];
const wrap360 = (d) => ((d % 360) + 360) % 360;

// last index i with ts[i] <= t (clamped to [0, n-1])
function locate(ts, t) {
  let lo = 0, hi = ts.length - 1;
  if (t >= ts[hi]) return hi;
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (ts[m] <= t) lo = m; else hi = m; }
  return lo;
}

// metres east/north of (lon0, lat0)
const toXY = (p, lon0, lat0) => [EARTH_R * Math.cos(lat0 * RAD) * (p[0] - lon0) * RAD, EARTH_R * (p[1] - lat0) * RAD];
const toLL = (x, y, lon0, lat0) => [lon0 + x / (EARTH_R * Math.cos(lat0 * RAD)) / RAD, lat0 + y / EARTH_R / RAD];

// Interpolated display pose at time t, or null before the agent exists.
// heading is unwrapped across the 0/360 seam (shortest way round) before interpolating.
export function displayPose(agent, t) {
  const ts = agent.ts;
  if (!ts || !ts.length || t < ts[0]) return null;
  const i = locate(ts, t), j = Math.min(i + 1, ts.length - 1);
  const f = ts[j] > ts[i] ? Math.min(1, Math.max(0, (t - ts[i]) / (ts[j] - ts[i]))) : 0;
  const p = agent.path[i], q = agent.path[j];
  const lerp = (a, b) => a + (b - a) * f;
  let heading;
  if (agent.heading) {
    const h0 = agent.heading[i], d = ((agent.heading[j] - h0 + 540) % 360) - 180;
    heading = wrap360(h0 + d * f);
  } else {
    let k = i, dx = 0, dy = 0;                                  // fallback: bearing of the current/last moving leg
    while (k < ts.length - 1 && !dx && !dy) { dx = agent.path[k + 1][0] - agent.path[k][0]; dy = agent.path[k + 1][1] - agent.path[k][1]; if (!dx && !dy) k++; }
    for (k = i; k > 0 && !dx && !dy; k--) { dx = agent.path[k][0] - agent.path[k - 1][0]; dy = agent.path[k][1] - agent.path[k - 1][1]; }
    heading = wrap360(Math.atan2(dx * Math.cos(p[1] * RAD), dy) / RAD);
  }
  const ch = (name) => (agent[name] ? lerp(agent[name][i], agent[name][j]) : 0);
  const [x0, y0] = toXY(p, p[0], p[1]), [x1, y1] = toXY(q, p[0], p[1]);
  const dt = ts[j] - ts[i];
  const speed = dt > 0 ? Math.hypot(x1 - x0, y1 - y0) / dt : 0;     // m/s over the current sample interval
  return {id: agent.id, cls: agent.cls, accent: agent.accent, agent, state: agent.states ? agent.states[i] : undefined,
          heading, roll: ch('roll'), pitch: ch('pitch'), heave: ch('heave'), speed,
          pos: [lerp(p[0], q[0]), lerp(p[1], q[1]), lerp(p[2] || 0, q[2] || 0)]};
}

// Kelvin wake segments from a track history (oldest first, last = vessel now). Mirror of vessel.py wake().
export function wakeSegments(history, speed, lengthM, {nSeg = 12, lenShips = 10} = {}) {
  const a0 = WAKE_ALPHA_MAX * Math.min(1, Math.max(0, speed) / WAKE_REF_MPS);
  if (history.length < 2 || a0 < 0.01) return [];
  const [lon0, lat0] = history[history.length - 1];
  const pts = [];                                                // newest first, repeated points dropped
  for (let k = history.length - 1; k >= 0; k--) {
    const xy = toXY(history[k], lon0, lat0), last = pts[pts.length - 1];
    if (!last || Math.hypot(xy[0] - last[0], xy[1] - last[1]) > 1e-6) pts.push(xy);
  }
  if (pts.length < 2) return [];
  const back = [0];
  for (let k = 1; k < pts.length; k++) back.push(back[k - 1] + Math.hypot(pts[k][0] - pts[k - 1][0], pts[k][1] - pts[k - 1][1]));
  const W = Math.min(Math.min(WAKE_LEN_SHIPS[1], Math.max(WAKE_LEN_SHIPS[0], lenShips)) * lengthM, back[back.length - 1]);
  const tan = Math.tan(KELVIN_HALF_ANGLE_DEG * RAD);
  const at = [];
  for (let j = 0; j <= nSeg; j++) {
    const d = (W * j) / nSeg;
    let k = 0; while (k < back.length - 2 && back[k + 1] <= d) k++;
    const u = back[k + 1] > back[k] ? (d - back[k]) / (back[k + 1] - back[k]) : 0;
    const x = pts[k][0] + (pts[k + 1][0] - pts[k][0]) * u, y = pts[k][1] + (pts[k + 1][1] - pts[k][1]) * u;
    let dx = pts[k][0] - pts[k + 1][0], dy = pts[k][1] - pts[k + 1][1];   // direction of travel
    const n = Math.hypot(dx, dy); dx /= n; dy /= n;
    at.push({d, x, y, dx, dy});
  }
  const out = [];
  for (const [kind, side] of [['arm_l', 1], ['arm_r', -1], ['trail', 0]]) {
    const P = at.map((a) => toLL(a.x - a.dy * side * a.d * tan, a.y + a.dx * side * a.d * tan, lon0, lat0));
    for (let j = 0; j < nSeg; j++) {
      const fade = Math.max(0, 1 - (0.5 * (at[j].d + at[j + 1].d)) / Math.max(W, 1e-9));
      out.push({kind, path: [P[j], P[j + 1]], alpha: a0 * fade * (kind === 'trail' ? 0.5 : 1)});
    }
  }
  return out;
}

// PathLayer of fading wake arms + centre trail for every pose that carries its agent.
// style: {wake_color: '#rrggbb', wake_px, wake_len_ships, vessel_length_m, wake_cls: {cls: lengthM}}.
export function wakeLayers(posesNow, t, style = {}) {
  const data = [];
  for (const p of posesNow) {
    if (!p || !p.agent || p.speed < 0.3) continue;
    const L = (style.wake_cls && style.wake_cls[p.cls]) ?? style.vessel_length_m ?? 76;
    const W = Math.min(WAKE_LEN_SHIPS[1], Math.max(WAKE_LEN_SHIPS[0], style.wake_len_ships ?? 10)) * L;
    const dt = Math.max(2, W / Math.max(p.speed, 0.5) / 24);       // 24 history samples spanning the wake length
    const hist = [];
    for (let k = 24; k >= 0; k--) { const q = displayPose(p.agent, t - k * dt); if (q) hist.push(q.pos); }
    data.push(...wakeSegments(hist, p.speed, L, {lenShips: style.wake_len_ships ?? 10}));
  }
  const rgb = hex(style.wake_color || '#ffffff');
  return [new PathLayer({id: 'vessel-wake', data, getPath: (d) => d.path, getColor: (d) => [rgb[0], rgb[1], rgb[2], Math.round(255 * d.alpha)],
    widthUnits: 'pixels', getWidth: style.wake_px ?? 1.5, capRounded: true, updateTriggers: {getPath: t, getColor: t}})];
}
