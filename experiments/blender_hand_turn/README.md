# Blender palm-turn study

A real, small Blender mesh test following the two-pose 2D arm experiments.
The scope is one hand turning from its back through an edge view to its palm.
This does not extract or texture the source drawing and is not yet integrated
with the character's 2D sleeve.

## Authored scene

- Palm, thenar volume, separate thumb, four fingers, wrist and cuff.
- Fingernails on the back; three surface-projected curves on the palm.
- Rotation around the hand's longitudinal X axis, 0–180 degrees at frames 1–24.
- Orthographic camera, transparent 640×360 PNG, 24 fps, Cycles CPU, 8 samples.
- Geometry, materials and lighting are authored here; no third-party model,
  texture or font is embedded in the native scene.
- The presentation labels use system DejaVu Sans, not bundled font bytes.

Build with Blender's trusted operator CLI, into a new directory:

```sh
blender --background --factory-startup --python build_hand.py -- --output NEW_DIR
```

The builder saves a native snapshot and a compact `hand-only.blend` containing
only this scene and its dependencies. It preserves the active scene and does
not start rendering. Long renders must use the repository's durable render-JOB
workflow documented in `docs/render-jobs.md`, selecting `scene.json`'s scene.
Never send this Python through the declarative scene API.

Package a trusted transfer ZIP containing `render-result.zip`, `hand-only.blend`
and operator receipts with:

```sh
python package_preview.py transfer.zip NEW_PREVIEW_DIR
```

This optional offline presentation step needs Pillow and ffmpeg. It verifies
24 readable frames, 640×360 dimensions and at least 12 pixels of camera margin.
The preview plays the 24 native frames at 12 fps, holds each endpoint and reverses
for an easily inspected loop; the native animation remains 24 fps.

## Acceptance and limitations

Accepted on LIME Blender 5.2.3 LTS through the existing Flamenco worker. The first
render exposed a camera crop and raised palm curves; the accepted revision widens
the camera and uses dense surface projection rather than sparse Bezier handles.
The complete native frame sequence must be inspected independently of unit tests.

The model uses intersecting separate meshes, without a fused anatomical skin or
finger rig. This can show seams at the finger bases. The cuff rotates with the
hand; anatomical forearm pronation and a fixed sleeve connection are not modeled.
The scene establishes visible volume and depth occlusion, not a finished anime
hand or fidelity to the original drawing. Further work is source-matched shape,
toon contours, a connected wrist and integration with the 2D arm.
