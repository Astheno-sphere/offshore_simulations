# Pocket City skill

Any place in the world, as a Pocket City: a square plot (150–250 m) of real buildings, streets, trees, shops,
traffic and people, hand-drawn in isometric, with seasons and special occasions. One self-contained HTML page.

See it: https://april-zhu.com/pocketcity

## Install

Claude Code:

```bash
curl -fsSL https://april-zhu.com/pocketcity/skill/pocket-city.tar.gz | tar -xz -C ~/.claude/skills
```

Codex:

```bash
curl -fsSL https://april-zhu.com/pocketcity/skill/pocket-city.tar.gz | tar -xz -C ~/.codex/skills
```

Claude.ai (Settings → Capabilities → Skills): upload `pocket-city.skill`. Other agents that read `SKILL.md` skills:
unzip into their skills folder.

Needs Python 3.9+ with `pip install shapely`, Node 18+ (22+ preferred), and Google Chrome or Chromium for the
check renders. The agent needs network access for OpenStreetMap and web research (in Codex, allow network for the
session or approve it when asked).

## Use

Ask: "Make a pocket city of Portofino harbour, 230 m", "Gion in Kyoto, 200 m", "a pocket city around the Pantheon in Rome", "my street in
Lisbon: Rua da Rosa at Travessa da Queimada, 180 m". The skill fetches the map, places the square so no famous
building is cut, researches the buildings, street life, climate and festivals, hand-builds the landmarks and checks
the result in renders.

What you get on the page: buildings with real façades and shopfronts, paved squares, trees by species, water with
reflections and ripples, moving people, bikes, cars and boats, seasons that each look different, and special occasions
(night scenes with lit windows, lamps, bonfires, fairy lights, falling petals).

## Credits

Pocket City by April Zhu. The drawing kit builds on Colorfigures and iso-glow, which build on Tolga Cohce's
iso-figure (MIT). Map data © OpenStreetMap contributors (ODbL). Licence: MIT (LICENSE).
