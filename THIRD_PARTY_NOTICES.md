# Third-party notices

## Junior Architect Pipeline v2.0.0 (Abhinav Bhardwaj)

`tools/hooks/gate.py` and `docs/HOOKS.md` adopt design ideas from the gates of the Junior Architect Pipeline
(`junior-architect/scripts/gate.js`, `junior-architect/hooks/hooks.json`): a PreToolUse hook that blocks with exit code 2 and a
message on stderr, a Stop hook that prints `{"decision":"block","reason":...}` and honours `stop_hook_active` to avoid a loop,
protecting evidence files from every tool including the shell, and failing quietly on unreadable input. The code is written
independently in Python; no source text was copied. The licence is reproduced here as a courtesy and because the ideas are credited.

```
MIT License

Copyright (c) 2026 Abhinav Bhardwaj

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Pocket City skill (April Zhu)

Vendored unmodified under `third_party/pocket-city/` (built example pages, preview SVGs and scene data removed to save
space). MIT. Its drawing kit builds on Colorfigures and iso-glow, which build on Tolga Cohce's iso-figure (MIT). Map data
fetched by it stays under the ODbL, credit "(c) OpenStreetMap contributors". Full licence text: `third_party/pocket-city/LICENSE`.
