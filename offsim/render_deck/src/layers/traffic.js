// AIS traffic density for the deck.gl renderer. `traffic` is the block offsim.traffic.positions.load_traffic put in scene.json: positions
// from a FETCHED clip (Kystverket HAIS / BarentsWatch), fixed-seed subsample. null/undefined (no clip pulled) -> no layer, and
// scene.world_stack says why. The dots carry no time (time_synchronised is false): this shows where vessels were, not when, so it never
// moves with the simulation clock and never makes a claim about the simulated run.
import {ScatterplotLayer} from '@deck.gl/layers';

const hex = (h, a = 255) => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16), a];

export function trafficLayers(traffic, st) {
  if (!traffic || !traffic.points || !traffic.points.length) return [];
  return [new ScatterplotLayer({id: 'ais-traffic', data: traffic.points, getPosition: (d) => d, getFillColor: hex(st.paper, 70),
    radiusUnits: 'pixels', getRadius: 1.4, parameters: {depthTest: false}})];
}
