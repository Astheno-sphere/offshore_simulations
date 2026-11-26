# Visual definitions (schema first, then verified rules)

Purpose: one place where the design rules for our films and graphics live, each with its source and licence, so a shot is
built from stated rules and not from taste. Every rule is paraphrased; a quote stays under 15 words. A rule with no verified
source is `OURS` (from our own measured references, `docs/REFERENCE_STUDY.md`) or is not written.

Sources, read from shallow clones at the pinned commits (read only, nothing executed):

| Tag | Repo @ commit | Licence | Use |
| --- | --- | --- | --- |
| HF | heygen-com/hyperframes @ 2ffa5ae (skills/hyperframes/references/*) | Apache-2.0 | film doctrine, motion craft, review lints |
| MD | iart-ai/motion-design-skills @ b85e50c | MIT | easing library, composition, safe areas |
| DA | iart-ai/data-animation-skills @ 6570c0c | MIT | chart and data animation |
| EV | iart-ai/explainer-video-skills @ 3c13a1b | MIT | explainer structure, voice timing |
| SC | scenario-labs/skills (scenario-video-color-grade, scenario-blender-previs-storyboard) | MIT | grade, camera blocking; grade skill vendored in third_party/ |
| VS | Vincentwei1021/video-shotcraft (references/aesthetic-rules.md, references/shots/) | Apache-2.0 | camera, pacing, text floors; paraphrase only |
| LO | lemomo-ai/lemo-opuscar (DIRECTOR.md, TECHNIQUE.md) | docs CC BY-NC 4.0, code MIT | review loop, pacing; paraphrase only, never copy |
| QC | tomotto1296/ai-animation-skills (skills/animation-qc-selfreview) | MIT | QC thresholds; paraphrase only |
| B1 | AmitSubhash/3brown1blue (src/three_b1b/skill/rules/) | MIT | explainer gates and timings; paraphrase only |
| HM | alchaincyf/huashu-motion (skills/huashu-motion/references/rhythm.md) | MIT (fonts, music separate) | rhythm; paraphrase only |
| OM | nexu-io/openmotion (skills/openmotion-production/references/reference-video.md) | Apache-2.0 | reference-to-shot-list method; paraphrase only |
| CA | artemnovitckii/claude-animation-skills (graph, map-route, breakdown) | MIT | HyperFrames templates; vendored in third_party/ |

Batch 2 (2026-11-25, owner list verified by clone): see the table above and section 13. Not absorbed (checked, thin or off-register): iart-ai/manim-skills, charlie947/motion-graphics-skills (launch-marketing
register), anthropics/skills (static design), gsap-skills and remotion skills (API recipes), kylezantos/design-motion-principles
(UI micro-interaction). Dropped: motion-canvas and manim (libraries, no rules), iart-ai/motion-skills (index). Not verified:
the owner's claim of a `skills/motion-graphics` file in HyperFrames (absent at HEAD) and the "13 skills" count (repo has 15).
Stars were read from page summaries and are approximate; they were not used to decide anything.

Entry form: `rule | value | source`. Status is `adopt` (apply now), `check` (render gate can test it) or `open`.

## 1. Beats and shot types
- Open on something working or a real need; frame 0 is the thumbnail, never black, never a logo alone | HF story §3 | adopt, check
- Beat shares for a ~35 s film: hook 8 %, tension 12 %, reveal 8 % (title at 20-30 % in), proof 40 %, payoff 20 % (60-80 % in, once), claim 8 %, end card 8 % holding 2-3 s | HF story §4 | adopt as a starting shape, bend per device
- The process runs fast, the payoff plays at normal speed; keep on screen only what is touched and what proves the line | HF story §4
- One viewer doing one real task is the spine; facts stay apart from creative choices, nothing is claimed the source did not say | HF story §1 | adopt (matches our report-ref rule)
- Three storylines then one: name, device, first two seconds, beats in one line, look, sound | HF story §2 | adopt for any new film
- Rhythm: contrast speeds; montage cuts every 0.13-0.8 s; a demo holds one framing 7-10 s while the thing acts; shots average 1.8-3 s | HF motion "Rhythm"
- A film visits several worlds, each with its own ground; enter each through an object already on screen | HF story §5 | open for us (our form is one world)
- Explainer shape: problem, solution, how, payoff; 30-90 s; script first, visuals illustrate the line | EV explainer-video SKILL

## 2. Easing and timing
- Ease by role: arrivals on a long tail (expo/quart out), moves and floods ease both ways, exits and zoom-throughs accelerate | HF motion | adopt
- Named curves as cubic-bezier: easeOutCubic 0.33,1,0.68,1 (safe default); easeOutQuint 0.22,1,0.36,1; easeOutExpo 0.16,1,0.3,1; easeInOutCubic 0.65,0,0.35,1; easeInCubic 0.32,0,0.67,0 (exit) | MD animation-principles/references/easing-curves.md | adopt
- Fast move 0.3-0.6 s with motion blur peaking at its fastest frame (6-12 px on text, 15-20 px full frame) | HF motion | adopt for Blender and 2D movers
- Exits are 40-50 % shorter than entrances; next element starts when the previous is 30-50 % done | HF motion | check
- Springs by damping ratio: 1.0 no bounce, 0.7-0.85 premium, 0.4-0.6 playful, under 0.3 cartoon; position and size may bounce, opacity and colour never | HF motion | adopt (engineering register: 1.0 or 0.85)
- Cut at the fastest frame of a move, same direction and speed both sides | HF motion "Cuts"

## 3. Type scale and text roles
- Title height 4-9 % of frame height, 1-2 lines; quiet lines 2.5-4 %; one accent word | HF motion "Title size" | adopt, check
- Hold a read for about 0.5 s plus 0.3 s a word; the last line at least 2 s | HF motion "Holds" | check
- Lines at most 6 words (an explainer may run to about 10), one line on screen at a time, no trailing period, no bullet slides, no three-card rows | HF story §6 | adopt (note: our headlines run longer; decision pending, see docs/VISUAL_GRAMMAR.md)
- Text below 2.6 % of the frame's short side is a lint failure | HF review §1 (`text_below_floor`) | check
- A landed title is dead still; vary entrances within a film | HF motion "Titles" | adopt
- Numbers: rounded, one formatter, tabular figures so digits do not jitter | DA chart-animation SKILL | adopt (our numbers also need a `report:` ref)

## 4. Colour roles and contrast
- Not filled by a verified external source. Our palette tokens stay `OURS` and come from the reference measurements and the owner's stated palette (oxblood, gold, orange or charcoal; Montserrat), not from a distilled hex table. | open
- Subject and ground must separate in value; two focal points in one frame is a fault | HF review §2 | check
- HyperFrames ships 13 frame presets (colour, type, treatment per look) under skills/hyperframes/assets/frame-presets/*/FRAME.md; read them when choosing a look, do not copy a preset as our brand | HF | pointer

## 5. Composition grid and safe areas
- One focal point on a thirds power point, not dead centre; hierarchy ranked; negative space used as rhythm | MD shot-composition SKILL | adopt
- Layer bg / mid / fg as ambient / secondary / primary motion | MD shot-composition SKILL
- Title-safe margins: 16:9 about 5 % all sides; 9:16 top 12-14 %, bottom 18-20 %, sides 6 %; 1:1 6-8 %; 4:5 sides 6 %, top and bottom 8 % | MD shot-composition SKILL §7 | adopt, check (our LinkedIn stills are 4:5)
- Adapt aspects by restacking, never by blind crop | MD shot-composition SKILL | adopt

## 6. Transitions
- A transition needs a cause: the object clicked becomes the next shot; match direction and speed | HF motion "Transitions with a cause" | adopt
- Every scene entering the same way, or the same move beat after beat, is a tell | HF story §8 | check

## 7. Chart and data animation
- Map data to pixels once; ease value changes (easeOutCubic counters); pace data over time; label and annotate on the mark | DA chart-animation SKILL | adopt
- Output checklist: values exact and inside the safe area at every frame, no overflow, no wrong column; inspect start, middle and end stills before encoding | DA SKILL "Deliver and verify" | adopt
- Our extra rule: every number is a `report:` ref | OURS (CLAUDE.md)

## 8. Camera moves
- One camera move per shot, named with property, from-to values, duration, easing: push/pull (dolly) 800-2000 ms ease-in-out, pan/tilt, follow, parallax | MD shot-composition SKILL §5 | adopt
- Continuous motion that works: the subject working, a slow orbit of the background stage (3-5 degrees a second); breathing or floating loops standing in for motion are a tell | HF motion
- Frame size from distance (blocking math): visible height = subject height x [4, 2, 1.15, 0.8, 0.6, 0.4, 0.25, 0.12] for extreme wide, wide, full, medium-wide, medium, medium close-up, close-up, extreme close-up; camera distance = visible height x lens (mm) / 20.25 (16:9 sensor height, 36 mm width) | SC previs-storyboard SKILL | adopt for the Blender camera
- Neutral start: eye level, medium lens (35 mm theatre frame, about 60 mm for an isolating key shot), centred, static; A/B the lens before posing; same-size lens swap d2 = d1 x f2/f1 | SC previs-storyboard SKILL | adopt
- Never constant speed; default slower; a main action arc at least 3 s; hold key information at least 1 s before cutting; pause 0.5 s after an entrance of many things | VS aesthetic-rules.md | adopt
- Whole-frame beat hits (scale pump, shake, flash) at most 3 per film, at least 16 beats apart; otherwise animate only the hero | VS aesthetic-rules.md | adopt
- Crash zoom 6 frames (4-8 allowed; over 10 reads as a push-in), at least 30 frames of hold before and 45 after; overshoot settles 3-6 %; tilt overshoot at most 3 degrees; handheld noise is 0.010-0.018 rad on an 18-26 frame scale, none on bright UI, product shot is the stillest | VS camera cards, SC previs | adopt as limits (engineering register: no handheld)
- Slow settle creep 1.2-1.8 % over a hold; no dead hold over 1 s unless it is a read | VS | check
- Audit gates for a cut sequence: one side of the action line, screen direction kept per journey, no lens jump on a cut, no two inserts in a row | SC previs | adopt
- Static camera is allowed and is the measured default in four reference films (`coordination/reports/reference-measurements.md`); a move is chosen per shot, not banned | OURS, decision pending

## 9. Linework and asset style
- Not filled by a verified rule. Pointers read by title only: EV whiteboard-animation and isometric-animation recipes (draw-on, isometric) under explainer-video-skills/skills/. | open
- Tells of a generated film (banned by name): dark void with small things floating, glow and particles, everything fading and sliding up, three cards in a row, docked logo, side-by-side panels standing in for a scene | HF story §8 and spec | check

## 10. QA lints (what a render gate can check)
- `npx hyperframes check --json` warns on: `line_unread`, `dead_stretch` (over 3 s nothing changes), `text_below_floor`, `first_frame_empty`, `film_silent` (over 15 s, no sound) | HF review §1 | wire for our HyperFrames cards
- Three contact sheets: each scene at start and middle, every beat, a strip across each cut, beat frames at 360 px phone width | HF review §1 | adopt
- Describe each beat frame in one sentence naming every object; an object you would have to explain is a P0; P0 breaks the read, P1 weakens, P2 polish | HF review §2-3 | adopt for every film review
- Trust measured numbers over the eye where they disagree | HF review §1
- Automatic QC thresholds: flicker if mean luma jumps 10 or more in one frame; strobing if swings of 22 or more occur more than 3 times a second; freeze if static 0.5 s or more with max pixel difference 12 or less; flag black, white or solid-colour frames; never start on a blank frame | QC animation-qc-selfreview/SKILL.md | check (port as our own lint)
- Declare intended statics, flashes and blackouts in an `expect` list before the first export, not after a failure | QC | adopt
- Loudness about -14 LUFS (ebur128), blackdetect, no NaN frames, one full-speed viewing with sound; do one fix round, re-check once | LO TECHNIQUE.md | adopt
- Minimum text height at 1080p: subtitles 56 px or more (about 5.2 % of frame height), secondary text 32 px or more; check by scaling frames to 480 px wide | VS | check (stricter than HF 2.6 %)
- Subtitle hold at least the spoken line plus 0.6 s and at least 1.8 s; title cards at least 4 s | LO DIRECTOR.md | adopt
- Visible height and safe areas were not found as measured lints in raea (FSL licence, source-available, cannot vendor); its list (clipped text, low contrast, unsafe areas, freezes, loudness) is a pointer only | raea README | open

## Applied to the Irina intervention shot (first test, to be rendered before and after)
1. Event frame shows the S-92 leaving (HF: describe each beat frame naming every object; today the chip names an object that is absent).
2. Frame 0 never empty (HF `first_frame_empty`): the before-state is already the thumbnail.
3. One framing held while the field acts (HF rhythm), one deliberate camera decision per shot (MD), exits shorter than entrances.
4. Text floor and hold times measured with the lints above; headline length decision stays with the owner.
5. Sea drawn from the Hs and Tp refs (`offsim/physics/jonswap.py`), display only.

## 11. Grade (new slot)
- Deterministic grade: per-pixel ops are baked into a 33^3 `.cube` by a pure-numpy script and applied with ffmpeg `lut3d`; vignette, grain and halation are separate finishing steps; a `.cube` carries colour only, spatial effects need a mask | SC scenario-video-color-grade/SKILL.md, references/ops.md | adopt, vendored (third_party/scenario-video-color-grade, MIT)
- Order: relight, selective, ops (in the LUT), then vignette, grain, halation | SC | adopt
- Op ranges: contrast 0.15-0.45 normal, 0.75-0.9 hard; saturation 0.4 bleach, 0.75 muted, 1.1-1.35 rich; black level 0.03-0.08 for faded; vignette angle PI/6 subtle, PI/3.5 strong; grain 4-10; relight only 0.3-1 stop | SC | adopt as limits
- Always grade one still first and compare before rendering video; check frame counts match the source; sweep keyed or relit renders for flicker | SC | adopt
- Proven here (2026-11-25): `grade.py` writes `.cube` files; `ffmpeg 6.1.1 -vf lut3d=file=...` applies them to the Irina baseline frame. Finding: bleach bypass and blue hour both darkened and muted the maroon frame and lost the amber accent, so a global look does not fix this frame; grade is a finishing step after the picture reads, not a repair | OURS, docs/TESTLOG.md
- Film emulation tools (film-lab) not found, unverified | open

## 12. Pacing and film review (additions)
- Cue map first, then picture locked to it, a script checks every cue; vary pace with one acceleration or deceleration and one held breath; at least four distinct camera moves in a longer film; subject fills a third of the frame height at key moments | LO DIRECTOR.md | adopt (paraphrased)
- Hook within 3 s; densest burst at 30-60 % of the length with 5-8 cuts on the beat (plus or minus a frame at 30 fps); hold the mark at least 1.5 s; soft 0.6-0.8 s eases everywhere make a film sleepy | HM rhythm.md | adopt
- Explainer gates: no animation code before a narration script, a scene list and a style contract exist; run times: equation first shown 1 s plus a 2 s wait, formula transform 1.5-2 s, camera zoom 1.5 s, hold 2-3 s after a major reveal, a 1 s wait after every 3-4 animations, at most 2 things moving, animation leads narration by about 0.5 s | B1 paper-explainer.md | adopt

## 13. Reference to shot list (our workflow, mechanised later)
- Read the reference at native frames around every cut; one-per-second thumbnails are navigation only; keep the source's exact frame rate; measure cuts, events, frames and the nearest ease curve, then name each shot and rebuild | OM reference-video.md | adopt as method (our `tools/reference_study.py` implements the same steps; do not adopt its CLI or its 215 MB app)

## 14. Production systems (verified on this machine)
- ffmpeg 6.1.1 with GPL and libzimg: `lut3d` (`.cube`), `tonemap`, `zscale`, `tblend`/`tmix`/`framestep`/`minterpolate` (motion blur), `vignette`, `noise` (temporal grain), `unsharp`, `xfade` (50+ transitions), `loudnorm` (two-pass), QC `ebur128`, `blackdetect`, `freezedetect`, `silencedetect`. GPL runs as a separate process | OURS, checked with `ffmpeg -h filter=`
- three.js is MIT. Headless render through system Chrome (WebGL2, frame by frame) is reported by another project but is untested here | open

## 15. Connectors and their risk
- `ahujasid/mcp-for-blender` (the former `blender-mcp`, MIT) exposes `execute_code`, which runs arbitrary Python in Blender, and its opt-in safe mode covers only the MCP path; the addon socket takes raw code from any local process. It has no camera tools (the "16 camera tools" claim did not verify). Not enabled by default; if ever used, on a throwaway render job only | audit of clone, 2026-11-25
- Our own path is the headless `bpy` subprocess (`offsim/blender/`), which is the same risk class; its input is our scene JSON, never agent-authored code

## 16. Studied from abhinavbwj (read in the owner's Chrome 2026-11-25; reports under coordination/reports/abhinav-*.md)
Sources: reel on Dubai walkability (AB1), carousel on informal cities (AB2), carousel on Rotterdam urban respiration (AB3). Stills only, sizes are fractions of the frame. Status: `adopt` means our template follows it, `test` means measure on a built shot first.
- Palette seen: AB2 and AB3 are near-black ground, one warm amber (data and lit rooms), cream for line and figures, one cool steel blue for the comparison; AB1 is mid-grey ground with white massing, red lines and yellow chips. A palette is a ground, one accent that carries data, one comparison colour. | AB2, AB3 | adopt as the shot palette roles; hex values come from `style.json` and the owner's reference frames, not from here
- Slide and frame text system: small spaced capital kicker (accent), bold headline of 4 to 6 words with the last 2 or 3 in accent, 3 to 5 line body, one grey source line, handle bottom right; picture on the top 55 to 65 %. | AB2 | adopt
- One template repeated across a series so the viewer learns where to look; vary only the colour map and the one-line finding. | AB3 | adopt
- Reference above result: the real satellite or map of the window above, the simulation below, with a labelled one-line finding beside the word SIMULATION. | AB3 | adopt for every simulated frame
- Say what the simulation is not: "simulation, not measurement", "a proxy, not X", and where the model differs from the real place. | AB3 | adopt; on our frames: "replay on assumed positions"
- Method on the frame: domain, resolution, time step, mask sources and solver named in a readable block (his is code). Ours: parameters as `report:` refs with page or table, assumptions flagged. | AB3 | adopt
- Colour map per physics, named and fixed: fields are the hero, not the labels. | AB3 | adopt
- Real mask geometry: OSM footprints, roads, water, parks rasterised into the model. | AB3 | adopt where the model touches the map (heliport insets)
- Locked camera for map frames; change comes from the field evolving or layers switching on the same view. One camera move only on a hero shot. | AB1, AB3 | adopt; supersedes "camera moves every shot"
- Split screen "tool above, result below" with a yellow-style chip at the seam carrying one number; chip text is a 3 to 6 word clause that runs on from the previous chip. | AB1 | test as the Irina device (option A in SHOTBOOK)
- Figure-ground maps on black: footprints in neutral grey, the studied place in accent, the comparison in blue; same window and scale for every place; value on a label chip. | AB2 | adopt
- Computed facts carry data date, window, method line and a completeness caveat; named outside sources. | AB2 | adopt
- Section drawing with lit interiors and small figures as the human layer (hidden-line, thin consistent stroke, flat fills, no shading). | AB2 | test (needs a figure library; see SHOTBOOK)
- A human anchor: a named place and a year before the data. | AB2 | adopt in the hook
- Hedge the conclusion: say where the result is mixed. | AB2 | adopt
- Number style: the largest type on screen, bold, unit small beside it, a tiny qualifier line below; before-to-after with an arrow. | AB1 | adopt
- Restyle one dataset instead of changing scene: satellite, full colour, oblique tilt, stripped to structure, back to satellite. The style change carries the beats. | AB5 (Pol reel) | test on the Bergen map
- Layer build-up, then explode into labelled slabs, then fuse into one volume: land, sea, weather, plan, replay as layers. | AB4 (Hamburg reel) | test as the model-explainer shot
- Corner counters that tick as the map fills, each with a one-line caption. | AB4 | adopt (numbers still `report:` refs)
- Annotation by thin leader line with a dot to a small spaced-capital label, no boxes. | AB4 | adopt
- Colour scale bar only where colour means a number (the data volume state). | AB4 | adopt
- Title style may change by film (handwritten script in AB4, bold sans in AB2, AB5); pick one per film. | AB4, AB5 | open
- Sound belongs to the film in his reels (minimal electronic tied to the data); ours is silent-first and unlicensed music is not allowed. | AB4, AB5 | open
- Not seen in any of five posts: neural-network simulation. His fields are numerical solvers and network analyses. A learned surrogate would be our own research direction, not a studied one. | AB1-5 | note

