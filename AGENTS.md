# AGENTS.md

FLAMORIS-CG is a **script-driven CG clip producer**, a sibling of KineticTypo. **Cinema is paused** and owns any future work of film-wide scripts, project-wide intent and orchestration; do not revive it or create a duplicate AI director here. Read README and docs/architecture.md before editing.

## Second purpose: AI-native CG research

Besides making useful CG clips, this repository investigates **how CG tools themselves evolve when AI is a first-class collaborator**. Treat this as an experimental question, not as proof that natural-language automation or a generative tool is superior. Design small controlled tests of semantic operations, inspectable state, targeted edits, repeatability and human approval. Document both favorable and unfavorable results. Keep everything scoped to individual CG scenes/clips; do not implement Cinema's paused project-wide planner. Read [docs/ai-native-research.md](docs/ai-native-research.md).

## Current stage

This is an **experimental Blender lab**, not a shipped CG engine. Linux headless Blender 5.2.3 LTS has accepted static preview generation and actual MCP image disclosure; see docs/preview-acceptance.md. This does not certify sequences, Windows hardware, arbitrary modeling or GPU jobs. Never claim a successful Blender render from a passing Python test.

## Boundaries

- CG: object identity, animation instructions, scene/clip output requests.
- Blender: mesh geometry, physics, lighting and actual rendering.
- Glyph: glyph geometry, morphing and provenance. Reuse its own APIs; do not fork its algorithms.
- KineticTypo: text animation.
- Kachinco: timeline/audio/editing. Do not mutate its projects outside its supported interface.
- Cinema: historical separate scene/take experiments and future project controller; leave paused.

## Engineering practice

1. Verify the repository's actual files, supported runtime and tests before edits. No assumed LIME/Mango/Blender paths, GPU devices, MCP URLs or service names.
2. Make each experiment **small, scriptable and reproducible**. Record the spec, Blender version, command, artifacts and acceptance outcome.
3. Keep scene JSON declarative, bounded, and strictly validated. Never execute user-provided Python, Python expressions, arbitrary Blender scripts, filesystem paths embedded in JSON or remote code.
4. Render only with explicit user action and a **new** output folder. No surprise installations, GPU jobs, services or overwrites.
5. Check licensing/provenance before introducing other repos' code, media, font, models or generated assets.
6. Preserve Windows/Linux portability; prefer standard-library tests when Blender isn't installed.
7. Compare Cinema's existing Blender bridge before copying functionality. Document a specific reason for any reimplementation or shared extraction.
8. Always distinguish the intended future lightweight modeling/physics/rendering capability from today's Blender-backed research.

## Checks

```sh
python tools/validate_scene.py examples/hello_motion.json
python -m unittest discover -s tests -v
```

A Blender test is separate and requires a real locally installed Blender. Do not treat CI as Blender acceptance.

Code license: Apache-2.0. Keep credentials, private deployments, and machine-specific configuration out of this public repository.

## Audio/video storage policy

Do not commit audio or video files (including MP3, MP4, WAV, FLAC, M4A, OGG, MOV, WebM and equivalents), regardless of size, ownership, license, or whether they are generated demos or test samples. This also prohibits Git LFS pointers, renamed/encoded media and media hidden inside archives. Do not bypass the rule with `git add -f` or ignore exceptions.

Store media outside Git in approved artifact/media storage. Commit references, SHA-256 digests, provenance, analysis results, scripts and small text/symbolic fixtures instead. Generate temporary synthetic media during tests when needed. Licensing review does not waive this storage policy. MIDI/project data and images retain their existing repository-specific rules.

The `.gitignore` covers common audio/video extensions case-insensitively. Where installed, the `Media policy / No tracked audio or video` PR check also detects force-added files and LFS pointers by filename; it is not a content/archives scanner or a server-side push restriction. Do not rewrite history or remove external assets as part of this rule. See the [shared policy](https://github.com/flamoris-jp/flamoris-commons/blob/main/docs/repository-policy.md#121-audio-and-video-storage).
