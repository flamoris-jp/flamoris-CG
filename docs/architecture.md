# Architecture: CG script -> Blender -> clip

## Identity

**flamoris-CG** owns object-animation intent and a clip-generation experiment. Its executable scope today is a bounded, declarative JSON scene description to an offline Blender scene builder.

This is intentionally **not** Cinema's film-wide authoring/AI planner and **not** Blender's replacement.

\`\`\`text
User / AI writes a bounded object-motion spec
       |
       v
flamoris_cg.spec   (pure Python, validates input)
       |
       v
Blender adapter    (bpy, creates meshes / keyframes / camera / light)
       |
       +--> native .blend (editable experiment)
       +--> optional PNG preview or PNG frame sequence
                         |
                         +--> [future: validated MP4 / RGBA handoff]
                                      |
                                      v
                                  Kachinco
\`\`\`

No project-wide screenplay or director is required. CG can create an individual clip without Cinema.

## Prototype contract (not a final CG language)

See \`examples/hello_motion.json\`: \`schema_version\`, \`fps\`, \`duration_frames\`, \`render\`, one camera, one or more lights, and a bounded list of primitives with optional translation keyframes. Coordinates use Blender's world axes (Z up), and frames are 1-based for this **isolated laboratory format**. This is **not** the Cinema v1 Scene/Take format: do not silently pass one format to the other.

- Supported shapes: cube and UV sphere, with constant material colour.
- Supported motion: explicit location keyframes (linear interpolation).
- Supported outputs: .blend, optional preview.png and optional PNG sequence.
- Not supported: rigs, procedural glyph topology, arbitrary meshes/paths, modifiers, collision/forces, parent constraints, render farms, media encoding, existing native project imports.
- Validation: IDs unique, unknown properties rejected, bounded object count, duration, resolution and samples, finite numeric coordinates, keyframes in ascending frame order.
- Execution: trusted locally installed Blender, **new output directory**; no auto-installs or GPU selection, no calls to LIME/Flamenco/MCP.
- Limits: max 32 objects, 8 lights, 240 frames, 1920x1080 preview ceiling, 64 samples, JSON <= 256 KiB; these are trial limits, not product promises.

## Clear ownership boundaries

| Component | Responsibility |
| --- | --- |
| CG | Object-motion scripts and clip-generation request, local experiment format |
| Blender | Geometry, native simulation/rigging, material, lighting and rendering |
| Glyph | Letter shapes, glyph components, morphing and provenance |
| KineticTypo | Animated text / typographic presentation |
| Kachinco | Multi-clip timeline, audio, compositing and final edit |
| Cinema (paused) | Future project-level story, intention, scene/event plan and multi-tool orchestration |

## The long-term idea

The destination is a **lightweight modeling + physics + rendering capability** for script-driven clips. "Lightweight" does not mean a tiny Blender clone; it means a focused, useful interface where only capabilities demanded by real productions become part of the public script model.

Decide later, with evidence, which operations stay delegated to Blender, which can be executed by a portable small runtime and which need a separate backend. The data contract should not expose Blender Python directly.

## Tests and evidence

Python unit tests validate the data contract without Blender. A successful Blender preview requires a real run and inspection of \`.blend\` and PNG outputs; it is not implied by CI. When accepted, record the Blender version, output files, render device, exact command and visible result. See [roadmap](roadmap.md).
