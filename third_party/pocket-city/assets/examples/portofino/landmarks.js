/* Portofino landmarks.
   Chiesa di San Martino (Divo Martino), founded 986, present look from late-19th-century works, three naves, rose
   window, striped front (en.wikipedia.org/wiki/Divo_Martino,_Portofino; it.wikipedia Chiesa di San Martino). The
   footprint is OSM w1472631837, drawn as its parts: w204694254 (church) and w200437670 (the 4 m square bell tower at
   the north-east corner). Heights, band widths, the belfry and the dome are read from Wikimedia Commons photographs,
   not from a measured drawing: say so in the field notes.
   Oratorio di Nostra Signora Assunta (OSM w200437978): 14th-century confraternity oratory with a slate portal of 1555
   (it.wikipedia). Drawn as a plain gabled hall with the dark slate portal; its colours are interpreted. */
const SM = 'w1472631837', SM_TOWER = 'w200437670', ORATORIO = 'w200437978';
const SM_YELLOW = '#efd9a0', SM_GREY = '#b4b1aa', SM_CREAM = '#f1e8d2', SLATE = '#8d8a86';

// one face (quad) seen from outside, with its own shade
function face4(q, col, ink = .5) { let n = vNewell(q); return vis(n) ? shape(q, tone(n, soft(col)), ink) : ''; }

function sanMartino() {
  const ax = [0.9919, 0.1267], nx = [-0.1267, 0.9919], F = [-43.99, 60.0];          // front (east) centre, nave axis
  const at = (u, v, z) => [F[0] - ax[0] * u + nx[0] * v, F[1] - ax[1] * u + nx[1] * v, z];
  const LEN = 35.5, HW = 5.95, WALL = 10.5;   // the OSM front between the south corner and the tower is 11.9 m
  const navRing = [at(0, -HW, 0), at(0, HW, 0), at(LEN, HW, 0), at(LEN, -HW, 0)].map(p => [p[0], p[1]]);
  const nave = block(navRing, 0, WALL, { facade: 'striped', wall: SM_YELLOW, stripe: SM_GREY, trim: SM_CREAM, bay: 6, shop: 'none' });
  const roof = roofOver({ c: at(LEN / 2, 0, 0).slice(0, 2), ax: [-ax[0], -ax[1]], L: LEN, W: HW * 2 }, WALL,
    { roof: 'gabled', pitch: 24, roofColour: SLATE, roofTex: 'slate', eaves: .35, wall: SM_YELLOW });
  const rise = (HW + .35) * Math.tan(24 * Math.PI / 180), top = WALL + rise;
  // the gable front: stripes, the little arched frieze, rose window, portal and lunette (all on the front plane)
  const front = () => {
    const o = .04, P3 = (v, z) => { const p = at(-o, v, z); return p; };
    if (!vis([ax[0], ax[1], 0])) return '';
    let s = '';
    for (let z = .62; z < top; z += 1.24) {           // grey bands over the yellow, cut to the gable outline
      const w0 = z < WALL ? HW : HW * (1 - (z - WALL) / rise), z1 = Math.min(z + .62, top), w1 = z1 < WALL ? HW : HW * (1 - (z1 - WALL) / rise);
      if (w0 <= .05) break;
      s += shape([P3(-w0, z), P3(w0, z), P3(Math.max(.02, w1), z1), P3(-Math.max(.02, w1), z1)], tone([ax[0], ax[1], 0], soft(SM_GREY)), 0);
    }
    if (UPX < .5) for (let v = -HW + .4; v < HW - .3; v += .55) {   // the small arches under the gable edges
      const z = WALL + rise * (1 - Math.abs(v) / HW) - .45;
      s += edge(P3(v, z), P3(v + .25, z - .22), SM_CREAM, .07) + edge(P3(v + .25, z - .22), P3(v + .5, z), SM_CREAM, .07);
    }
    const rose = Array.from({ length: 16 }, (_, k) => P3(Math.cos(k * Math.PI / 8) * 1.25, 9.6 + Math.sin(k * Math.PI / 8) * 1.25));
    s += shape(Array.from({ length: 16 }, (_, k) => P3(Math.cos(k * Math.PI / 8) * 1.55, 9.6 + Math.sin(k * Math.PI / 8) * 1.55)), tone([ax[0], ax[1], 0], soft(SM_CREAM)), .35)
       + shape(rose, '#4f5a63', .3);
    if (UPX < .5) for (let k = 0; k < 8; k++) s += edge(P3(0, 9.6), rose[k * 2], SM_CREAM, .06);
    const arch = (w, z0, h, c) => shape([P3(-w, z0), P3(w, z0), P3(w, z0 + h - w), ...Array.from({ length: 9 }, (_, k) => P3(Math.cos(k * Math.PI / 8) * w, z0 + h - w + Math.sin(k * Math.PI / 8) * w)).slice(1, 8), P3(-w, z0 + h - w)], c, .35);
    s += arch(1.75, 0, 5.6, tone([ax[0], ax[1], 0], soft(SM_CREAM))) + arch(1.15, 0, 3.4, '#5a4334') + arch(1.15, 3.55, 1.7, tone([ax[0], ax[1], 0], soft('#d9c48f')));
    for (const v of [-4.3, 4.3]) s += arch(.55, 0, 2.6, '#5a4334');   // side doors
    return s;
  };
  // the pebble mosaic in front (black and white): a paved rectangle with a pattern
  const sagrato = () => {
    let s = shape([at(-7, -HW, .02), at(-7, HW, .02), at(0, HW, .02), at(0, -HW, .02)], '#d9d3c4', .3);
    if (UPX < .6) for (let u = -6.5; u < -.3; u += 1.1) for (let v = -HW + .5; v < HW - .3; v += 1.1)
      if ((Math.round(u) + Math.round(v)) % 2) s += shape([at(u, v, .03), at(u + .5, v + .5, .03), at(u, v + 1, .03), at(u - .5, v + .5, .03)], '#4a4a48', 0);
    return s;
  };
  const sag = { fp: [at(-7, -HW, 0), at(-7, HW, 0), at(0, HW, 0), at(0, -HW, 0)].map(p => [p[0], p[1]]), z1: .05, svg: null, draw: sagrato };
  // the rest of the OSM footprint, as separate low volumes that touch the nave but never cut into it:
  // the north aisle behind the tower (three naves), the sacristy on the south side, the rooms at the west end
  const P2 = (u, v) => at(u, v, 0).slice(0, 2);
  const aisleRing = [P2(4.7, HW), P2(4.7, 10.9), P2(LEN, 10.9), P2(LEN, HW)];
  const aisle = block(aisleRing, 0, 7.4, { facade: 'striped', wall: SM_YELLOW, stripe: SM_GREY, trim: SM_CREAM, bay: 6, shop: 'none', top: SLATE });
  const southRing = [[-70.42, 50.76], [-69.81, 44.4], [-74.48, 43.5], [-74.86, 46.05], [-78.28, 45.66], P2(LEN, -HW)];
  const south = block(southRing, 0, 6, { facade: 'painted', wall: '#e8cf98', shutters: ['#3f6b4c'], floor: 3, shop: 'none', top: SLATE });
  const westRing = [P2(LEN, -HW), [-79.24, 54.15], [-89.67, 53.13], [-90.54, 62.32], [-87.75, 64.19], [-84.54, 64.71], [-84.71, 65.81], P2(LEN, 10.9)];
  const west = block(westRing, 0, 8, { facade: 'painted', wall: '#e8cf98', shutters: ['#3f6b4c'], floor: 3.4, shop: 'none', top: SLATE });
  const backRing = southRing.concat(westRing);
  // the bell tower: cream shaft with corner pilasters, belfry with two arches a side, octagonal drum, dome, lantern
  const tw = findBuilding(SM_TOWER), tr = tw ? ccw(tw.ring) : [at(-.3, HW - .2, 0), at(-.3, HW + 4, 0), at(3.9, HW + 4, 0), at(3.9, HW - .2, 0)].map(p => [p[0], p[1]]);
  const tc = avg(tr.map(p => [...p, 0])).slice(0, 2), SH = 21.5, BF = 25.6;
  const tower = () => {
    let s = '';
    const quads = (z0, z1, inset = 0) => tr.map((a, i) => { const c = tr[(i + 1) % tr.length], sh = p => [p[0] + (tc[0] - p[0]) * inset, p[1] + (tc[1] - p[1]) * inset]; const A = sh(a), C = sh(c); return [[...A, z0], [...C, z0], [...C, z1], [...A, z1]]; });
    for (const q of quads(0, SH)) {
      s += face4(q, SM_CREAM, .55);
      let n = vNewell(q); if (!vis(n)) continue;
      const lerp = (t, z) => [q[0][0] + (q[1][0] - q[0][0]) * t, q[0][1] + (q[1][1] - q[0][1]) * t, z];
      s += edge(lerp(.08, 0), lerp(.08, SH), mix(SM_CREAM, '#8a7f6e', .35), .06) + edge(lerp(.92, 0), lerp(.92, SH), mix(SM_CREAM, '#8a7f6e', .35), .06);
      for (const z of [11, 16.5]) s += shape([lerp(.44, z), lerp(.56, z), lerp(.56, z + 1.5), lerp(.44, z + 1.5)], '#5b6266', .25);   // small windows
    }
    // every level is closed on top: seen from above, an open shaft shows the ground through the tower
    const cap = (z, inset = 0) => shape(tr.map(p => [p[0] + (tc[0] - p[0]) * inset, p[1] + (tc[1] - p[1]) * inset, z]), mix(SM_CREAM, '#ffffff', .1), .4);
    for (const q of quads(SH, SH + .4, -.06)) s += face4(q, SM_CREAM, .45);   // cornice
    s += cap(SH + .4, -.06);
    for (const q of quads(SH + .4, BF)) {
      s += face4(q, SM_CREAM, .5);
      if (!vis(vNewell(q))) continue;
      const lerp = (t, z) => [q[0][0] + (q[1][0] - q[0][0]) * t, q[0][1] + (q[1][1] - q[0][1]) * t, z];
      for (const t0 of [.16, .56]) {   // two arched openings
        const z0 = SH + 1, z1 = BF - 1.1, w = .28, mid = t0 + w / 2;
        s += shape([lerp(t0, z0), lerp(t0 + w, z0), lerp(t0 + w, z1), ...Array.from({ length: 7 }, (_, k) => { const a = k * Math.PI / 6; return lerp(mid + Math.cos(a) * w / 2, z1 + Math.sin(a) * w * 1.6); }).slice(1, 6), lerp(t0, z1)], '#3e4448', .3);
      }
    }
    for (const q of quads(BF, BF + .45, -.08)) s += face4(q, SM_CREAM, .45);
    s += cap(BF + .45, -.08);   // the belfry's flat top, around the drum
    const oct = (r, z) => polygon(tc[0], tc[1], r, 8, Math.PI / 8).map(p => [...p, z]);
    s += loft(oct(1.75, BF + .45), oct(1.75, BF + 2.3), n => tone(n, soft(SM_CREAM)));
    s += shape(oct(1.75, BF + 2.3), SM_CREAM, .4);
    const dome = [[1.75, 0], [1.62, .8], [1.3, 1.55], [.82, 2.15], [.36, 2.5]];
    for (let k = 0; k < dome.length - 1; k++) s += loft(oct(dome[k][0], BF + 2.3 + dome[k][1]), oct(dome[k + 1][0], BF + 2.3 + dome[k + 1][1]), n => tone(n, soft('#9a9893')));
    const zl = BF + 4.8;
    s += loft(oct(.34, zl), oct(.34, zl + .9), n => tone(n, soft(SM_CREAM))) + peak(polygon(tc[0], tc[1], .4, 8, Math.PI / 8), zl + .9, [tc[0], tc[1], zl + 1.4], '#9a9893');
    s += stick([tc[0], tc[1], zl + 1.4], [tc[0], tc[1], zl + 2.6], .04, '#4a4a48') + stick([tc[0] - .35, tc[1], zl + 2.2], [tc[0] + .35, tc[1], zl + 2.2], .04, '#4a4a48');
    return s;
  };
  // five volumes that touch: planOrder sorts them by which side of each shared wall the reader is on
  const parts = [
    { fp: southRing, z1: 6, draw: south.draw },
    { fp: westRing, z1: 8, draw: west.draw },
    { fp: aisleRing, z1: 7.4, draw: aisle.draw },
    { fp: navRing, z1: top, draw: () => nave.draw() + roof() + front() },
    { fp: tr, z1: BF + 7.5, draw: tower },
  ];
  return [obj(sag.fp, .05, sag.draw), obj(navRing.concat(backRing, aisleRing, tr), BF + 7.5, () => planOrder(parts.map(p => ({ fp: p.fp, z1: p.z1, svg: p.draw() }))))];
}

function oratorio() {
  const b = findBuilding(ORATORIO); if (!b) return null;
  const { c, ax, L, W } = b.obb, WALL = 8;
  const body = block(b.ring, 0, WALL, { facade: 'painted', wall: '#e9c98f', trim: '#f4ead5', shutters: ['#3f6b4c'], floor: 4, shop: 'none', bay: 4.5 });
  const roof = roofOver({ c, ax, L, W }, WALL, { roof: 'gabled', pitch: 22, roofColour: SLATE, roofTex: 'slate', eaves: .3, wall: '#e9c98f' });
  // the slate portal on the street end (the end nearest the plot centre, toward via Roma: interpreted)
  const end = dot([ax[0], ax[1], 0], [-c[0], -c[1], 0]) > 0 ? 1 : -1, o = [c[0] + ax[0] * end * (L / 2 + .04), c[1] + ax[1] * end * (L / 2 + .04)], nx = [-ax[1], ax[0]];
  const P = (v, z) => [o[0] + nx[0] * v, o[1] + nx[1] * v, z];
  const portal = () => vis([ax[0] * end, ax[1] * end, 0]) ? shape([P(-1.3, 0), P(1.3, 0), P(1.3, 4.6), P(-1.3, 4.6)], '#5d5f63', .35) + shape([P(-.85, 0), P(.85, 0), P(.85, 3.4), P(-.85, 3.4)], '#4a3a30', .3) + shape([P(-.85, 3.55), P(.85, 3.55), P(0, 4.4)], '#c9b98f', .3) : '';
  return obj(b.ring, WALL + 3, () => body.draw() + roof() + portal());
}

const LANDMARKS = [
  { name: 'Chiesa di San Martino', ids: [SM, SM_TOWER], build: sanMartino },
  { name: 'Oratorio di Nostra Signora Assunta', ids: [ORATORIO], build: oratorio },
];

// San Giorgio: the bonfire on the Piazzetta with its central pole (penola); Christmas: the tree by the sea.
// Positions are on the mapped Piazzetta (OSM way 33852544); sizes are illustrative.
const FIRE = [9, 18], XMAS = [14, 9];
function CITY_EXTRA(t) {
  if (SEASON.id === 'sangiorgio') {
    const [x, y] = FIRE;
    // the pyre: two rings of logs leaning on the penola, inside a ring of stones; flames are lofted tongues that sway
    const logs = [];
    for (let i = 0; i < 20; i++) { const a = i * 2 * Math.PI / 20 + .1; logs.push({ a: [x + Math.cos(a) * 2.1, y + Math.sin(a) * 2.1, 0], b: [x + Math.cos(a) * .3, y + Math.sin(a) * .3, 4.4], r: .15, c: i % 3 ? '#8a6a4c' : '#a07c58' }); }
    for (let i = 0; i < 12; i++) { const a = i * 2 * Math.PI / 12 + .35; logs.push({ a: [x + Math.cos(a) * 1.3, y + Math.sin(a) * 1.3, 0], b: [x + Math.cos(a) * .2, y + Math.sin(a) * .2, 5.4], r: .13, c: '#7a5c42' }); }
    const tongue = (cx, cy, z0, H, R, col, t, k) => {
      const sway = Math.sin(t * .0035 + k * 1.9) * .35, rings = [];
      for (let j = 0; j <= 6; j++) { const u = j / 6, r = Math.max(.02, R * Math.pow(Math.sin(Math.PI * Math.min(.98, u * .92 + .04)), .8) * (1 - u * .55));
        rings.push(polygon(cx + sway * u * u, cy + sway * .6 * u * u, r, 7, k).map(p => [...p, z0 + H * u])); }
      let s = ''; for (let j = 0; j < 6; j++) s += loft(rings[j], rings[j + 1], () => col);   // flame light is not shaded
      return s;
    };
    const ring = [];
    for (let k = 0; k < 20; k++) {   // people standing round the fire, facing it
      const a = k * 2 * Math.PI / 20 + (k % 3) * .15, r = 5.6 + (k % 3) * 1.2, px = x + Math.cos(a) * r, py = y + Math.sin(a) * r;
      if (!standable(px, py)) continue;   // never in the water or inside a house
      const pd = { ...pedDressed(900 + k), p: [px, py], d: [-Math.cos(a), -Math.sin(a)], walked: 0, kind: 'ped', alpha: 1 };
      ring.push({ fp: rect(px, py, .6, .6), h: 1.9, draw: t => pedestrian(pd, t).svg || '' });
    }
    return [{ fp: rect(x, y, 6, 6), h: 12, draw: t => {
      const fk = .3 + .06 * Math.sin(t * .006);
      let s = SEASON.night ? lightPool(x, y, 11, '#ffb85c', .7 + fk * .4) : '';
      for (let i = 0; i < 16; i++) { const a = i * 2 * Math.PI / 16; s += ball([x + Math.cos(a) * 2.7, y + Math.sin(a) * 2.7, .18], .26, soft('#9a958c'), .3); }
      s += shape(atZ(polygon(x, y, 2.4, 16), .02), '#5a4a3e', .2);   // ash bed
      for (let i = 0; i < 26; i++) { const a = i * 2.4, r = .4 + (i % 5) * .38; if (Math.sin(t * .005 + i * 1.7) > -.4) s += stick([x + Math.cos(a) * r, y + Math.sin(a) * r, .08], [x + Math.cos(a) * r, y + Math.sin(a) * r, .1], .1, i % 2 ? '#ffb85c' : '#ff8a3d'); }   // embers
      const parts = logs.map(l => ({ d: depthOf([(l.a[0] + l.b[0]) / 2, (l.a[1] + l.b[1]) / 2, 1.5]), svg: stick(l.a, l.b, l.r, l.c) }));
      parts.push({ d: depthOf([x, y, 4]), svg: stick([x, y, 0], [x, y, 8.2], .09, '#3a2e26') });   // the penola, charred, rising out of the fire
      const fl = [[0, 0, 4.6, 1.6, '#f26a2e'], [.8, .3, 3.4, 1.1, '#ff8a3d'], [-.7, .5, 3.8, 1.2, '#f26a2e'], [.2, -.8, 3.2, 1.0, '#ff8a3d'], [0, 0, 3.0, .9, '#ffc069'], [.4, .4, 2.2, .6, '#fde9b0']];
      s += parts.sort((p, q) => p.d - q.d).map(p => p.svg).join('');
      // flames burst from the top of the pyre and lick down its sides; drawn over the logs
      const fl2 = fl.map(([dx, dy, H, R, c], k) => ({ dx: dx * .7, dy: dy * .7, z0: 2.6 + (k % 3) * .4, H: H * 1.25, R: R * 1.15, c, k }));
      fl2.push({ dx: 1.2, dy: -.9, z0: .4, H: 2.6, R: .7, c: '#ff8a3d', k: 6 }, { dx: -1.1, dy: -1.0, z0: .4, H: 2.2, R: .6, c: '#f26a2e', k: 7 },
               { dx: 0, dy: 0, z0: 3.0, H: 4.2, R: .75, c: '#fff3c4', k: 8 }, { dx: .3, dy: .2, z0: 2.8, H: 3.0, R: .5, c: '#fff8e0', k: 9 });   // white-hot core
      s += fl2.sort((p, q) => depthOf([x + p.dx, y + p.dy, 3]) - depthOf([x + q.dx, y + q.dy, 3]) + (p.k > 3 && p.k < 6 || p.k > 7) - (q.k > 3 && q.k < 6 || q.k > 7))
        .map(f => tongue(x + f.dx, y + f.dy, f.z0, f.H * (.85 + .2 * Math.abs(Math.sin(t * .004 + f.k * 1.3))), f.R, f.c, t, f.k)).join('');
      for (let k = 0; k < 5; k++) {   // smoke: soft puffs, no outline, rising, drifting and fading
        const u = ((t * .00010 + k / 5) % 1), r = 1 + u * 2.6;
        s += lightPool(x + u * 3, y + u * 1.6, r, '#d9d3c8', .5 * (1 - u), 8 + u * 10);
      }
      return s; } }, ...ring];
  }
  if (SEASON.id === 'natale') {
    // a tall fir hung with warm white lights and a star, people gathered round it (sizes illustrative)
    const [x, y] = XMAS, H = 12.5, tiers = [[3.2, .9, 4.6], [2.6, 3.4, 7.0], [2.0, 5.8, 9.2], [1.35, 8.0, 11.2], [.7, 10.2, H]];
    const lights = [];
    for (let i = 0; i < 280; i++) {   // a spiral of bulbs over the cone
      const u = i / 280, z = 1 + u * (H - 1.4), r = 3.25 * (1 - (z - .9) / (H - .4)) + .12, a = i * 2.39;
      lights.push([x + Math.cos(a) * r, y + Math.sin(a) * r, z]);
    }
    const tree = { fp: rect(x, y, 6.6, 6.6), h: H + .8, draw: t => {
      let s = lightPool(x, y, 9, '#ffcf7a', .6);   // warm light on the paving, fading out
      s += stick([x, y, 0], [x, y, 1], .25, '#6e5440') + shape(atZ(polygon(x, y, 1.1, 8), .5), '#8a6f55', .3);
      for (const [r, z0, z1] of tiers) s += peak(polygon(x, y, r, 12), z0, [x, y, z1], '#3f6b4c');
      lights.forEach((p, i) => { if (!vis([p[0] - x, p[1] - y, .4])) return; if (Math.sin(t * .0025 + i * 2.1) > -.6) s += stick(p, [p[0], p[1], p[2] + .02], .11, i % 3 ? '#fff3c4' : '#ffe7a8'); });
      // the star on top: a five-pointed star in two crossed upright planes, so it reads from every side
      const sz = H + .75, star = (ux, uy) => Array.from({ length: 10 }, (_, k) => { const a = Math.PI / 2 + k * Math.PI / 5, r = k % 2 ? .3 : .75; return [x + ux * Math.cos(a) * r, y + uy * Math.cos(a) * r, sz + Math.sin(a) * r]; });
      s += shape(star(1, 0), '#f6c445', .3) + shape(star(0, 1), '#f2c94c', .3) + ball([x, y, sz], .16, { l: '#fff8e0', m: '#fff8e0', d: '#fff3c4' }, 0);
      return s; } };
    const crowd = [];
    for (let k = 0; k < 22; k++) {   // standing, facing the tree
      const a = k * 2 * Math.PI / 22 + (k % 3) * .12, r = 5 + (k % 4) * 1.1, px = x + Math.cos(a) * r, py = y + Math.sin(a) * r;
      if (!standable(px, py)) continue;   // never in the water or inside a house
      const pd = { ...pedDressed(700 + k), p: [px, py], d: [-Math.cos(a), -Math.sin(a)], walked: 0, kind: 'ped', alpha: 1 };
      crowd.push({ fp: rect(px, py, .6, .6), h: 1.9, draw: t => { const part = pedestrian(pd, t); return part.svg || ''; } });
    }
    return [tree, ...crowd];
  }
  return [];
}
