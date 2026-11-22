function ball(c, r, m, w=.9){
  const [X, Y] = P(...c), R = r*CAM_K;
  return `<circle cx="${f(X)}" cy="${f(Y)}" r="${f(R)}" fill="${m.m}" stroke="${INK}" stroke-width="${w}"/>`
    + `<circle cx="${f(X+R*.15)}" cy="${f(Y-R*.18)}" r="${f(R*.7)}" fill="${m.l}"/>`;
}


const stick = (a, b, r, col, w=.45) => { const d = pd([a, b], false), W = 2*r*CAM_K;
  return `<path d="${d}" fill="none" stroke="${col}" style="stroke-width:${W.toFixed(2)}" stroke-linecap="round"/>`; };
// Draw order from plan footprints. Everything here stands on the ground, so for two things whose footprints are
// disjoint convex polygons, the one nearer the viewer along the ground (g = view direction flattened) goes later.
// Only pairs that overlap on screen are compared; the result is a topological sort (ties: nearer last).
function planSort(items){
  const g = norm([CAM_V[0], CAM_V[1], 0]), pp = [-g[1], g[0]], N = items.length;
  for (const it of items){
    it.pg = it.fp.map(q => [q[0]*pp[0] + q[1]*pp[1], q[0]*g[0] + q[1]*g[1]]);
    const ps = it.pg.map(q => q[0]); it.p0 = Math.min(...ps); it.p1 = Math.max(...ps);
    it.dep = it.pg.reduce((a, q) => a + q[1], 0) / it.pg.length;
    let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9;
    for (const q of it.fp) for (const z of [it.z0 || 0, it.z1]){ const [X, Y] = P(q[0], q[1], z); x0 = Math.min(x0, X); x1 = Math.max(x1, X); y0 = Math.min(y0, Y); y1 = Math.max(y1, Y); }
    it.sb = [x0, y0, x1, y1];
  }
  const gAt = (pg, pm) => { let lo = 1e9, hi = -1e9;
    for (let i = 0; i < pg.length; i++){ const [p1, g1] = pg[i], [p2, g2] = pg[(i+1) % pg.length];
      if ((p1 - pm)*(p2 - pm) <= 0 && p1 !== p2){ const gg = g1 + (g2 - g1)*(pm - p1)/(p2 - p1); lo = Math.min(lo, gg); hi = Math.max(hi, gg); } }
    return lo > hi ? pg.reduce((a, q) => a + q[1], 0) / pg.length : (lo + hi) / 2; };
  const after = Array.from({ length: N }, () => []), indeg = new Array(N).fill(0);
  for (let i = 0; i < N; i++) for (let j = i + 1; j < N; j++){
    const A = items[i], B = items[j];
    if (A.sb[2] < B.sb[0] || B.sb[2] < A.sb[0] || A.sb[3] < B.sb[1] || B.sb[3] < A.sb[1]) continue;
    const lo = Math.max(A.p0, B.p0), hi = Math.min(A.p1, B.p1);
    if (hi - lo < 1e-4) continue;
    const pm = (lo + hi) / 2, ga = gAt(A.pg, pm), gb = gAt(B.pg, pm);
    if (Math.abs(ga - gb) < 1e-6) continue;
    if (ga < gb){ after[i].push(j); indeg[j]++; } else { after[j].push(i); indeg[i]++; }
  }
  const done = new Array(N).fill(false), out = [];
  for (let n = 0; n < N; n++){
    let best = -1;
    for (let i = 0; i < N; i++) if (!done[i] && indeg[i] === 0 && (best < 0 || items[i].dep < items[best].dep)) best = i;
    if (best < 0) for (let i = 0; i < N; i++) if (!done[i] && (best < 0 || items[i].dep < items[best].dep)) best = i;   // a cycle: nearest-last
    done[best] = true; out.push(items[best].svg);
    for (const j of after[best]) indeg[j]--;
  }
  return out.join('');
}
const sq = (x, y, r) => [[x-r, y-r], [x+r, y-r], [x+r, y+r], [x-r, y+r]];

const pfig = limbs => { const outl = new Map(), runs = [];
  for (const { a, b, r, col } of limbs){ const d = pd([a, b], false), k = r + col;
    const o = outl.get(k); if (o) o.d += d; else outl.set(k, { r, col, d });
    const last = runs[runs.length - 1]; if (last && last.k === k) last.d += d; else runs.push({ k, r, col, d }); }
  let s = '';
  for (const { r, col, d } of outl.values()) s += `<path d="${d}" fill="none" stroke="${mix(col, '#24182a', .5)}" style="stroke-width:${(2*r*CAM_K + .7*INK_K).toFixed(2)}" stroke-linecap="round"/>`;
  for (const { r, col, d } of runs) s += `<path d="${d}" fill="none" stroke="${col}" style="stroke-width:${(2*r*CAM_K).toFixed(2)}" stroke-linecap="round"/>`;
  return s; };
const pstick = (a, b, r, col) => { const d = pd([a, b], false), W = 2*r*CAM_K;
  return `<path d="${d}" fill="none" stroke="${mix(col, '#24182a', .5)}" style="stroke-width:${(W + .7*INK_K).toFixed(2)}" stroke-linecap="round"/>`
    + `<path d="${d}" fill="none" stroke="${col}" style="stroke-width:${W.toFixed(2)}" stroke-linecap="round"/>`; };
// walkers' shadows: collected while the frame is built and drawn as one path on the street, under everyone
let PED_SH = '';
const pedShadow = (x, y, z) => { const [X, Y] = P(x, y, z), rx = .34*CAM_K, ry = .17*CAM_K;
  PED_SH += `M${f(X-rx)} ${f(Y)}a${f(rx)} ${f(ry)} 0 1 0 ${f(2*rx)} 0a${f(rx)} ${f(ry)} 0 1 0 ${f(-2*rx)} 0`; };
function pedestrian(pd_, t){
  const L = [], pst = (a, b, r, col) => L.push({ a, b, r, col });
  const [x, y] = pd_.p, d = pd_.d, s = pd_.walked || 0, h = pd_.tall, n = [-d[1], d[0]];
  const ph = s * 2.4, sw = Math.sin(ph) * .26, bob = Math.abs(Math.cos(ph)) * .04;
  const at = (fwd, side, z) => [x + d[0]*fwd + n[0]*side, y + d[1]*fwd + n[1]*side, z];
  pedShadow(x, y, 0);
  let svg = '';
  // legs and arms: draw the far side first
  const legs = [[sw, .1], [-sw, -.1]].sort((p, q) => depthOf(at(0, p[1], 0)) - depthOf(at(0, q[1], 0)));
  for (const [fw, sd] of legs) pst(at(0, sd, .78*h + bob), at(fw, sd, .05), .1, pd_.pants);
  const armL = at(-sw*.8, .26, .98*h + bob), armR = at(sw*.8, -.26, .98*h + bob);
  const arms = [[armL, .26], [armR, -.26]].sort((p, q) => depthOf(p[0]) - depthOf(q[0]));
  dressTop(pst, at, h, bob, pd_, arms, d);
  svg += pfig(L);
  svg += ball([x, y, 1.6*h + bob], .21, pd_.skin, .5);
  const [HX, HY] = P(x, y, 1.62*h + bob), R = .215*CAM_K;      // hair (a cap over the top of the head) or a woolly hat
  svg += headTop(HX, HY, R, pd_.hair, pd_.hat);
  if (pd_.umb){   // an umbrella: a stick from the hand, a wide rim and the raised middle of the canopy
    const zc = 2.08*h + bob, ring = (r, z) => Array.from({ length: 12 }, (_, k) => [x + Math.cos(k*Math.PI/6)*r, y + Math.sin(k*Math.PI/6)*r, z]);
    svg += pstick(at(.12, -.18, 1.2*h + bob), [x, y, zc + .2], .03, '#3a3540') + shape(ring(.8, zc - .08), pd_.umb.m, .45) + fill(pd(ring(.48, zc + .16)), pd_.umb.l); }
  return { fp: sq(x, y, .35), z1: pd_.umb ? 2.9 : 2.3, svg };
}

function carDraw(cr){
  const c = cr.p, d = cr.d, M = cr.mesh, n = [-d[1], d[0]], hl = M.L/2, hw = M.W/2;
  const svg = drawVehicle(M, { c, d, z: 0, mats: { paint: cr.m, tail: cr.v < 1.2 ? V_BRAKE : V_TAIL }, w: .5 });   // brake lights while slowing or stopped
  const fp = [[-1,-1],[1,-1],[1,1],[-1,1]].map(([a, b]) => [c[0] + d[0]*hl*a + n[0]*hw*b, c[1] + d[1]*hl*a + n[1]*hw*b]);
  return { fp, z1: M.H, c, d, hl, hw, H: M.H, svg };
}
