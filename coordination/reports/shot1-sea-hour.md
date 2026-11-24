# Shot 1 sea hour (prep for the helideck still)

Source: NORA3 point series, point 3.0E 60.6N (the stress-test point),
winter 2011/12 (the worst winter: 24 unmet flights, 10 infeasible days in
the original set). Files `pt_nora3_wave_201112/201201/201202.nc`, 2,184 hours.

- **Hook hour (candidate): 2011-12-18T01:00 — Hs 4.00 m, Tp 12.3 s.**
  A working winter sea: rough enough to read, not a survival storm.
- Extreme hour in the same winter: 2011-12-25T20:00 — Hs 14.22 m, Tp 14.9 s.
  (The kind of sea that cancels flights; a candidate reference for the grid
  beats, not the hook.)
- Winter 2011/12 Hs: p50 3.34 m, p90 6.21 m, p99 9.92 m. Hours above the
  routine limit (5.5 m): 332/2,184; above the regulatory limit (7.0 m): 134.

The seed and the hour go in the shot spec (`jonswap.Sea` seeded from this
hour's Hs and Tp), per SHOTBOOK.md's simulation-accuracy section.
