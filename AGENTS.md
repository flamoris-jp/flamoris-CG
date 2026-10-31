# AGENTS.md

FLAMORIS-CG is a **script-driven CG clip producer**, a sibling of KineticTypo. **Cinema is paused** and owns any future work of film-wide scripts, project-wide intent and orchestration; do not revive it or create a duplicate AI director here. Read README and docs/architecture.md before editing.

## Current stage

This is an **experimental Blender lab**, not a shipped CG engine. The small strict JSON spec and Blender builder have not been accepted on Blender hardware yet. Never claim a successful Blender render from a passing Python test.

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

\`\`\`sh
python tools/validate_scene.py examples/hello_motion.json
python -m unittest discover -s tests -v
\`\`\`

A Blender test is separate and requires a real locally installed Blender. Do not treat CI as Blender acceptance.

Code license: Apache-2.0. Keep credentials, private deployments, and machine-specific configuration out of this public repository.
