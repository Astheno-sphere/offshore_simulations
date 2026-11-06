// Map depth: terrain + bathymetry mesh draped with the baked hillshade, plus CAD-style isobaths.
// Input (scene.world.terrain, built by offsim/worlds/depth.py build_world_depth and inlined by render.py):
//   {bounds:[w,s,e,n,zmin,zmax], positions:[[lon,lat,z]...], normals:[[x,y,z]...], texcoords:[[u,v]...],
//    indices:[...], texture:{image:"data:image/png;base64,...", bounds:[w,s,e,n]}, isobaths:{type:"FeatureCollection",
//    features:[{geometry:{type:"LineString"|"MultiLineString"}, properties:{depth, bold}}]}}
// Offline: everything in memory; no URL fetch, no CDN worker. Pure function of the data (no time dependence).
import {SimpleMeshLayer} from '@deck.gl/mesh-layers';
import {BitmapLayer, PathLayer} from '@deck.gl/layers';
import {COORDINATE_SYSTEM} from '@deck.gl/core';

const hexA = (h, a = 255) => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16), a];

function meshFrom(terrain) {
  // positions relative to an origin so float32 keeps precision; METER_OFFSETS-free: LNGLAT_OFFSETS in degrees
  const [w, s, e, n] = terrain.bounds;
  const ox = (w + e) / 2, oy = (s + n) / 2;
  const P = terrain.positions, N = terrain.normals, T = terrain.texcoords;
  const pos = new Float32Array(P.length * 3), nor = new Float32Array(P.length * 3), uv = new Float32Array(P.length * 2);
  for (let i = 0; i < P.length; i++) {
    pos[3 * i] = P[i][0] - ox; pos[3 * i + 1] = P[i][1] - oy; pos[3 * i + 2] = P[i][2];
    if (N) { nor[3 * i] = N[i][0]; nor[3 * i + 1] = N[i][1]; nor[3 * i + 2] = N[i][2]; }
    if (T) { uv[2 * i] = T[i][0]; uv[2 * i + 1] = 1 - T[i][1]; }   // depth.py v=1 north; texture rows go north->south
  }
  return {origin: [ox, oy], mesh: {attributes: {POSITION: {value: pos, size: 3}, NORMAL: {value: nor, size: 3},
    TEXCOORD_0: {value: uv, size: 2}}, indices: {value: new Uint32Array(terrain.indices), size: 1}}};
}

export function terrainLayers(terrain, style) {
  if (!terrain) return [];
  const layers = [];
  const tex = terrain.texture && terrain.texture.image;
  if (terrain.positions && terrain.indices) {
    const {origin, mesh} = meshFrom(terrain);
    layers.push(new SimpleMeshLayer({
      id: 'terrain-mesh', data: [{}], mesh, texture: tex || null,
      coordinateSystem: COORDINATE_SYSTEM.LNGLAT_OFFSETS, coordinateOrigin: [origin[0], origin[1], 0],
      getPosition: () => [0, 0, 0], getColor: tex ? [255, 255, 255, 255] : hexA(style.land),
      material: {ambient: 0.75, diffuse: 0.35, shininess: 0, specularColor: [0, 0, 0]}, pickable: false,
    }));
  } else if (tex) {
    const [w, s, e, n] = terrain.texture.bounds || terrain.bounds;
    layers.push(new BitmapLayer({id: 'terrain-hillshade', image: tex, bounds: [w, s, e, n], opacity: 1}));
  }
  const iso = terrain.isobaths && terrain.isobaths.features;
  if (iso && iso.length) {
    const paths = [];
    for (const f of iso) {
      const g = f.geometry, bold = f.properties && f.properties.bold;
      const lines = g.type === 'MultiLineString' ? g.coordinates : [g.coordinates];
      for (const l of lines) paths.push({path: l, bold});
    }
    layers.push(new PathLayer({
      id: 'isobaths', data: paths, getPath: (d) => d.path, widthUnits: 'pixels',
      getWidth: (d) => (d.bold ? style.isobath_bold_px || 1.6 : style.isobath_px || 1.0),
      getColor: (d) => hexA(style.paper, d.bold ? 90 : 45), parameters: {depthTest: false},
    }));
  }
  return layers;
}
