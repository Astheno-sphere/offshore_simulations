# Evidence form built, six palettes added, three more Abhinav studies (read in order)
Owner: "keep teaching Nordlys". What changed on `agent/claude/visual-engine`:
1. `coordination/reports/abhinav-dubai-walkable-reel.md`, `abhinav-informal-cities-carousel.md`, `abhinav-urban-respiration-carousel.md`, `abhinav-hamburg-and-pol-reels.md`:
   five posts studied in the owner's Chrome (stills only; no easing, cut or sound measured). Read the gap tables.
2. `docs/VISUAL_GRAMMAR.md` section 10 (the pattern), `rules.EVIDENCE`, `offsim/cinema/evidence.py` (inspector, wired into `story.check`),
   `offsim/motion/evidence.py` (frame builder), `tools/evidence_still.py` (draft frame from the three stress-test files; run with `PYTHONPATH=.`).
3. `offsim/cinema/look.py`: palettes amber-black, grey-red-chip, neon-black, oxblood-gold, paper-oxblood, charcoal-orange (estimated by eye, tune against frames).
Your part: your Molde peak-shot and Blender map work should output the REFERENCE panel (real map of the window) and a field or route panel for shots 2 and 3;
`render_evidence(shot, values, panels={"reference": PIL, "result": PIL}, palette)` takes them. Counting rule stays: the number shown is counted in the frame.
Do not tune hex values from memory; send saved frames (reels as files) and run `eyes dna` (skills/reference-eyes/SKILL.md) to measure motion and palette.
Montserrat: put Montserrat-Bold.ttf and -Regular.ttf (OFL) in offsim/assets/fonts and use family "Montserrat" (no code change needed).
