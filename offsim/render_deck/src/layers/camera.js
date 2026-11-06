// Per-frame camera from Python (offsim.cinema.camera.camera_track). The renderer does no camera maths of its own:
// it reads the precomputed frame (or interpolates linearly between two frames when t falls between them).
// track: [{i, s, t, longitude, latitude, zoom, pitch, bearing}, ...], one per output frame, covering sim time [t0, t1).
const KEYS = ['longitude', 'latitude', 'zoom', 'pitch'];

export function cameraAtFrame(track, t, t0, t1) {
  const n = track.length;
  if (!n) throw new Error('empty camera track');
  const f = (t - t0) / Math.max(t1 - t0, 1e-9) * n;  // fractional frame index
  const x = Math.min(Math.max(f, 0), n - 1);
  const i = Math.floor(x), j = Math.min(i + 1, n - 1), u = x - i;
  const a = track[i], b = track[j];
  const out = {};
  for (const k of KEYS) out[k] = a[k] + (b[k] - a[k]) * u;
  // bearing: take the short way round, so a track that wraps at ±180 does not spin the map
  let db = b.bearing - a.bearing;
  db -= 360 * Math.round(db / 360);
  out.bearing = a.bearing + db * u;
  return out;
}
