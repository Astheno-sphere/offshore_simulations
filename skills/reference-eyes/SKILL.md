---
name: reference-eyes
description: Watch, measure and compare videos locally with claude-eyes (index, contact sheets, shots, palette, editing DNA, crops). Use when studying a reference film (Abhinav frames, any clip) or checking our own render against it.
---

# reference-eyes (offsim wrapper)

Upstream: https://github.com/moritzkremb/claude-eyes (MIT, pinned a540961, 2026-10-16). Installed, not vendored. It runs only
ffmpeg, tesseract or rapidocr, and optional whisper.cpp, on local files. The one cloud route (ElevenLabs transcript) is off unless
`ELEVENLABS_API_KEY` is set: never set it for our work. `yt-dlp` fetches URLs; this workspace's allowlist usually refuses that, so
bring clips in as files.

## Install (this workspace or a laptop)
    python -m venv /tmp/eyes-venv && /tmp/eyes-venv/bin/pip install "git+https://github.com/moritzkremb/claude-eyes@a540961"
    /tmp/eyes-venv/bin/eyes setup        # READY is enough for silent films (no whisper needed)
Windows laptop: same commands with `py -m venv`; `eyes setup --fix` installs ffmpeg where it can.

## Our loop (docs/REFERENCE_STUDY.md: measure, name, budget, gate, build)
1. `eyes index ref.mp4` then `eyes overview ref` (contact sheets under `~/.cache/eyes/<id>/sheets`). Read the sheets with Read.
2. `eyes dna ref --json`: format, shots, cuts per minute, shot lengths, text overlays, palette, loudness. These are the measured numbers.
3. `eyes crop ref 0:12 --box x,y,w,h` to read type size, linework and label craft at full resolution; `eyes frames ref --range a-b --fps 2`.
4. Build our shot, index it the same way, `eyes compare ref ours` and `eyes report ref --vs ours` (metric by metric match/close/off).
5. Write measurements to `coordination/reports/reference-measurements.md`. Numbers, not impressions.

## Rules
- A reference video is studied, never committed: no frames, crops, sheets or DNA caches in git (cache lives in `~/.cache/eyes`, outside the repo). Our own renders may be indexed freely.
- DNA is pacing and palette, not quality: it will not tell you the linework is weak. Look at the crops.
- OCR reads our own text too: use it as a typo and clipping lint on our renders (see TESTLOG).
- Soft dissolves are missed by shot detection (upstream roadmap): count those by eye.
- GPU, Blender and browser steps stay elsewhere; this skill only measures.

## Evidence
docs/TESTLOG.md, 2026-11-25 entry (claude-eyes).
