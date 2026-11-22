# Teaching note: everything Nordlys has studied of Abhinav's work (videos + pictures)

from: Nordlys
to: Claude (integrator)
date: 2026-11-22
in reply to: owner request — "teach Claude all the videos and pictures you have
studied on Abhinav assets, across conversations"

## How to use this note, and its limits

This is a consolidation of what I studied in other conversations (poster system,
four reference films, one video DNA, the data-trees audit). It is teaching, not a
dump: the numbers and rules below are the transferable part.

Two hard limits, both from repo rules and from the connector:

1. **Nothing from a reference is committed.** No frames, video, or poster images
   travel with this note. The media lives only on my VM (paths in §6). Fetch the
   public sources yourself from the URLs in §6 if you need the raw pixels.
2. **I cannot push binaries through the connector** (UTF-8 text only). If a future
   task needs a frame on git, it goes as a release asset or a bundle, never as a
   committed file.

Where a claim below is a measurement, it says so. Where it is "by eye", it says
so. Do not upgrade either into the other.

## 1. The pictures: the poster system (135 posters, 5 batches)

Studied: Abhinav Bhardwaj's computational-design poster collection (~500 images
total; 135 analyzed in 5 batches: 11 + 20 + 22 + 27 + 55). Distilled into a skill
I hold locally; the distillation is mine, the posters are his. All 81 of his
source skills were read in full (digests on my VM; public repo §6).

### Tokens (hex values printed inside the images themselves — never invent others)

| Hex | Name in-image | Role |
|---|---|---|
| `#2E151C` | canonical maroon | Default background (Batch 1 urbanism / Grasshopper / CV) |
| `#1C1A19` | Space Syntax charcoal | Space Syntax series; reads as black |
| `#1A1613` | Alexander charcoal | Alexander series; darker, warmer |
| `#E8DFD0` | cream / ghost | Primary text, mass highlights |
| `#F0E8D8` | warm off-white | Variant cream |
| `#D4835C` | terracotta | Accent: the selected / focal element |
| `#D4A530` | amber | Secondary data: near-optimal, moderate |
| `#F2D98C` | bright amber | Highest-visibility end of gradients |
| `#C45545` | warm red | Danger / highest values |
| `#9DB886` | sage | Positive / optimal / comfortable |
| `#7CBAC4` | teal | Directional elements (wind) |
| `#5A7A7A` | cool slate | Low / no-visibility, muted context |
| `#C4B8A8` | warm grey | Muted tertiary |
| `#C0402C` | Alexander brick red | Exactly one title word + one tiny scene detail |

Semantic mapping, consistent across the collection: sage = good, amber =
moderate, warm red = bad/highest, cream = neutral text/mass, terracotta = the
selected element. Gradients run sage → amber → warm red. No pure white, no pure
black, no saturated primaries outside the documented variants. Everything muted,
warm, slightly desaturated — except small red accents.

### Anatomy (top → bottom)

1. Palette legend strip (4-5 chips, hex + semantic label) — on every urbanism
   poster; absent on Grasshopper explainers and the Alexander series.
2. Header metadata (optional, top-right): iteration, population, parameters.
3. Main diagram — the hero. One diagram *is* the poster (one scatter, one map,
   one section). If you cannot name it in one phrase, there is no parti yet.
4. Supporting panels below/beside: option strips, convergence graphs, spec boxes.
5. Title block — thin rule, then huge all-caps title, then one-sentence subtitle.
   **The title goes at the bottom, not the top.** The diagram leads; the
   explanation lands last.
6. Footer — centered `@abhinavbwj` handle, small, muted.

### Rules that matter for our films

- **One takeaway, one hero figure, minimal text.** One poster = one argument.
- **One accent, disciplined.** Most families use exactly one accent doing every
  accent job. Count it — it is a checkable property.
- **Honest encoding.** Bars start at zero, axes carry quantity + unit,
  uncertainty shown where it exists. Never fabricate data.
- **Numbers are load-bearing.** Every poster carries real parameters (population
  150, 200 generations, MAE 2.88, R² 0.82-0.91). A spec box with invented numbers
  is worse than no spec box.
- **Citations are a design component.** Real academic citations in the footer,
  never invented, never placeholder.
- **People are never portraits.** Stick figures, always doing something (walking,
  playing, cycling, gathering). No faces, no clothing detail.
- **Motifs never cross registers.** Map register = footprints only, no windows.
  Scene register = full facade detail. Street-section register = its own set.
  A map never gets a window; a scene never gets a bare footprint.
- **Deviations are documented, not normalized away.** When a poster breaks the
  template, record it as an observed fact.

## 2. The videos: four reference films (N6/N7/N8/N9), measured

All four: 720x900, 30 fps, 20.000 s, h264, **0 cuts**, 2 panels (section + map
of ONE case — panels are views, not cases). Full tables are in
`coordination/reports/reference-measurements.md` (branch
`agent/nordlys/reference-measurements`); headline numbers here:

| Film | Scene share | Saturated | Acts before/event/after | Motion mean / peak |
|---|---|---|---|---|
| Last tree (N6) | 0.738 | 0.0352 | 45 / 10 / 45 | 10.05 / s10 22.30 |
| Ténéré (N7) | 0.489 | 0.0224 | 50 / 5 / 45 | 5.53 / s10 15.93 |
| Tree of Knowledge (N8) | 0.691 | 0.2975 | 40 / 15 / 45 | 17.56 / s16 31.53 |
| Prometheus (N9) | 0.618 | 0.0288 | 45 / 10 / 45 | 8.12 / s10 17.92 |

What the measurements say, in one paragraph: the camera is **static** in all
four (no pan/tilt/dolly/zoom — measured); the motion is the animated field and
the light cycle. Luminance dips to its minimum at or just after the event in all
four (36.9-43.2 at s 9-10) and recovers in the after act. The motion peak sits at
the event in 3 of 4 — Tree of Knowledge breaks it (peaks at s 1, 5, 12, 16, driven
by the plan panel flipping tan/dark), so motion-peak-at-event is not a rule; the
gate rule is displacement > 0 everywhere. Tree of Knowledge is the saturated
outlier (0.2975 vs 0.02-0.04) because its plan panel is coloured by its one
scalar (temperature) — the plan *is* the field in the second panel.

Grammar amendments proposed from these films (N7; Arshad + Fable to decide, NOT
applied): panels are views not cases; act shares after always 45%, event = the
striking's own duration; 7 honest text roles plus one small corner legend (≤5
items) and one micro-readout (≤4 numbers); headline ≤7 words → ≤11 words; scene
floor 65% refuses Ténéré (48.9%) and Prometheus (61.8%) — propose 45% or keep 65%
and build tighter; scale figures = people (or the place's travellers), vehicles
where the place has them, lit rooms; saturated colour: subject only in the
section, map panel coloured by its one scalar; motion peak is NOT always at the
event.

What was NOT measured in these four (do not claim it): lens / depth of field,
light direction, colour temperature in K. If the Blender rig adds camera
movement, that target must come from a different reference, not these four.

## 3. The video: island-redevelopment reel, DNA'd frame by frame

Source: https://www.instagram.com/reel/DTVKzv5iMQQ/ (posted 2026-01-10, 1080x1920
vertical, 30 fps, 48.97 s). Subject: island-centred urban redevelopment —
geographic overview → 3D massing → zoning, movement, plots, transit, nodes,
phases. Measured on 49 frames (1 fps) with PIL/numpy. The full DNA doc is on my
VM; the transferable findings:

**10 beats in 49 s (~4.9 s each; one argument per beat, one variable changes
per beat):** reality (satellite photo, site outlined red) → build (photo
dissolves to white line base map; massing extrudes) → diagrams (movement →
zoning → plots, crossfaded) → process (Rhino viewport over Grasshopper canvas,
slow orbit, longest hold ~10 s) → poster → variants → transit → nodes → focal
points → phases (exploded axonometric; final frame is the poster).

**Palette (measured):** paper `#EBE9E7`-`#F1F1F0` dominant in every key frame;
water one flat fill `#9ED0EB` (std ≤1.7/channel — zero gradient, zero texture);
yellow `#F1C500`, light blue `#84B0EF`; orange/red, blue, teal as zone hues.
Six hues carry meaning (yellow, orange/red, blue, teal, green, purple); each hue
= one zone/use. The surrounding city is always white with grey edges (zero hue).
**Dark pixels (luminance < 50): 0% in every key frame.** There is no dark mode
anywhere in the video. Negative space (luminance > 240): 37-65% per key frame;
the model occupies ~40-50% of the frame.

**Typography (measured):** grotesque sans (Helvetica/Inter-like; exact font not
identifiable from pixels — not claimed). Titles ALL CAPS, letterspaced, grey or
black, top-left, bare (no box, no halo, no plate): "MOVEMENT HIERARCHY" cap
height 29 px at 1080 wide; "URBAN TRANSIT CONCEPT" 31 px; "Phased Development"
40 px title case. Body/legend ~14-18 px, ALL CAPS, small swatch + text, in a
corner on white. **No full-width legend strip and no black callout box
anywhere.** Text per frame: one title + one small legend, at most; 2-8 words
total. Labels on the model: none — zones are named by the legend and the
diagram title, not by text on the shapes.

**Line work (measured):** context/city fabric 1-2 px grey hairlines; movement /
route lines 4-6 px orange; site outline 6-8 px red. The 3D massing has flat
faces and thin dark outlines — the drawing IS the model, not a render of it.
Nothing is textured, shaded with gradients, or given a drop shadow.

**Denotation:** diagram titles name the *question*, not the picture
("MOVEMENT HIERARCHY", "URBAN TRANSIT CONCEPT", "Phased Development"). Nothing
on screen names a number, a KPI, or a verdict — no clock, no HUD. The caption
does the arguing, as questions: "How to make it more rational? More tangible?
More usable?" / "Tried this out. The output was decent, still a lot of
refinements required though." Register: peer review, not sales.

**Motion:** camera static in every diagram/poster beat. The model does not move;
the *content* moves (fills appear, massing extrudes, lines draw on). Slow orbit
only inside the Rhino screen record (14-24 s); slow push only in the opening
build (1-7 s). The base map and island outline never move once established.

**Sound (measured, not listened to):** mean -16.1 dB, max -1.0 dB; silence only
in the first 1.55 s. Credited as "Ghost Duet" by Louie Zong. Speech presence
unverified; do not claim a genre or mood beyond the credit.

**The childishness test — his 10 devices, mapped to our demo v4 faults
(measured):** (1) white paper, 0% dark pixels — authority from restraint; ours
was dark ambient everywhere. (2) One saturated thing per frame, one argument
per beat; ours had everything at once, every frame. (3) Context ghosted to
~15% so the argument sits alone; ours had context at full strength. (4) Flat
colour only, one encoding per thing; ours had five competing encodings of the
same sea. (5) Denotation by naming, bare caps titles, small corner legends;
ours had black callout boxes + a full-width legend strip. (6) Zero chrome — no
clock, KPI ticker, HUD, watermark, footer; ours had seven chrome elements.
(7) The model is the object (white massing, thin grey edges); ours had 5x
vessel symbols with rings and halos. (8) Questions, not claims; ours declared
("THE PLAN", "CHECKED"). (9) ~5 s per beat, one variable per beat; ours was one
continuous 24 s camera move with everything visible. (10) Starts from reality
(satellite photo, red site outline) and shows the process (Rhino/Grasshopper
screen record); ours started from a typeset equation card and never showed the
tool or the real place.

Durable rules from it (not demo-specific): paper, not dark ambient; one argument
per beat; delete the legend strip and black callout boxes; delete the HUD chrome
or reduce it to one small line; one encoding per thing; show the computation;
start from reality; change the register to questions and admit limits.

## 4. The pictures: Grasshopper data trees (carousel audit)

Source: https://www.instagram.com/p/Df7tq2qEaT5/ (15 slides, 19 Nov 2026).
Audited against Rutten (2018) + Issa ch. 3. Already on main as
`docs/DATA_TREES.md` (you rewrote it with the mapping section) — read that, do
not re-derive it from this note. The audit's errors, for the record: slides 7-8
use Text Format ("{0}+{1}={2}"), not Addition — outputs are strings; slide 5
headline {0} is right, panel read {0;0} is suspect; slide 7/8 path readings
{0;0} conflict with Issa §3.3.2 and invert graft depth — counts (3 vs 9) right,
paths unverified; slide 15 Simplify read as 12 branches like Graft, impossible
for a 3-branch input. "R." = Rajaa Issa. Exit test still open: rebuild slides 7,
8, 15 in Grasshopper on desktop and report actual panel paths.

## 5. What I have NOT studied (gaps — do not fill these by guessing)

- No lens / depth-of-field / light-direction / colour-temperature measurements
  anywhere. The poster skill and the film measurements do not contain them.
- The 135 poster *images* are not stored on my VM — they were analyzed from the
  public collection and the distillation is the skill. If you need a specific
  poster, fetch it from his public repos/Instagram; do not claim I hold the
  files.
- Only one Abhinav video has a full DNA (the island reel, §3). The four tree
  films (§2) are the only other films measured.
- The taste skill (Leonxlnx design-taste-frontend) is NOT Abhinav. Different
  system, different domain (web pages). Do not confuse its palettes or effects
  with the tokens in §1 — we installed it adapted, web-pages-only, for that
  reason.
- Sound: I measured levels, I did not listen. Speech presence unverified.

## 6. Sources you can fetch yourself

- Public skills repo (all 81 skills): https://github.com/Abhinavbwj/Claude-skills-for-Computational-Designers.git
- Island reel: https://www.instagram.com/reel/DTVKzv5iMQQ/
- Data-trees carousel: https://www.instagram.com/p/Df7tq2qEaT5/
- Four reference films: local-only files on my VM (media library, 6 files,
  20 MB); re-measure from your own copies if you need the raw frames — they are
  not on git and will not be committed.
- Full tables: `coordination/reports/reference-measurements.md` (branch
  `agent/nordlys/reference-measurements`).
- Data trees: `docs/DATA_TREES.md` on main.
- Poster tokens/anatomy: distilled in §1 above; the full skill lives on my VM
  only (`custom-skills/abhinav-poster-style/SKILL.md`, local-only). If a task
  needs the whole file on git, say so and Arshad decides — it is a distillation
  of his public work, not his files, but it is still his system and the call is
  his.
