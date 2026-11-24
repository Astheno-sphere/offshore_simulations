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

Not absorbed (checked, thin or off-register): iart-ai/manim-skills, charlie947/motion-graphics-skills (launch-marketing
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
- Static camera is allowed and is the measured default in four reference films (`coordination/reports/reference-measurements.md`); a move is chosen per shot, not banned | OURS, decision pending

## 9. Linework and asset style
- Not filled by a verified rule. Pointers read by title only: EV whiteboard-animation and isometric-animation recipes (draw-on, isometric) under explainer-video-skills/skills/. | open
- Tells of a generated film (banned by name): dark void with small things floating, glow and particles, everything fading and sliding up, three cards in a row, docked logo, side-by-side panels standing in for a scene | HF story §8 and spec | check

## 10. QA lints (what a render gate can check)
- `npx hyperframes check --json` warns on: `line_unread`, `dead_stretch` (over 3 s nothing changes), `text_below_floor`, `first_frame_empty`, `film_silent` (over 15 s, no sound) | HF review §1 | wire for our HyperFrames cards
- Three contact sheets: each scene at start and middle, every beat, a strip across each cut, beat frames at 360 px phone width | HF review §1 | adopt
- Describe each beat frame in one sentence naming every object; an object you would have to explain is a P0; P0 breaks the read, P1 weakens, P2 polish | HF review §2-3 | adopt for every film review
- Trust measured numbers over the eye where they disagree | HF review §1

## Applied to the Irina intervention shot (first test, to be rendered before and after)
1. Event frame shows the S-92 leaving (HF: describe each beat frame naming every object; today the chip names an object that is absent).
2. Frame 0 never empty (HF `first_frame_empty`): the before-state is already the thumbnail.
3. One framing held while the field acts (HF rhythm), one deliberate camera decision per shot (MD), exits shorter than entrances.
4. Text floor and hold times measured with the lints above; headline length decision stays with the owner.
5. Sea drawn from the Hs and Tp refs (`offsim/physics/jonswap.py`), display only.
