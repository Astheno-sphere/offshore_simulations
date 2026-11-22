/* Gion Shirakawa landmarks.
   Tatsumi Daimyojin (OSM w1232496244): a very small shrine on the triangular plot where Shirakawa-minami-dori and
   Shinbashi-dori fork; a torii, a small hokora behind it, vermilion tamagaki carrying performers' names, fox statues on
   both sides (4travel.jp/dm_shisetsu/11291565). Sizes and placing inside the plot are read from photographs.
   Tatsumi-bashi (OSM 190891717): steel girder bridge, 7.5 m long, 3.1 m wide (1957), stone paving on top, wooden railing
   (Kyoto City bridge leaflet hashishirube03.pdf).
   Kanikakuni stone: a natural Kurama stone about 30 m west of Tatsumi-bashi (same leaflet); its exact spot is interpreted. */
const TATSUMI = 'w1232496244', VERMILION = '#c4472f', SHRINE_ROOF = '#5f6168';

function tatsumiShrine() {
  const b = findBuilding(TATSUMI); if (!b) return null;
  const ring = ccw(b.ring), { c, ax } = b.obb, nx = [-ax[1], ax[0]];
  const at = (u, v, z) => [c[0] + ax[0] * u + nx[0] * v, c[1] + ax[1] * u + nx[1] * v, z];   // u > 0 toward the torii (west)
  const draw = () => {
  const parts = [];
  // gravel ground, then the vermilion tamagaki: one part per edge so planOrder puts the near edges in front of the hall
  const ground = shape(atZ(ring, .04), '#e2dbca', .3);
  for (let i = 0; i < ring.length; i++) {
    const a = ring[i], q = ring[(i + 1) % ring.length], L = Math.hypot(q[0] - a[0], q[1] - a[1]), n = Math.max(1, Math.round(L / .55));
    const ux = (q[0] - a[0]) / L * .08, uy = (q[1] - a[1]) / L * .08;
    const fp = [[a[0] + uy, a[1] - ux], [q[0] + uy, q[1] - ux], [q[0] - uy, q[1] + ux], [a[0] - uy, a[1] + ux]];
    let f = '';
    for (let k = 0; k <= n; k++) { const p = [a[0] + (q[0] - a[0]) * k / n, a[1] + (q[1] - a[1]) * k / n]; f += stick([...p, 0], [...p, 1.05], .07, VERMILION); }
    f += stick([...a, 1.05], [...q, 1.05], .06, VERMILION) + stick([...a, .55], [...q, .55], .04, VERMILION);
    parts.push({ fp, z1: 1.1, svg: f });
  }
  // the hokora: a small red hall on a stone base with a tiled gable roof, at the plot's east end
  const hc = at(-2.4, -.6, 0), hall = rect(hc[0], hc[1], 2.2, 1.7).map(p => { const dx = p[0] - hc[0], dy = p[1] - hc[1]; return [hc[0] + ax[0] * dx - ax[1] * dy, hc[1] + ax[1] * dx + ax[0] * dy]; });
  const base = block(hall.map(p => [hc[0] + (p[0] - hc[0]) * 1.25, hc[1] + (p[1] - hc[1]) * 1.25]), 0, .35, { facade: 'plain', wall: '#b9b3a6', top: '#cfc9bc', shop: 'none' });
  const body = block(hall, .35, 2.3, { facade: 'plain', wall: '#b8402c', shop: 'none', top: '#7a3a2c' });
  const roof = roofOver({ c: [hc[0], hc[1]], ax, L: 2.2, W: 1.7 }, 2.3, { roof: 'gabled', pitch: 32, roofColour: SHRINE_ROOF, roofTex: 'kawara', eaves: .45, wall: '#b8402c' });
  parts.push({ fp: hall, z1: 3.4, svg: base.draw() + body.draw() + roof() });
  // the torii at the west end, facing the lane
  const tc = at(2.9, -.4, 0), side = v => [tc[0] + nx[0] * v, tc[1] + nx[1] * v];
  const torii = () => {
    const [a, q] = [side(-.9), side(.9)];
    let s = stick([...a, 0], [...a, 2.7], .1, VERMILION) + stick([...q, 0], [...q, 2.7], .1, VERMILION);
    s += stick([...side(-1.2), 2.2], [...side(1.2), 2.2], .07, VERMILION);                               // nuki
    s += stick([...side(-1.35), 2.75], [...side(1.35), 2.75], .11, VERMILION) + stick([...side(-1.45), 2.95], [...side(1.45), 2.95], .09, '#2f2b2b');   // kasagi
    return s;
  };
  parts.push({ fp: rect(tc[0], tc[1], .6, 2.6), z1: 3, svg: torii() });
  // two stone foxes either side of the hall
  for (const v of [-1.3, 1.1]) { const f = at(-1.0, v, 0); parts.push({ fp: rect(f[0], f[1], .5, .5), z1: .9, svg: stick([f[0], f[1], 0], [f[0], f[1], .35], .2, '#a9a49a') + ball([f[0], f[1], .62], .2, soft('#d9d4c8'), .3) + stick([f[0], f[1], .7], [f[0], f[1], .9], .04, '#d9d4c8') }); }
  return ground + planOrder(parts);
  };
  return obj(ring, 3.4, draw);   // everything is drawn at draw time: roofOver and block read SEASON (snow, night)
}

// Tatsumi-bashi: stone deck on steel girders with a wooden railing, laid along the mapped footbridge
function tatsumiBridge() {
  const A = [9.8, -11.0], B = [11.4, -18.8], L = Math.hypot(B[0] - A[0], B[1] - A[1]), u = [(B[0] - A[0]) / L, (B[1] - A[1]) / L], n = [-u[1], u[0]], hw = 1.55;
  const e1 = [A[0] - u[0] * .4, A[1] - u[1] * .4], e2 = [B[0] + u[0] * .4, B[1] + u[1] * .4];
  const deck = [[e1[0] - n[0] * hw, e1[1] - n[1] * hw], [e2[0] - n[0] * hw, e2[1] - n[1] * hw], [e2[0] + n[0] * hw, e2[1] + n[1] * hw], [e1[0] + n[0] * hw, e1[1] + n[1] * hw]];
  const draw = () => {
    let s = block(deck, -.2, .22, { facade: 'plain', wall: '#6f7a78', top: '#c9c2b4', shop: 'none' }).draw();
    for (const sg of [-1, 1]) {
      const off = p => [p[0] + n[0] * hw * .92 * sg, p[1] + n[1] * hw * .92 * sg];
      for (let k = 0; k <= 6; k++) { const p = off([e1[0] + (e2[0] - e1[0]) * k / 6, e1[1] + (e2[1] - e1[1]) * k / 6]); s += stick([...p, .22], [...p, 1.1], .07, '#7a5a40'); }
      s += stick([...off(e1), 1.1], [...off(e2), 1.1], .07, '#8a6a4c') + stick([...off(e1), .7], [...off(e2), .7], .04, '#8a6a4c');
    }
    return s;
  };
  return obj(deck, 1.2, draw);
}

// the Kanikakuni stone (Kurama stone) on the bank, about 30 m west of the bridge (spot interpreted)
const STONE = [-18.7, -20.4];   // between two bank trees
function kanikakuniStone() {
  const [x, y] = STONE, rings = [[1.0, 0], [1.05, .45], [.9, .9], [.55, 1.25], [.2, 1.4]];
  const rk = (r, z, k) => polygon(x + Math.sin(k) * .08, y, r, 7, .3 + k * .2).map(p => [...p, z]);
  return obj(rect(x, y, 2.4, 2.4), 1.5, () => {
    let s = shape(atZ(polygon(x, y, 1.25, 8), .05), '#a8a196', .3);
    for (let k = 0; k < rings.length - 1; k++) s += loft(rk(rings[k][0], rings[k][1] + .05, k), rk(rings[k + 1][0], rings[k + 1][1] + .05, k + 1), nn => tone(nn, soft('#7f7b73')));
    return s;
  });
}

const LANDMARKS = [
  { name: 'Tatsumi Daimyojin', ids: [TATSUMI], build: tatsumiShrine },
  { name: 'Tatsumi-bashi', ids: [], build: tatsumiBridge },
  { name: 'Kanikakuni stone', ids: [], build: kanikakuniStone },
];

// Yoizakura light-up: andon lanterns along Shirakawa-minami-dori (the lane on the north bank); Kanikakuni-sai: white
// chrysanthemums at the stone. Positions illustrative; what is shown comes from the cited event pages.
const LANE = [[-127, -51], [-96, -42], [-89, -40], [-7, -12], [8, -4], [21, 3]];
function CITY_EXTRA(t) {
  if (SEASON.id === 'yoizakura') {
    const out = [];
    for (let i = 0; i < LANE.length - 1; i++) {
      const a = LANE[i], b = LANE[i + 1], L = Math.hypot(b[0] - a[0], b[1] - a[1]), u = [(b[0] - a[0]) / L, (b[1] - a[1]) / L], n = [u[1], -u[0]];
      for (let s = 2; s < L; s += 4.2) for (const off of [2.6, -2.6]) {
        const x = a[0] + u[0] * s + n[0] * off, y = a[1] + u[1] * s + n[1] * off;
        if (!standable(x, y, .5)) continue;
        out.push({ fp: rect(x, y, .5, .5), h: 1.05, draw: () => {
          const fp = rect(x, y, .34, .34);
          return block(fp, 0, .1, { facade: 'plain', wall: '#3a2e26', top: '#3a2e26', shop: 'none' }).draw() + loft(atZ(fp, .1), atZ(fp, .85), () => '#fff3c4') + shape(atZ(fp, .85), '#fde9b0', .2) + shape(atZ(rect(x, y, .4, .4), .9), '#3a2e26', .2);
        } });
      }
    }
    return out;
  }
  if (SEASON.id === 'kanikakuni') {
    const [x, y] = STONE, out = [];
    for (let k = 0; k < 9; k++) { const a = -1.3 + k * .32, px = x + Math.cos(a) * 1.35, py = y + Math.sin(a) * 1.35;
      out.push({ fp: rect(px, py, .3, .3), h: .5, draw: () => stick([px, py, 0], [px, py, .35], .03, '#5f7f55') + ball([px, py, .4], .13, soft('#f6f3ea'), .25) }); }
    return out;
  }
  return [];
}
