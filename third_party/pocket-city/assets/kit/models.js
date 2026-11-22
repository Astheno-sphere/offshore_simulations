/* Pocket City trees, shared by both cities: the eight styles picked from the tree gallery (numbers as in the gallery).
   1 linden · 2 elm vase · 3 chestnut · 4 dense · 5 airy · 6 chunky · 7 column · 18 spruce
   A tree is a branching skeleton (round-capped strokes) and a few hundred small flat leaf cards, built once in world
   coordinates. A frame only projects it: the wood, then the back leaves, then the front ones, with the leaves of one colour
   and one tone merged into one shape, so a tree is about a dozen elements. The shadows are illustrative.
   Needs core3d.js (pd, depthOf, vis, rotV, L, CAM_K, norm, cross, mix). */
// a phone-sized page draws lighter (fewer leaves and people, no glazing bars); the page tells its frame workers its width
const PHONE = self.PHONE_PROFILE;
const TREE_LOD = +(new URLSearchParams(self.PAGE_SEARCH ?? location.search).get('leaves') || (PHONE ? .22 : .35));   // city scale: a third of the gallery's leaves, each larger
const TREE_FORM = {   // fork: where the trunk splits (share of height); w: crown half-width (share of height); vase: wider at the top
  1: { fork: .3,  w: .34, limbs: 5, leader: true,  twigs: 4, count: 230, size: .058, spread: .22 },
  2: { fork: .28, w: .38, limbs: 5, vase: .5,      twigs: 4, count: 230, size: .058, spread: .22 },
  3: { fork: .3,  w: .42, limbs: 6,                twigs: 4, count: 250, size: .06,  spread: .22 },
  4: { fork: .3,  w: .34, limbs: 5,                twigs: 5, count: 420, size: .038, spread: .2 },
  5: { fork: .35, w: .24, limbs: 6, leader: true,  twigs: 4, count: 120, size: .04,  spread: .3, wood: .7 },
  6: { fork: .3,  w: .36, limbs: 5,                twigs: 3, count: 90,  size: .1,   spread: .2 },
  7: { fork: .2,  w: .14, limbs: 6, leader: true,  twigs: 4, count: 220, size: .045, spread: .14 },
};
// makeTree(style, { x, y, z0, H, seed, m, m2, share2, lod }): m is the leaf colour {l, m, d}; m2 an optional second colour
// mixed in at share2;
// lod < 1 keeps that share of the leaves and makes each one larger, so the crown covers the same area with less to draw
function makeTree(style, { x, y, z0 = 0, H = 11, seed = 1, m, m2, share2 = .35, lod = 1 }){
  let sd = Math.floor(seed * 7919) % 2147483646 + 1; const R = () => { sd = (sd * 16807) % 2147483647; return (sd - 1) / 2147483646; };
  const lerp3 = (a, b, k) => [a[0] + (b[0]-a[0])*k, a[1] + (b[1]-a[1])*k, a[2] + (b[2]-a[2])*k];
  const add3 = (a, b, k = 1) => [a[0] + b[0]*k, a[1] + b[1]*k, a[2] + b[2]*k];
  const segs = [], twigs = [], leaves = [], base = [x, y, z0];
  if (style === 18){   // spruce: a straight trunk and twelve tiers of drooping needle cards, narrowing to the tip
    const k0 = H / 11; segs.push([base, [x, y, z0 + H*.8], .16*k0]);   // the trunk ends inside the top tiers
    for (let k = 0; k < 12; k++){ const z = z0 + (1.6 + k*.78)*k0, r = (3.1*(1 - k/12) + .3)*k0, n = Math.max(6, Math.round(r/k0*5));
      for (let i = 0; i < n; i++){ const a = i/n*Math.PI*2 + k*.4 + R()*.2, out = [Math.cos(a), Math.sin(a), 0], c = [x + out[0]*r*.55, y + out[1]*r*.55, z - .25*k0];
        const nn = norm([out[0]*.5, out[1]*.5, 1]), t = norm([out[0], out[1], -.45]), sd2 = cross(nn, t), L2 = r*.55, W = .45*k0;
        leaves.push({ c, n: nn, m, pts: [add3(c, t, -L2), add3(c, sd2, W), add3(c, t, L2), add3(c, sd2, -W)] }); } }
    leaves.forEach((lf, i) => { lf.k = (i*.618034) % 1; lf.j = (i*.754878 + .5) % 1; });
    return { x, y, segs, twigs: [], leaves, zc: z0 + H*.45, zTop: z0 + H, ext: 3.4*k0 };
  }
  const fm = TREE_FORM[style] || TREE_FORM[1], wood = fm.wood || 1, vase = fm.vase || 0;
  const zf = z0 + H*fm.fork, zc = (zf + z0 + H)/2 + H*.04, rz = (z0 + H - zf)/2, C = [x, y, zc];
  // the crown's outer shell at height u (-1 bottom .. 1 top) and direction a: an ellipsoid, a vase leans its width up
  const shell = (u, a) => { const k = Math.sqrt(Math.max(0, 1 - u*u)) * (1 + vase*(u - .2)); return [x + Math.cos(a)*H*fm.w*k, y + Math.sin(a)*H*fm.w*k, zc + u*rz]; };
  segs.push([base, [x, y, zf], (.1 + H*.008)*wood]);
  const tips = [], n = fm.limbs + (fm.leader ? 1 : 0);
  for (let k = 0; k < n; k++){
    const lead = fm.leader && k === n - 1, a = k/fm.limbs*Math.PI*2 + R()*.9;
    const u = lead ? .85 : (vase ? .25 + R()*.45 : -.05 + R()*.5);
    const end = lead ? [x, y, zc + rz*.85] : lerp3(C, shell(u, a), .78), mid = lerp3([x, y, zf], end, .5); mid[2] += H*.03;
    const r0 = (.045 + H*.0045)*wood; segs.push([[x, y, zf], mid, r0], [mid, end, r0*.65]);
    for (let j = 0; j < fm.twigs; j++){
      const tip = lerp3(C, shell(Math.max(-.7, Math.min(.9, u + (R() - .5)*.7)), a + (R() - .5)*1.1), .92);
      twigs.push([lerp3(mid, end, .4 + R()*.6), tip, r0*.35]); tips.push(tip); }   // twigs show only when the crown is bare
  }
  // leaves: small kite-shaped cards around the twig tips, each turned its own way (mostly facing up and out)
  const count = Math.max(Math.round(fm.count*lod), Math.min(fm.count, PHONE ? 32 : 68)), grow = Math.sqrt(fm.count/count);   // never thinner than 90 leaves
  for (let i = 0; i < count; i++){
    const t = tips[i % tips.length], q = [t[0] + (R() - .5)*H*fm.spread, t[1] + (R() - .5)*H*fm.spread, t[2] + (R() - .5)*H*fm.spread*.75];
    const out = norm([q[0] - x, q[1] - y, 0]), nn = norm([out[0]*.55 + (R() - .5)*.9, out[1]*.55 + (R() - .5)*.9, .75 + R()*.4]);
    const rot = R()*6.3, t1 = norm(cross(nn, [Math.cos(rot), Math.sin(rot), .3])), t2 = cross(nn, t1), s = 1.18*H*fm.size*grow*(.75 + R()*.5);
    const at = (a, b) => add3(add3(q, t1, a), t2, b);
    // k, j: two evenly spread ranks, so a season can keep a share of the leaves (k) or colour a share of them (j)
    leaves.push({ c: q, n: nn, m: m2 && R() < share2 ? m2 : m, k: (i*.618034) % 1, j: (i*.754878 + .5) % 1, pts: [at(s, 0), at(s*.42, s*.52), at(-s*.22,s*.6), at(-s*.85, 0), at(-s*.25,-s*.55), at(s*.32,-s*.48)] });
  }
  const vertices=new Set([...segs,...twigs].flatMap(([a,b])=>[a,b]));
  for(const leaf of leaves){vertices.add(leaf.c);for(const p of leaf.pts)vertices.add(p)}
  const peak=Math.max(...[...vertices].map(p=>p[2]));
  const heightScale=H/(peak-z0);
  for(const p of vertices)p[2]=z0+(p[2]-z0)*heightScale;
  return { x, y, segs, twigs, leaves, zc:z0+(zc-z0)*heightScale, zTop: z0 + H, ext: H*fm.w*(1 + vase*.8) + H*fm.spread*.5 };
}
// drawTree(T, { ink, inkK, bark, keep, m, m2, share }): the svg for one tree from the current camera. A season sets keep
// (the share of leaves still on), m (their colour, else each leaf's own) and m2 for a share of them; below half a crown
// the twigs show again
function drawTree(T, { ink, inkK = 1, bark, keep = 1, m = null, m2 = null, share = 0 }){
  // per leaf only two dot products (facing and light) and its side of the trunk, against rows worked out once per tree
  const rw = camRows(), vw = visRow(), lw = litRow(), V = CAM_V, groups = [new Map(), new Map()];
  for (const lf of T.leaves){ if (lf.k >= keep) continue;
    const n = lf.n, d0 = n[0]*lw[0] + n[1]*lw[1] + n[2]*lw[2], d = n[0]*vw[0] + n[1]*vw[1] + n[2]*vw[2] > 1e-6 ? d0 : -d0;
    const tk = d > -.15 ? 'l' : d > -.45 ? 'm' : 'd';
    const g = groups[!PHONE && (lf.c[0] - T.x)*V[0] + (lf.c[1] - T.y)*V[1] > 0 ? 1 : 0];   // in front of the trunk at the leaf's own height (a phone keeps one group: too small to tell)
    const lm = m2 && lf.j < share ? m2 : m || lf.m; let e = g.get(lm); if (!e) g.set(lm, e = { d: '', m: '', l: '' });
    e[tk] += pdR(rw, lf.pts); }
  const leafSVG = g => { let s = ''; for (const [m, e] of g) for (const k of ['d', 'm', 'l']) if (e[k]) s += `<path d="${e[k]}" fill="${m[k]}" stroke="${ink}" stroke-width=".3" stroke-linejoin="round"/>`; return s; };
  // wood as round-capped strokes with a slightly darker edge, all pieces of one thickness in one path, thickest first
  const byR = new Map();
  // (pieces are grouped as trunk, limbs, twigs, each drawn at its group's mean thickness: far fewer elements per tree)
  const segs = keep < .5 ? T.segs.concat(T.twigs) : T.segs, rMax = Math.max(...segs.map(s => s[2]));
  const grp = new Map(); for (const [a, b, r] of segs){ const k = r >= rMax*.99 ? 0 : r > rMax*.3 ? 1 : 2; const g = grp.get(k) || { d: '', rs: 0, n: 0 }; g.d += pd([a, b], false); g.rs += r; g.n++; grp.set(k, g); }
  for (const g of grp.values()) byR.set(g.rs / g.n, g.d);
  let br = ''; const edgeC = mix(bark, '#24182a', .45);
  for (const r of [...byR.keys()].sort((p, q) => q - p)){ const d = byR.get(r), W = 2*r*CAM_K;
    br += `<path d="${d}" fill="none" stroke="${edgeC}" style="stroke-width:${(W + .5*inkK).toFixed(2)}" stroke-linecap="round"/>`
        + `<path d="${d}" fill="none" stroke="${bark}" style="stroke-width:${W.toFixed(2)}" stroke-linecap="round"/>`; }
  let backing='';
  if(keep>=.5){
    const center=P(T.x,T.y,T.zc), bins=new Array(20).fill(null);
    for(const leaf of T.leaves)if(leaf.k<keep)for(const pt of leaf.pts){
      const q=P(...pt), dx=q[0]-center[0],dy=q[1]-center[1],r=dx*dx+dy*dy;
      const i=Math.min(19,Math.floor((Math.atan2(dy,dx)+Math.PI)/(2*Math.PI)*20));
      if(!bins[i]||bins[i].r<r)bins[i]={q,r};
    }
    const rim=bins.filter(Boolean).map(b=>b.q), pigment=m || T.leaves[0].m;
    if(rim.length>3){
      const path=rim.map(([x,y],i)=>{
        const p=rim[(i+rim.length-1)%rim.length];
        return (i?'L':'M')+f((p[0]+x)*.46+center[0]*.08)+' '+f((p[1]+y)*.46+center[1]*.08)+'L'+f(x)+' '+f(y);
      }).join('')+'Z';
      backing=`<path d="${path}" fill="${pigment.m}" stroke="${ink}" stroke-width=".55"/>`;
    }
  }
  return br + backing + leafSVG(groups[0]) + leafSVG(groups[1]);   // wood first: the crown covers its limbs, only the trunk below shows
}

/* Pocket City vehicles, shared by both cities: cars at their real sizes, and Amsterdam's canal boats.
   A vehicle is a mesh built once in its own frame (x forward, y left, z up, origin on the ground or water under its
   middle): a few convex solids drawn in layers, each solid's visible faces in the three soft tones, then the details
   that lie on those faces (windows, lights, wheels, plates). A frame only turns and projects it.
   Needs core3d.js (shape, line, tone, vis, depthOf, P, pd, norm, cross, dot, sub, avg, mix, INK). */
const V_GLASS = { l: '#d3e8f2', m: '#a6c9da', d: '#7fa3b8' }, V_TYRE = { l: '#4c484e', m: '#3a373c', d: '#29272b' };
const V_HUB = { l: '#e6e8ea', m: '#c6cacd', d: '#a0a5aa' }, V_DARK = { l: '#5e5c63', m: '#4a484f', d: '#35333a' };
const V_HEAD = { l: '#fff6d6', m: '#f1e6bd', d: '#d9cc9f' }, V_TAIL = { l: '#c9473c', m: '#b23d34', d: '#8f3029' };
const V_BRAKE = { l: '#ff5a44', m: '#f2493a', d: '#d63b2f' };
const vMat = hex => ({ l: hex, m: mix(hex, '#8a74a8', .16), d: mix(hex, '#54467e', .34) });

const vNewell = pts => { let x = 0, y = 0, z = 0;
  for (let i = 0; i < pts.length; i++){ const a = pts[i], b = pts[(i + 1) % pts.length];
    x += (a[1] - b[1])*(a[2] + b[2]); y += (a[2] - b[2])*(a[0] + b[0]); z += (a[0] - b[0])*(a[1] + b[1]); }
  const l = Math.hypot(x, y, z); return l ? [x/l, y/l, z/l] : null; };
// a convex solid lofted between two rings of equal length; capA, capB, strip(i) give materials (null leaves it open)
function vLoft(A, B, capA, capB, strip, layer = 0){
  const cen = avg(A.concat(B)), S = { faces: [], det: [], layer, cen };
  const add = (pts, m) => { if (!m) return; let n = vNewell(pts); if (!n) return; if (dot(n, sub(avg(pts), cen)) < 0) n = n.map(v => -v); S.faces.push({ pts, n, m }); };
  add(A, capA); add(B, capB);
  for (let i = 0; i < A.length; i++){ const j = (i + 1) % A.length; add([A[i], A[j], B[j], B[i]], strip(i)); }
  return S;
}
const vBox = (x0, x1, y0, y1, z0, z1, m, layer) => { const r = z => [[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z]]; return vLoft(r(z0), r(z1), m, m, () => m, layer); };
// a detail lying on a face of solid S: out is roughly its outward direction; line: an open stroke; both: seen from either side
const vDet = (S, pts, m, out, o = {}) => { let n = o.line ? out : vNewell(pts); if (dot(n, out) < 0) n = n.map(v => -v); S.det.push({ pts, n, m, ...o }); };
const vRing = (cx, cz, r, n, y, a0 = 0, a1 = Math.PI*2) => Array.from({ length: n }, (_, i) => { const a = a0 + (a1 - a0)*i/(a1 === Math.PI*2 ? n : n - 1); return [cx + Math.cos(a)*r, y, cz + Math.sin(a)*r]; });

/* ---------- cars ----------
   Sizes are real (length, width, height, wheelbase, wheel radius in metres); hood, windscreen, roof and rear-glass runs
   shape the side view, whatever is left behind is the boot. win: side windows as shares of the glasshouse. */
const CAR_TYPES = {
  small:  { L: 3.60, W: 1.65, H: 1.50, hood: .70, ws: .70, roof: 1.50, rg: .50, belt: .98, nose: .80, tail: .96, wb: 2.42, r: .30, zb: .17, win: [[0, .5], [.55, 1]] },
  hatch:  { L: 4.28, W: 1.79, H: 1.46, hood: 1.05, ws: .75, roof: 1.75, rg: .55, belt: .98, nose: .80, tail: .96, wb: 2.63, r: .32, zb: .16, win: [[0, .4], [.45, .78], [.82, 1]] },
  sedan:  { L: 4.67, W: 1.81, H: 1.46, hood: 1.15, ws: .80, roof: 1.30, rg: .65, belt: .98, nose: .80, tail: .95, wb: 2.70, r: .32, zb: .16, win: [[0, .47], [.52, 1]] },
  estate: { L: 4.77, W: 1.83, H: 1.50, hood: 1.10, ws: .80, roof: 2.15, rg: .45, belt: .98, nose: .80, tail: .97, wb: 2.79, r: .32, zb: .16, win: [[0, .36], [.4, .7], [.74, 1]] },
  suv:    { L: 4.60, W: 1.86, H: 1.68, hood: 1.00, ws: .65, roof: 2.25, rg: .35, belt: 1.10, nose: .98, tail: 1.08, wb: 2.70, r: .37, zb: .24, win: [[0, .4], [.45, .78], [.82, 1]] },
  mpv:    { L: 5.20, W: 1.88, H: 1.78, hood: .95, ws: .85, roof: 2.95, rg: .25, belt: 1.05, nose: .95, tail: 1.03, wb: 3.09, r: .35, zb: .2, win: [[0, .3], [.34, .66], [.7, 1]] },
  van:    { L: 4.50, W: 1.80, H: 1.85, hood: .75, ws: .70, roof: 2.85, rg: .06, belt: 1.05, nose: .98, tail: 1.03, wb: 2.68, r: .33, zb: .2, win: [[0, .27]] },
};
// makeCar(type, { plate, sign }): plate is the number-plate colour (a city's), sign a roof-light colour for a taxi
function makeCar(type, { plate = '#f2f2ee', frontPlate = plate, sign = null } = {}){
  const T = CAR_TYPES[type] || CAR_TYPES.hatch, { L, W, H, belt, nose, tail, r, zb } = T, hw = W/2;
  const xN = L/2, xT = -L/2, xC = xN - T.hood, xRF = xC - T.ws, xRR = xRF - T.roof, xRG = xRR - T.rg;
  // the lower body: a side profile pushed out to the full width
  const prof = [[xT + .1, zb], [xN - .15, zb], [xN, zb + .18], [xN, nose - .1], [xN - .18, nose], [xC, belt], [xRG, belt], [xT + .08, tail], [xT, tail - .12], [xT, zb + .15]];
  const side = y => prof.map(([x, z]) => [x, y, z]);
  const body = vLoft(side(hw), side(-hw), 'paint', 'paint', () => 'paint', 0);
  // the glasshouse narrows toward the roof (tumblehome): windscreen, roof, rear glass
  const wb = hw - .04, wt = hw - .2, gh = y => [[xC, y*wb, belt], [xRF, y*wt, H], [xRR, y*wt, H], [xRG, y*wb, belt]];
  const glass = vLoft(gh(1), gh(-1), 'paint', 'paint', i => i === 0 || i === 2 ? 'glass' : 'paint', 1);
  const mesh = { solids: [body, glass], L, W, H };
  const ox = (L - T.wb)*.48, xf = xN - ox, xr = xf - T.wb;
  for (const s of [1, -1]){
    const y = s*(hw + .004), out = [0, s, 0];
    // side windows on the slanted glasshouse side, split by the pillars
    const B0 = [xC - .14, belt + .05], B1 = [xRG + .1, belt + .05], T0 = [xRF - .06, H - .07], T1 = [xRR + .06, H - .07];
    const at = ([x, z]) => [x, s*(wb + (wt - wb)*(z - belt)/(H - belt) + .004), z], lp = (a, b, k) => [a[0] + (b[0] - a[0])*k, a[1] + (b[1] - a[1])*k];
    for (const [a, b] of T.win) vDet(glass, [lp(B0, B1, a), lp(T0, T1, a), lp(T0, T1, b), lp(B0, B1, b)].map(at), 'glass', [0, s, .3]);
    // door shut lines, wheel arches, tyres and hubs
    const doors = [xC - .04, ...T.win.slice(0, -1).map(([, b], i) => xC + (xRG - xC)*((b + T.win[i + 1][0])/2))];
    for (const x of doors.slice(0, type === 'van' ? 1 : 3)) vDet(body, [[x, y, zb + .1], [x, y, belt - .02]], 'line', out, { line: true });
    for (const x of [xf, xr]){
      const R = r + .07, arc = vRing(x, r, R, 9, y, 0, Math.PI);
      vDet(body, [[x + R, y, zb], ...arc, [x - R, y, zb]], 'arch', out);
      vDet(body, vRing(x, r, r, 14, y + s*.01), 'tyre', out);
      vDet(body, vRing(x, r, r*.56, 10, y + s*.02), 'hub', out); }
  }
  // front: headlights and a grille; back: tail lights and the plate
  const fq = (y0, y1, z0, z1, x) => [[x, y0, z0], [x, y1, z0], [x, y1, z1], [x, y0, z1]];
  for (const s of [1, -1]){
    vDet(body, fq(s*(hw - .12), s*(hw - .46), nose - .26, nose - .13, xN + .004), 'head', [1, 0, 0]);
    vDet(body, fq(s*(hw - .08), s*(hw - .4), tail - .36, tail - .2, xT - .004), 'tail', [-1, 0, 0]); }
  vDet(body, fq(-.36, .36, zb + .26, nose - .3, xN + .004), 'dark', [1, 0, 0]);
  vDet(body, fq(-.26, .26, zb + .3, zb + .42, xT - .004), vMat(plate), [-1, 0, 0]);
  vDet(body, fq(-.22, .22, zb + .25, zb + .36, xN + .006), vMat(frontPlate), [1, 0, 0]);
  if (sign){ const xm = (xRF + xRR)/2 + .1; mesh.solids.push(vBox(xm - .16, xm + .16, -.32, .32, H, H + .17, vMat(sign), 2)); }
  return mesh;
}

/* ---------- boats ----------
   sloop: an open salon boat, about 6.8 m, with cushions round a table, people aboard and the Dutch flag at the stern.
   tour: a canal tour boat (rondvaartboot), about 19 m, low hull, a long glass cabin with a rounded glass roof. */
function vHullRing(L, w, z, k = 1, bow = 2){   // plan outline: a square-ish stern, straight sides, a rounded bow to a point
  const r = [[-L/2, -w*.82*k, z], [-L/2 + .5, -w*k, z], [L/2 - bow, -w*k, z]];
  for (let i = 1; i < 6; i++){ const a = i/6*Math.PI/2; r.push([L/2 - bow + bow*Math.sin(a), -w*k*Math.cos(a), z]); }
  r.push([L/2, 0, z]);
  for (let i = 5; i > 0; i--){ const a = i/6*Math.PI/2; r.push([L/2 - bow + bow*Math.sin(a), w*k*Math.cos(a), z]); }
  r.push([L/2 - bow, w*k, z], [-L/2 + .5, w*k, z], [-L/2, w*.82*k, z]);
  return r;
}
const vInset = (ring, d) => { const c = avg(ring); return ring.map(p => { const v = [p[0] - c[0], p[1] - c[1]], l = Math.hypot(v[0], v[1]) || 1; return [p[0] - v[0]/l*d, p[1] - v[1]/l*d, p[2] + .002]; }); };
function vFlag(mesh, x, z){   // the Dutch flag on a short staff, flying aft
  const S = { faces: [], det: [], layer: 3, cen: [x, 0, z + .8] };
  vDet(S, [[x, 0, z], [x, 0, z + 1.2]], 'line', [0, 0, 1], { line: true, both: true });
  [['#d9473c', 1.08], ['#fbf8f0', .96], ['#2f5fa8', .84]].forEach(([c, zt]) =>
    vDet(S, [[x, 0, z + zt], [x - .62, 0, z + zt - .02], [x - .62, 0, z + zt - .14], [x, 0, z + zt - .12]], vMat(c), [0, 1, 0], { both: true }));
  mesh.solids.push(S);
}
// makeBoat(kind, { hull, people: [{ shirt, skin }] }): hull is the hull colour {l, m, d}
function makeBoat(kind, { hull, people = [] } = {}){
  const tour = kind === 'tour', L = tour ? 19 : 6.8, w = tour ? 2.0 : 1.05, fb = tour ? .45 : .55, mesh = { solids: [], L, W: 2*w, H: tour ? 2 : 1.2 };
  // the hull: below the rubbing strake in the hull colour, a band above it in wood or white
  const bow = tour ? 2.6 : 2.0, band = tour ? vMat('#f4efe4') : vMat('#b07a4e');
  const k0 = vHullRing(L, w, -.06, .9, bow), k1 = vHullRing(L, w, fb - .2, 1, bow), k2 = vHullRing(L, w, fb, 1.01, bow);
  mesh.solids.push(vLoft(k0, k1, null, null, () => hull, 0), vLoft(k1, k2, null, tour ? vMat('#ece6da') : band, () => band, 0));
  const top = mesh.solids[1];
  top.smooth=true;mesh.solids[0].smooth=true;
  if (!tour){
    const teak=vMat('#cb9568'),ivory=vMat('#efe0bf'),denim=vMat('#455672'),up=[0,0,1];
    const deck=vInset(k2,.13);
    vDet(top,deck,teak,up);
    // Laid foredeck planks stop at the sheer. The inner coaming encloses a separate, darker cockpit.
    for(let y=-.8;y<=.81;y+=.16){
      const x=1.34+bow*Math.sqrt(Math.max(0,1-(y/.96)**2))-.13;
      vDet(top,[[1.38,y,fb+.009],[x,y,fb+.009]],'line',up,{line:true});
    }
    const well=[[-2.92,-.68],[-2.71,-.86],[.83,-.86],[1.30,-.66],[1.44,-.32],[1.44,.32],[1.30,.66],[.83,.86],[-2.71,.86],[-2.92,.68]];
    vDet(top,well.map(([x,y])=>[x,y,fb+.012]),vMat('#684f4a'),up);
    vDet(top,well.map(([x,y])=>[x*.96,y*.91,fb+.014]),vMat('#a57f60'),up);
    for(let j=-3;j<=3;j++){
      const y=j*.17;vDet(top,[[-2.68,y,fb+.017],[1.16,y,fb+.017]],'line',up,{line:true,ink:'#896652',width:.014});
    }
    const table=vBox(-1.27,-.52,-.22,.22,fb+.11,fb+.18,vMat('#bb8964'),1);
    mesh.solids.push(table);
    for(const side of [-1,1]){
      mesh.solids.push(vBox(-2.52,.91,side*.67-.12,side*.67+.12,fb+.02,fb+.10,ivory,1));
      const rail=mesh.solids[0],out=[0,side,0];
      vDet(rail,[[-2.83,side*1.008,.22],[1.35,side*1.008,.22],[1.35,side*1.011,.27],[-2.83,side*1.011,.27]],ivory,out);
    }
    mesh.solids.push(vBox(-2.85,-2.48,-.64,.64,fb+.018,fb+.105,vMat('#698582'),1));
    // Cleats and a small coiled painter give the bow a readable working scale.
    for(const x of [-3.01,2.48])mesh.solids.push(vBox(x-.115,x+.115,-.032,.032,fb+.018,fb+.096,vMat('#607271'),1));
    for(let i=0;i<3;i++){
      const rope=Array.from({length:17},(_,k)=>{const a=k*Math.PI/8;return [1.87+(.21-i*.034)*Math.cos(a),.22+(.15-i*.024)*Math.sin(a),fb+.023]});
      vDet(top,rope,'line',up,{line:true,ink:'#e4c596',width:.023});
    }
    const places=[[-2.61,.04],[-1.83,.67],[-1.20,-.67],[-.52,.67],[.26,-.67],[.53,.60],[-2.08,-.64],[1.06,-.32]];
    people.slice(0,places.length).forEach(({shirt,skin},i)=>{
      const [cx,cy]=places[i],angle=i===0?.12:Math.atan2(-cy,.18+.42*Math.sin(i*1.7)),cs=Math.cos(angle),sn=Math.sin(angle);
      const at=(u,v,h)=>[cx+cs*u-sn*v,cy+sn*u+cs*v,fb+h];
      const section=(u,v,h,rx,ry)=>Array.from({length:8},(_,j)=>{const a=j*Math.PI/4;return at(u+rx*Math.cos(a),v+ry*Math.sin(a),h)});
      const body=(a,b,m)=>{
        const solid=vLoft(section(...a),section(...b),null,m,()=>m,2);
        solid.smooth=true;mesh.solids.push(solid);
      };
      const clothes=vMat(shirt),hair=vMat(['#56413b','#896549','#6a5047','#51423e'][i%4]);
      body([.12,0,.065,.17,.165],[.135,0,.20,.21,.17],denim);
      body([.02,0,.17,.125,.152],[-.013,0,.52,.105,.204],clothes);
      body([-.013,0,.52,.106,.205],[.015,0,.60,.068,.091],clothes);
      for(const sd of [-1,1]){
        body([.073,sd*.201,.30,.063,.058],[-.004,sd*.177,.51,.077,.072],clothes);
        body([.09,sd*.20,.30,.065,.059],[.207,sd*.164,.274,.066,.054],skin);
      }
      if(i%3===1)body([-.008,0,.528,.113,.177],[.008,0,.566,.098,.135],vMat('#e8cb9f'));
      body([.016,0,.59,.071,.064],[.034,0,.74,.126,.115],skin);
      body([.034,0,.74,.127,.116],[.016,0,.829,.098,.101],hair);
      body([.016,0,.829,.098,.101],[.008,0,.852,.052,.063],hair);
      if(i%4===0){
        const cap=vMat('#526d78');
        body([.065,0,.772,.185,.12],[.055,0,.789,.158,.115],cap);
        body([.015,0,.786,.119,.117],[.010,0,.861,.068,.071],cap);
      }
    });
    vFlag(mesh,-L/2+.08,fb);

  } else {
    // the cabin: a cross-section (wall band, side glass, rounded glass roof) run along most of the boat
    const wc = w - .32, x0 = -L/2 + 1.6, x1 = L/2 - 2.6, zd = fb;
    const sec = x => [[x, wc, zd], [x, wc, zd + .5], [x, wc - .06, zd + 1.12], [x, wc - .5, zd + 1.42], [x, 0, zd + 1.55], [x, -wc + .5, zd + 1.42], [x, -wc + .06, zd + 1.12], [x, -wc, zd + .5], [x, -wc, zd]];
    const mats = ['wall', 'glass', 'glass', 'glass', 'glass', 'glass', 'glass', 'wall', null];
    const cab = vLoft(sec(x0), sec(x1), 'wall', 'glass', i => mats[i] === 'wall' ? vMat('#f4efe4') : mats[i] === 'glass' ? 'glass' : null, 1);
    cab.faces.forEach(f => { if (f.m === 'wall') f.m = vMat('#f4efe4'); });
    mesh.solids.push(cab);
    // window frames: thin lines across the glass every 1.3 m, and a wall band at the bow end
    for (let x = x0 + 1.3; x < x1 - .3; x += 1.3){ const S = sec(x);
      for (const s of [1, -1]) vDet(cab, s > 0 ? S.slice(1, 5) : S.slice(4, 8), 'frame', [0, s, .5], { line: true }); }
    vDet(cab, [[x1 + .004, wc, zd], [x1 + .004, -wc, zd], [x1 + .004, -wc, zd + .5], [x1 + .004, wc, zd + .5]], vMat('#f4efe4'), [1, 0, 0]);
    vFlag(mesh, -L/2 + .1, fb);
  }
  return mesh;
}

/* ---------- drawing ---------- */
const vClip = (pts, lo, hi, open) => {   // keep the part of a polygon (or an open line) with lo <= x <= hi
  const cut = (P0, keep, xv) => { const out = [], n = P0.length;
    for (let i = 0; i < (open ? n - 1 : n); i++){ const a = P0[i], b = P0[(i + 1) % n], ia = keep(a[0]), ib = keep(b[0]);
      if (ia) out.push(a); if (ia !== ib){ const k = (xv - a[0])/(b[0] - a[0]); out.push([xv, a[1] + (b[1] - a[1])*k, a[2] + (b[2] - a[2])*k]); } }
    if (open && keep(P0[n - 1][0])) out.push(P0[n - 1]); return out; };
  let r = pts; if (lo > -1e8) r = cut(r, x => x >= lo, lo); if (r.length && hi < 1e8) r = cut(r, x => x <= hi, hi); return r; };
// drawVehicle(mesh, { c, d, z, mats, lo, hi, w }): c the centre on the ground, d the unit heading; mats fills in named
// materials ('paint', 'glass', 'tail' ...); lo/hi keep only that stretch along the length (a boat under a bridge)
function drawVehicle(mesh, { c, d, z = 0, mats = {}, lo = -1e9, hi = 1e9, w = .45 }){
  const M = { glass: V_GLASS, tyre: V_TYRE, hub: V_HUB, dark: V_DARK, arch: V_DARK, head: V_HEAD, tail: V_TAIL, ...mats };
  const W3 = p => [c[0] + d[0]*p[0] - d[1]*p[1], c[1] + d[1]*p[0] + d[0]*p[1], z + p[2]], WN = n => [d[0]*n[0] - d[1]*n[1], d[1]*n[0] + d[0]*n[1], n[2]];
  const mat = m => typeof m === 'string' ? M[m] : m;
  const sol = mesh.solids.map(S => ({ S, dep: depthOf(W3(S.cen)) })).sort((a, b) => a.S.layer - b.S.layer || a.dep - b.dep);
  let s = '';
  for (const { S } of sol){
    if (S.ball){ const [x, y, zz, r] = S.ball; if (x < lo || x > hi) continue; const [X, Y] = P(...W3([x, y, zz])), R = r*CAM_K;
      s += `<circle cx="${f(X)}" cy="${f(Y)}" r="${f(R)}" fill="${S.m.l}" stroke="${INK}" stroke-width="${w}"/>`; continue; }
    for (const F of S.faces){ const n = WN(F.n); if (!vis(n)) continue;
      const q = vClip(F.pts, lo, hi); if (q.length > 2) s += shape(q.map(W3), tone(n, mat(F.m)), S.smooth ? 0 : w); }
    for (const D of S.det){ const n = WN(D.n); if (!D.both && !vis(n)) continue;
      const q = vClip(D.pts, lo, hi, D.line); if (q.length < 2) continue;
      if(D.line && D.ink)s+='<path d="'+pd(q.map(W3),false)+'" fill="none" stroke="'+D.ink+'" style="stroke-width:'+D.width*CAM_K+'"/>';
      else if (D.line) s += line(q.map(W3), D.m === 'frame' ? w*.8 : w*.7);
      else if (q.length > 2) s += shape(q.map(W3), tone(vis(n) ? n : n.map(v => -v), mat(D.m)), w*.7); }
  }
  return s;
}

/* Pocket City seasons, shared by both cities: the season state, snow colours, the weather particles and the selector bar.
   Each city lists its own states (four seasons plus its special days) with what changes and a one-line note that says
   only what a named source says (research in seasons/RESEARCH.md); the city's setSeason(id) applies one. A state can:
   - restyle the trees (leaves kept, their colour) and the ground (snow, wet streets, ice),
   - change how many people, bikes and boats are about,
   - add weather drawn over the scene (rain, drizzle, snow, plane-tree fluff),
   - tint the finished picture (grey winter light, haze), as a CSS filter on the page, so it costs the frame builders nothing.
   Needs core3d.js (P, f, mix, INK_K) and trees.js (PHONE). Runs in the page and again in each frame worker (a data-scene script). */
const SEASON_Q = new URLSearchParams(self.PAGE_SEARCH ?? location.search).get('season');
let SEASON_ID = null;
// the meteorological season of a date (northern hemisphere: Dec–Feb winter, Mar–May spring, …)
const seasonOfDate = (d = new Date()) => ['winter', 'winter', 'spring', 'spring', 'spring', 'summer', 'summer', 'summer', 'autumn', 'autumn', 'autumn', 'winter'][d.getMonth()];
// snow over a surface: k of the way to snow white
const snowy = (hex, k = .85) => mix(hex, '#f6f8fb', k);
const SNOW = { l: '#f6f8fb', m: '#e2e8f2', d: '#c3cbdd' };
// weather over the plate, in world space so it turns with the camera; every kind is one path.
// rain and drizzle: short streaks slanting with the wind; snow and fluff: round dots that drift as they fall.
// Paths are in metres; widths (w) are in ink units, so a flake stays the same size on screen at any zoom
const WX = {
  rain:    { n: 320, v: 12, len: 2.4, w: .85, col: '#5f7bb0', op: .6, top: 30 },
  drizzle: { n: 420, v: 7,  len: 1.8, w: .7,  col: '#6a82b4', op: .55, top: 26 },
  snow:    { n: 320, v: 1.1, w: 3,   col: '#ffffff', op: .95, top: 30, drift: .9, edge: '#9aa7c4' },
  heavysnow: { n: 980, v: 1.35, w: 3.5, col: '#ffffff', op: .95, top: 30, drift: 1.25, edge: '#9aa7c4' },
  fluff:   { n: 80,  v: .45, w: 3.2, col: '#fbf3dc', op: .9,  top: 14, drift: 1.6, edge: '#c9b98e' },
};
function weather(kind, t, half, zAt = () => 0, contains = null){
  const W = WX[kind]; if (!W) return '';
  const h = (i, k) => { const x = Math.sin(i*127.1 + k*311.7) * 43758.5453; return x - Math.floor(x); };
  let d = '';
  const N = PHONE ? Math.round(W.n * .6) : W.n;   // fewer on a phone's small screen
  for (let i = 0; i < N; i++){
    let x = (h(i, 1) - .5) * 2 * half, y = (h(i, 2) - .5) * 2 * half;
    if(contains && !contains(x,y))continue;
    const z0 = zAt(x, y), span = W.top - z0, z = z0 + span - ((t * W.v * (.8 + h(i, 3)*.4) + h(i, 4) * span) % span);
    if (W.drift){ const ph = t * .7 + h(i, 5) * 6.3; x += Math.sin(ph) * W.drift; y += Math.cos(ph * .8) * W.drift * .6; }
    const [X, Y] = P(x, y, z);
    if (W.len){ const [X2, Y2] = P(x + W.len*.12, y + W.len*.08, z - W.len); d += `M${f(X)} ${f(Y)}L${f(X2)} ${f(Y2)}`; }
    else d += `M${f(X)} ${f(Y)}h0`;
  }
  const w = W.w * INK_K;
  return (W.edge ? `<path d="${d}" fill="none" stroke="${W.edge}" stroke-opacity=".55" style="stroke-width:${(w + .35*INK_K).toFixed(2)}" stroke-linecap="round"/>` : '')
    + `<path d="${d}" fill="none" stroke="${W.col}" stroke-opacity="${W.op}" style="stroke-width:${w.toFixed(2)}" stroke-linecap="round"/>`;
}
// Space-time reservations include actual vehicle dimensions and the entire swept turn.
// A new trip is admitted at the edge once its passage is clear, including the exit
// from a junction. All street users share this ledger. Rendering only samples admitted trips.
function measuredLane(record){
  const pts=record.p.filter((q,i,a)=>!i||Math.hypot(q[0]-a[i-1][0],q[1]-a[i-1][1])>.006);
  const cum=[0],directions=[];
  for(let i=1;i<pts.length;i++){
    const dx=pts[i][0]-pts[i-1][0],dy=pts[i][1]-pts[i-1][1],l=Math.hypot(dx,dy);
    directions.push([dx/l,dy/l]);cum.push(cum[i-1]+l);
  }
  const tangent=pts.map((p,i)=>{
    const a=directions[Math.max(0,i-1)],b=directions[Math.min(i,directions.length-1)],l=Math.hypot(a[0]+b[0],a[1]+b[1]);
    return l>.01?[(a[0]+b[0])/l,(a[1]+b[1])/l]:b;
  });
  return {pts,cum,tangent,len:cum[cum.length-1],ends:[true,true],off:0,ways:record.ways||[],junctions:record.junctions};
}
function laneSegment(path,s){
  let lo=0,hi=path.cum.length-1;
  while(hi-lo>1){const m=(hi+lo)>>1;if(path.cum[m]<=s)lo=m;else hi=m}return lo;
}
function tAt(path,s){
  const i=laneSegment(path,s),a=path.pts[i],b=path.pts[i+1],u=path.tangent[i],v=path.tangent[i+1];
  const f=Math.max(0,Math.min(1,(s-path.cum[i])/(path.cum[i+1]-path.cum[i]))),dx=u[0]+(v[0]-u[0])*f,dy=u[1]+(v[1]-u[1])*f,l=Math.hypot(dx,dy)||1;
  return {p:[a[0]+(b[0]-a[0])*f,a[1]+(b[1]-a[1])*f],d:[dx/l,dy/l],off:0};
}
const TRAFFIC_DT=.5;
function sweptBody(path,s0,s1,halfL,halfW){
  const a=tAt(path,s0),b=tAt(path,s1),axis=tAt(path,(s0+s1)/2).d;
  const samples=[a];for(let i=laneSegment(path,s0)+1;path.cum[i]<s1;i++)samples.push({p:path.pts[i],d:path.tangent[i]});samples.push(b);
  let minX=Infinity,minY=Infinity,maxX=-Infinity,maxY=-Infinity;
  for(let i=1;i<samples.length;i++){
    const A=samples[i-1],B=samples[i],cos=Math.max(-1,Math.min(1,A.d[0]*B.d[0]+A.d[1]*B.d[1]));
    // During rotation each corner stays within this distance of the chord between its end poses.
    const margin=Math.hypot(halfL,halfW)*(1-Math.sqrt((1+cos)/2))+.025;
    for(const q of [A,B]){
      const x=q.p[0]*axis[0]+q.p[1]*axis[1],y=-q.p[0]*axis[1]+q.p[1]*axis[0];
      const c=Math.abs(q.d[0]*axis[0]+q.d[1]*axis[1]),s=Math.abs(q.d[1]*axis[0]-q.d[0]*axis[1]);
      const rx=halfL*c+halfW*s+margin,ry=halfL*s+halfW*c+margin;
      minX=Math.min(minX,x-rx);maxX=Math.max(maxX,x+rx);minY=Math.min(minY,y-ry);maxY=Math.max(maxY,y+ry);
    }
  }
  const x=(minX+maxX)/2,y=(minY+maxY)/2,l=(maxX-minX)/2,w=(maxY-minY)/2;
  return {x:x*axis[0]-y*axis[1],y:x*axis[1]+y*axis[0],u:axis[0],v:axis[1],l,w,r:Math.hypot(l,w)};
}
function conflict(a,b){
  const dx=a.x-b.x,dy=a.y-b.y,r=a.r+b.r;if(dx*dx+dy*dy>=r*r)return false;
  const c=Math.abs(a.u*b.u+a.v*b.v),s=Math.abs(a.u*b.v-a.v*b.u);
  return Math.abs(dx*a.u+dy*a.v)<a.l+b.l*c+b.w*s && Math.abs(-dx*a.v+dy*a.u)<a.w+b.l*s+b.w*c &&
    Math.abs(dx*b.u+dy*b.v)<b.l+a.l*c+a.w*s && Math.abs(-dx*b.v+dy*b.u)<b.w+a.l*s+a.w*c;
}
// Spatial filing for the traffic ledger: a box goes in every 6 m cell its bounding circle covers.
const GRID_CELL=6;
function gridSpan(b,f){
  const x0=Math.floor((b.x-b.r)/GRID_CELL),x1=Math.floor((b.x+b.r)/GRID_CELL),y0=Math.floor((b.y-b.r)/GRID_CELL),y1=Math.floor((b.y+b.r)/GRID_CELL);
  for(let x=x0;x<=x1;x++)for(let y=y0;y<=y1;y++)if(f(x*4096+y))return true;
  return false;
}
function gridAdd(row,b){gridSpan(b,k=>{const c=row.get(k);if(c)c.push(b);else row.set(k,[b])})}
function gridHit(row,b){return gridSpan(b,k=>{const c=row.get(k);return !!c&&c.some(o=>conflict(b,o))})}
function streetSimulation(feeds,capacity,warmup=120){
  const ledger=new Map();let active=[],tick=-warmup-1,serial=0;
  function reset(){
    tick=-warmup-1;serial=0;active=[];ledger.clear();
    feeds.forEach((f,i)=>{f.next=-warmup+Math.floor(rnd(i*11.4+3)*f.interval/TRAFFIC_DT);f.attempt=0;f.visit=0});
  }
  function book(actor,start,speed,stopAt=-1,wait=0){
    const {path,kind,shape}=actor,steps=[0],boxes=[];let s=0,v=speed,remaining=wait,halted=stopAt<0;
    while(s<path.len){
      const a=tAt(path,s),ahead=tAt(path,Math.min(path.len,s+3.6));
      const bend=Math.max(0,1-a.d[0]*ahead.d[0]-a.d[1]*ahead.d[1]);
      let target=kind==='ped'?speed:speed/(1+2.6*Math.sqrt(bend));
      const stop=path.lightAt===undefined?null:path.lightAt-shape[0]-.2;
      const red=stop!==null&&s<=stop+.0001&&!path.green((start+boxes.length)*TRAFFIC_DT);
      if(red)target=Math.min(target,Math.sqrt(3.2*Math.max(0,stop-s)));
      if(!halted){if(s>=stopAt-.015){target=0;if(--remaining<=0)halted=true}
        else target=Math.min(target,Math.sqrt(3.2*(stopAt-s)))}
      v+=Math.min(1.35*TRAFFIC_DT,Math.max(-2.8*TRAFFIC_DT,target-v));
      let end=Math.min(path.len,s+v*TRAFFIC_DT);if(!halted)end=Math.min(stopAt,end);
      if(red)end=Math.min(end,stop);
      const body=sweptBody(path,s,end,shape[0],shape[1]),slot=start+boxes.length,row=ledger.get(slot);
      if(row && gridHit(row,body))return {blocked:s};
      boxes.push(body);steps.push(end);s=end;
    }
    for(let i=0;i<boxes.length;i++){const time=start+i;let row=ledger.get(time);if(!row)ledger.set(time,row=new Map());gridAdd(row,boxes[i])}
    active.push({...actor,steps,start,end:start+boxes.length});return {ok:true};
  }
  function enter(feed,index){
    const i=feed.visit+feed.attempt,roll=rnd(index*37.4+i*17.3+.72);
    const path=feed.paths[Math.min(feed.paths.length-1,Math.floor(roll*feed.paths.length))],kind=feed.kind,id=serial++;
    const pace=rnd(id*3.9+.42);
    // Metres per second on open road. Even the slower conflict-retry pace for
    // a car clears the bicycle range before cornering or yielding is applied.
    const cruise=kind==='car'?6.5+1.2*pace:kind==='bike'?3.15+.85*pace:(feed.walkSpeed??1.20*(.82+.32*pace));
    const m=kind==='car'?carModel(id):null;
    const shape=m?[m.L/2+.36,m.W/2+.09]:kind==='bike'?[1.11,.39]:[.39,.35];
    const props=kind==='car'?carProps(id):kind==='bike'?bikeLook(id):pedDressed(id);
    const actor={id,kind,path,shape,...props};
    let attempt=book(actor,tick,cruise);
    if(!attempt.ok && kind!=='ped'){
      // A crossing conflict can be resolved with a brief, bounded yield on the approach.
      const relevant=path.junctions.filter(j=>j<attempt.blocked+7 && j>8 && attempt.blocked-j<15);
      if(relevant.length){
        const stopAt=Math.max(3,Math.min(attempt.blocked-5,relevant.at(-1)-5));
        if(stopAt<attempt.blocked-1)attempt=book(actor,tick,cruise,stopAt,4+id%5);
      }
      if(!attempt.ok && attempt.blocked>7)attempt=book(actor,tick,cruise*.82);
      if(!attempt.ok && SEASON.kings && kind==='bike')attempt=book(actor,tick,1.3+.22*rnd(id+.19));
    }
    if(attempt.ok){feed.visit++;feed.attempt=0;feed.next=tick+Math.ceil(feed.interval*(.65+.72*rnd(id*5.4+.81))/TRAFFIC_DT)}
    else{feed.attempt++;feed.next=tick+3+(feed.attempt+index)%4}
  }
  function advance(){
    tick++;ledger.delete(tick-1);active=active.filter(a=>a.end>tick);
    for(let j=0;j<feeds.length;j++){
      const i=(j+tick+warmup)%feeds.length,f=feeds[i];
      if(f.next<=tick && active.length<capacity)enter(f,i);
    }
  }
  reset();
  return {to(t){
    const dest=Math.floor(t/TRAFFIC_DT+1e-8);if(dest<tick)reset();
    while(tick<dest)advance();
    const fraction=Math.max(0,Math.min(1,t/TRAFFIC_DT-tick));
    return active.map(a=>{
      const i=tick-a.start,s0=a.steps[i],ds=a.steps[i+1]-s0,s=s0+ds*fraction,pose=tAt(a.path,s);
      return {...a,...pose,s,dir:1,walked:s,v:ds/TRAFFIC_DT,alpha:Math.min(1,s/2.2,(a.path.len-s)/2.2)};
    });
  }};
}

// a bike: two wheels standing in the plane of travel, a frame, a rider pedalling
// winter: a muted coat, a bright scarf and, on about six in ten, a woolly hat; the coat also stands in as the shirt
const WINTER_COATS = ['#3c4a63', '#a9805a', '#4b4b55', '#6b6a4a', '#7d3b45', '#2f3b36', '#8a5a44', '#56637a', '#c9b79a'];
const WINTER_SCARVES = ['#d9493a', '#f0b52e', '#3f8f8a', '#efe4cc', '#c9566f', '#e07a3a', '#6d8fc9'];
const WINTER_HATS = ['#d9493a', '#2f3b4f', '#efe4cc', '#f0b52e', '#5d7f6a', '#8c4a6a', '#4a4a55', '#3f8f8a'];
const pick = (list, r) => list[Math.floor(r * list.length) % list.length];
const winterWear = (o, k) => { o.coat = pick(WINTER_COATS, rnd(k*11.3 + .2)); o.shirt = o.coat;
  o.scarf = pick(WINTER_SCARVES, rnd(k*12.7 + .4)); o.hat = rnd(k*13.9 + .6) < .62 ? pick(WINTER_HATS, rnd(k*14.3 + .1)) : null; return o; };
// the top of the head: hair, or a woolly hat (a dome down over the ears, a folded cuff and a pompom)
const headTop = (HX, HY, R, hair, hat) => {
  if (!hat) return `<path d="M${f(HX-R)} ${f(HY+R*.15)}a${f(R)} ${f(R)} 0 0 1 ${f(2*R)} 0Q${f(HX)} ${f(HY-R*.15)} ${f(HX-R)} ${f(HY+R*.15)}Z" fill="${hair}"/>`;
  const r = R*1.07, ink = 'stroke="#24182a" stroke-width=".4" stroke-linejoin="round"';
  return `<path d="M${f(HX-r)} ${f(HY+R*.34)}L${f(HX-r)} ${f(HY+R*.02)}A${f(r)} ${f(R*1.14)} 0 0 1 ${f(HX+r)} ${f(HY+R*.02)}L${f(HX+r)} ${f(HY+R*.34)}Z" fill="${hat}" ${ink}/>`
    + `<path d="M${f(HX-r)} ${f(HY+R*.34)}L${f(HX-r)} ${f(HY+R*.02)}Q${f(HX)} ${f(HY-R*.16)} ${f(HX+r)} ${f(HY+R*.02)}L${f(HX+r)} ${f(HY+R*.34)}Q${f(HX)} ${f(HY+R*.16)} ${f(HX-r)} ${f(HY+R*.34)}Z" fill="${mix(hat, '#ffffff', .16)}" ${ink}/>`
    + `<circle cx="${f(HX)}" cy="${f(HY-R*1.12)}" r="${f(R*.32)}" fill="${mix(hat, '#ffffff', .3)}" ${ink}/>`; };
// a walker's arms and body: a shirt with bare arms, or in winter a long coat, sleeves to the wrist and a scarf
const dressTop = (pst, at, h, bob, lk, arms, d) => {
  if (!lk.coat){
    pst(at(0, arms[0][1], 1.3*h + bob), arms[0][0], .06, lk.skin.l);
    pst(at(0, 0, .86*h + bob), at(0, 0, 1.3*h + bob), .25, lk.shirt);
    pst(at(0, arms[1][1], 1.3*h + bob), arms[1][0], .06, lk.skin.l); return; }
  const arm = ([hand, sd]) => { pst(at(0, sd, 1.3*h + bob), hand, .078, lk.coat); pst(hand, [hand[0], hand[1], hand[2] - .05], .055, lk.skin.l); };
  arm(arms[0]);
  pst(at(0, 0, .6*h + bob), at(0, 0, 1.3*h + bob), .28, lk.coat);
  pst(at(0, 0, 1.27*h + bob), at(0, 0, 1.38*h + bob), .2, lk.scarf);
  if (vis([d[0], d[1], 0])) pst(at(.25, .09, 1.3*h + bob), at(.28, .11, 1.0*h + bob), .06, lk.scarf);
  arm(arms[1]); };
function bikeDraw(o, t){
  const c = o.p, d = o.d, vh = o, n = [-d[1], d[0]], z = groundZ(c[0], c[1]), ph = (o.walked || 0) * 2.1;   // a new bike is drawn once before its first step
  const at=(fw,up,side=0)=>[c[0]+d[0]*fw+n[0]*side,c[1]+d[1]*fw+n[1]*side,z+up];
  let tyres='',spokes='';
  for(const hub of [-.55,.55]){
    tyres+=pd(Array.from({length:16},(_,i)=>{const a=i*Math.PI/8;return at(hub+Math.cos(a)*.34,.34+Math.sin(a)*.34)}));
    if(CAM_K/UPX>5)for(let j=0;j<3;j++){const a=ph+j*Math.PI/3,dx=.31*Math.cos(a),dz=.31*Math.sin(a);
      spokes+=pd([at(hub-dx,.34-dz),at(hub+dx,.34+dz)],false)}
  }
  let s=`<path d="${spokes}" fill="none" stroke="#869597" stroke-opacity=".66" stroke-width=".38"/><path d="${tyres}" fill="none" stroke="#4c4952" stroke-width=".74"/>`;
  const frame=pd([at(-.55,.34),at(-.05,.35),at(.38,.74),at(-.18,.8),at(-.55,.34)],false)+pd([at(-.18,.8),at(-.05,.35)],false)+pd([at(.55,.34),at(.38,.74),at(.42,1.03)],false);
  s+=`<path d="${frame}" fill="none" stroke="${vh.frame}" stroke-width=".85" stroke-linejoin="round"/>`;
  const far=dot([n[0],n[1],0],CAM_V)>0?-1:1;
  function leg(side){
    const a=ph+(side<0?Math.PI:0),k=at(-.02+Math.cos(a)*.14,.65+Math.sin(a)*.10,side*.115);
    const foot=at(-.05+Math.cos(a)*.16,.37+Math.sin(a)*.15,side*.125);
    return pstick(at(-.15,.92,side*.11),k,.067,'#43506b')+pstick(k,foot,.055,'#43506b');
  }
  s+=leg(far)+pstick(at(-.12,.95),at(.045,1.46),.19,vh.shirt)+leg(-far);
  const bar=pd([at(.36,1.04,-.27),at(.43,1.01,0),at(.36,1.04,.27)],false);
  s+=`<path d="${bar}" fill="none" stroke="#626b6b" stroke-width=".67"/>`;
  for(const side of [far,-far]){const elbow=at(.20,1.23,side*.20);
    s+=pstick(at(.03,1.42,side*.14),elbow,.056,vh.shirt)+pstick(elbow,at(.36,1.06,side*.25),.045,'#d8af8c')}
  if (vh.scarf) s += pstick(at(.04, 1.43), at(.06, 1.56), .15, vh.scarf);
  s += ball(at(.07, 1.78), .19, soft('#f2c6a0'), .5);
  const [HX, HY] = P(...at(.07, 1.8)), R = .195*CAM_K;
  s += headTop(HX, HY, R, ['#2b211c', '#5a3a26', '#8a6a4a', '#1f1b22'][vh.k % 4], vh.hat);
  return { fp: [[-1,-1],[1,-1],[1,1],[-1,1]].map(([a, b]) => [c[0] + d[0]*.9*a + n[0]*.25*b, c[1] + d[1]*.9*a + n[1]*.25*b]), z0: z, z1: z + 2, svg: s };
}

// Transparent repeating ink tiles. Their pitch is specified in metres so joints get finer on zoom-out.
const INK_TILE_SIZE=4.8,inkTiles=new Map();
function surfaceTile(style,low){
  const key=style+':'+low;if(inkTiles.has(key))return inkTiles.get(key);
  const size=192,tile=makeSurface(size,size),ctx=tile.getContext('2d');
  const pigments=style==='walk'?['#756579','#fff4ce']:style==='slate'?['#453e57','#f3e4d8']:['#824f53','#ffebbf'];
  
  function block(x,y,w,h,seed){
    const v=rnd(seed+17.13),light=v>.48;
    ctx.fillStyle=pigments[light?1:0];ctx.globalAlpha=(.018+Math.abs(v-.5)*.24)*(style==='walk'?.84:1);
    ctx.fillRect(x+.22,y+.22,w-.44,h-.44);
    ctx.fillStyle=pigments[0];ctx.globalAlpha=style==='walk'?.32:.27;
    ctx.fillRect(x,y,w,.65);ctx.fillRect(x,y,.59,h);
    ctx.fillStyle=pigments[1];ctx.globalAlpha=.35;
    ctx.fillRect(x+.7,y+.7,w*.84,.47);
  }
  if(style==='fishscale'||style==='pantile'){
    const nx=style==='fishscale'?12:14,ny=12,w=size/nx,h=size/ny;
    // Each lower edge overlaps the previous course. Repeat the boundary rows to join the tile seamlessly.
    for(let row=-1;row<=ny;row++)for(let col=-1;col<=nx;col++){
      const j=(row+ny)%ny,i=(col+nx)%nx,seed=j*nx+i;
      const x=(col+(j%2)*.5)*w,y=row*h,lip=(style==='fishscale'?.43:.20)*h;
      const variation=rnd(seed+3);
      ctx.beginPath();ctx.moveTo(x,y+h);ctx.lineTo(x+w,y+h);ctx.lineTo(x+w,y+.06*h);
      ctx.quadraticCurveTo(x+w*.52,y-lip,x,y+.06*h);ctx.closePath();
      ctx.fillStyle=variation>.48?'#fff5d6':'#514956';ctx.globalAlpha=.035+.15*Math.abs(variation-.48);ctx.fill();
      ctx.globalAlpha=.40;ctx.strokeStyle='#665a69';ctx.lineWidth=1.15;
      ctx.beginPath();ctx.moveTo(x+w,y+h*.71);ctx.lineTo(x+w,y+.06*h);
      ctx.quadraticCurveTo(x+w*.52,y-lip,x,y+.06*h);ctx.stroke();
      ctx.globalAlpha=.58;ctx.strokeStyle='#fff1d8';ctx.lineWidth=.98;ctx.beginPath();
      ctx.moveTo(x+w*.08,y+.095*h);ctx.quadraticCurveTo(x+w*.36,y-lip*.48,x+w*.60,y-lip*.35);ctx.stroke();
    }
  }else if(style==='asphalt'){
    // Periodic pigment variation and aggregate, baked once at both sampling densities.
    const pixels=ctx.createImageData(size,size);
    const grids=[4,12].map(n=>Array.from({length:n*n},(_,i)=>rnd(i+n*47)));
    function mottling(x,y,n,grid){
      const u=x*n/size,v=y*n/size,i=Math.floor(u),j=Math.floor(v),fx=u-i,fy=v-j;
      const a=j*n,b=(j+1)%n*n,k=(i+1)%n;
      return (grid[a+i]*(1-fx)+grid[a+k]*fx)*(1-fy)+(grid[b+i]*(1-fx)+grid[b+k]*fx)*fy;
    }
    for(let y=0;y<size;y++)for(let x=0;x<size;x++){
      const i=y*size+x,grain=rnd(i*1.73+9)-.5;
      const v=.46*(mottling(x,y,4,grids[0])-.5)+.32*(mottling(x,y,12,grids[1])-.5)+grain*.84;
      const k=i*4;
      pixels.data[k]=v<0?89:255;pixels.data[k+1]=v<0?82:243;pixels.data[k+2]=v<0?96:217;
      pixels.data[k+3]=Math.round(Math.abs(v)*82);
    }
    ctx.putImageData(pixels,0,0);
  }else if(style==='road'){
    // A staggered pair of perpendicular units makes a seamless two-to-one herringbone repeat.
    const u=6;
    for(let j=-4;j<36;j++)for(let i=-4;i<36;i++){
      const n=((i-j)%4+4)%4;
      if(n===0)block(i*u,j*u,u*2,u,19*((i+32)%32)+43*((j+32)%32));
      if(n===3)block(i*u,j*u,u,u*2,23*((i+32)%32)+47*((j+32)%32));
    }
  }else{
    const rows=style==='walk'?8:style==='park'?24:16,cols=style==='walk'?6:style==='park'?16:12;
    const w=size/cols,h=size/rows;
    for(let j=0;j<rows;j++)for(let i=-1;i<cols;i++)block((i+(j%2)*.5)*w,j*h,w,h,(i+cols)%cols*31+j*41);
  }
  if(low){
    const small=makeSurface(24,24),g=small.getContext('2d');g.imageSmoothingQuality='high';g.drawImage(tile,0,0,24,24);inkTiles.set(key,small);
  }else inkTiles.set(key,tile);
  return inkTiles.get(key);
}
const printPatterns=new Map();
function printPattern(ctx,style,angle,low){
  const key=[style,angle,low].join('/');if(printPatterns.has(key))return printPatterns.get(key);
  const tile=surfaceTile(style,low),pattern=ctx.createPattern(tile,'repeat'),a=angle*Math.PI/180,k=INK_TILE_SIZE/tile.width;
  pattern.setTransform({a:k*Math.cos(a),b:k*Math.sin(a),c:-k*Math.sin(a),d:k*Math.cos(a),e:0,f:0});
  printPatterns.set(key,pattern);return pattern;
}
