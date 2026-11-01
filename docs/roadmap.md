# FLAMORIS-CG Roadmap

**Product goal:** script-driven objects become editable CG scenes and reusable video clips. In the long run, support lightweight modeling, physics, and rendering.

**Research goal:** investigate what changes in CG tooling when AI is a first-class collaborator, rather than a UI automation add-on. Keep hypotheses, experiments and results separate. See [AI-native research charter](ai-native-research.md).

This is a sequence of **acceptance gates**, not a delivery schedule.

| Gate | Scope | Acceptance evidence | Status |
| --- | --- | --- | --- |
| 0. Blender laboratory | Strict scene JSON, 2 primitives, translation keyframes, camera/light, native .blend and optional PNGs | Python validation + actual Blender preview / saved file check | Linux static preview + saved file + MCP image accepted; sequences remain unaccepted |
| 1. Modeling experiments | Primitive transforms, mesh editing or procedural geometry via Blender; asset references | A scene can be changed by editing only the script | Not started |
| 2. Physics experiments | Blender rigid body, gravity/contact/bounce; explicitly separate driven vs simulated motion | A controlled repeatable drop and recorded outcome | Not started |
| 3. Clip producer | Frame range/fps, validated PNG/MP4 output, optional alpha, manifest, robust errors | Kachinco can import and edit the generated clip | Not started |
| 4. Glyph/other assets | Read-only shapes and components, morphing where supported, object IDs/provenance | Same script addresses mixed shapes without copying Glyph internals | Not started |
| 5. Lightweight runtime research | Evaluate small scene/geometry/physics/render pieces vs Blender | A real clip proves benefit, portability and limits; no blanket rewrite | Not started |

## First small demonstration

Create a floor and a red UV sphere, move the sphere across a simple path, save a Blender native project, and request a preview PNG. The motion is **keyframe animation**, not physics. Then edit a keyframe and regenerate into a different output folder.

Static red/blue previews were accepted on Linux headless Blender 5.2.3 LTS on 2026-11-01; see [evidence and limits](preview-acceptance.md). Complete sequences and physical Windows rendering remain separate. Do not make CI green stand in for hardware acceptance.

## Out of scope now

- Cinema/AI film director / project-wide screenplay.
- A general-purpose Blender alternative, custom physics solver or renderer.
- Tool-spanning automatic orchestration, persistent service or Blender MCP deployment.
- Video editing/timeline responsibilities owned by Kachinco.

## Next acceptance gate after bootstrap

The static preview/observation baseline is accepted. Decide whether the next bounded experiment is modeling operations, rigid-body behavior or clip encoding; do not infer motion-sequence acceptance from a single frame.

## Research track (independent of feature milestones)

- **Now:** establish a baseline: simple scene data -> Blender output, with human-readable IDs, reproducible scripts and strict validation.
- **Later, when examples justify it:** compare semantic high-level actions to low-level operations, single-object revisions to whole-scene regeneration, and Blender-native manual edits to script-controlled changes.
- **Evaluate:** clarity of instructions, unwanted changes, ability to inspect/revise, reproducibility, safety and resource cost; document failure cases too.
- **Not yet implemented:** an AI agent planner, scene self-repair loop, production AI-native editor or autonomous rendering service.

This track studies **single CG scenes / clips**. Multi-tool project-wide planning remains Cinema's responsibility and is paused.


## 2026-11-01: saved-preview observation accepted

Linux headless static preview generation and real MCP PNG/JPEG image disclosure are now verified separately from Python CI. See [acceptance scope](preview-acceptance.md). This supersedes earlier untested-static-preview status only; other hardware/sequence/GPU milestones remain separate.

## 2026-11-01: 旧Scene Engineバックログの整理

[CG #8](https://github.com/flamoris-jp/flamoris-CG/issues/8)と[責任整理](scene-engine-scope.md)に旧Kachinco #124 / Glyph #3の対応表を記録。物理はgate 2、出力/受け渡しはgate 3、Glyph取込はgate 4、軽量実行系はgate 5の候補です。新gateや実装開始は追加せず、独立リポジトリ・全体共通schema・Cinema再開を前提にしません。Cinemaの証跡はCGの受入れを代替しません。
