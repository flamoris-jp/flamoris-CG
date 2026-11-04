# Two-pose interpolation laboratory

A controlled offline experiment requested by Akino: start with two generated
character drawings and calculate intermediate poses. This is a standalone
research script, not a production scene API, automatic animation system, or
Blender renderer. Existing CG scene, JOB, preview and handoff paths are untouched.

## Inputs and provenance

The two 1122×1402 Akino illustrations were generated earlier in the same user
session and supplied for this experiment. No external model/code/assets were
introduced. Images are **not committed**. The annotation contains 82 manually
estimated character landmarks plus eight stationary image-border anchors.
`layers_akino.py` contains eight manually cut regions. The annotation generator
can reproduce the committed landmark JSON, but it does not detect any points.
Left/right always mean **image side**, not anatomical side.

The observations use the source drawings at their existing shared canvas size;
no pose-dependent scale alignment was applied. Display copies are uniformly
resized to 480×600. Input hashes are in the run reports.

## Reproduce

Python 3.11+, optional `two-pose-lab` dependencies, and explicitly installed FFmpeg
with libx264 are required. No script installs anything or accesses the network.
Do not install these optional libraries into the existing Blender MCP service.
Use your own selected paths for the images and new output directories:

```sh
python -m pip install '.[two-pose-lab]'
python experiments/two_pose/run.py --a /input/pose-a.png --b /input/pose-b.png --landmarks experiments/two_pose/akino_landmarks.json --output /new/full-mesh --width 480
python experiments/two_pose/run_layered.py --a /input/pose-a.png --b /input/pose-b.png --landmarks experiments/two_pose/akino_landmarks.json --output /new/layered --width 480
python -m unittest discover -s tests -v
```

Existing output directories are rejected. Each script is bounded to 2–120
frames and width 128–1122 pixels. Annotation data contains coordinates and bone
connections only, with unknown fields, nonfinite values, duplicates and
out-of-canvas points rejected. CLI file paths are explicit trusted operator input;
this laboratory format must not be exposed directly as an MCP write API.

## Compared methods

1. **Fade:** ordinary unaligned image dissolve, the visual control condition.
2. **Full-image mesh:** one fixed midpoint Delaunay mesh, inverse barycentric
   sampling and aligned texture dissolve. The topology stays fixed across time.
3. **Layered smooth warp:** head, torso, two arms, two hands and two legs each use
   a thin-plate-spline inverse displacement field, premultiplied alpha and a
   manually fixed stacking order. The overlay triangles are diagnostic drawings;
   they are **not** used to rasterize the smooth-warp output.

The third method was added after actual inspection showed severe torso/arm
tearing in method two. It does not copy Cinema's Blender bridge or Glyph's
morphing code: neither owns a matching raster character-pose experiment.
Existing generic raster geometry, SciPy and Pillow are used instead.

## Observed outcome — 2026-11-04

The full mesh has 90 points, 170 triangles and up to **10 inverted/degenerate
triangles** over 101 sampled interpolation times. It can move the face but tears
around arms, fingers and crossed clothing. This is an unfavorable result for
using a single unrestricted mesh on this input pair.

The layered output visibly moves the head, hands, torso and feet with less
whole-body tearing. However it still has double contours, stretched sleeves,
softened fingers and doubled badge letters. It is **not accepted as finished
animation**. No automatic point matching, vector line extraction, line redraw,
bone-length constraint, 3D reconstruction or physical body-turn angle was proven.

Endpoint frames explicitly use the original resized images, so exact endpoints
are not evidence that the cutouts reconstruct the originals perfectly. Without
that override, mean absolute RGB errors are 2.342 for A and 3.191 for B (0–255).
This small whole-image average includes a large white background and must not be
interpreted as a quality score. Endpoint transitions may reveal mask seams.

A small **flat coat-colored patch** was manually placed beneath B's left fist to
avoid carrying that hand into the torso layer. It is an explicit disocclusion
assumption, not inferred hidden artwork. The stacking order and all masks are
manual assumptions too. Local `linear_baseline_max_folds` values describe the
discarded per-layer triangle rasterizer, not a no-fold guarantee for TPS.

Screen-space measurements from manual landmarks, original pixels:

| Measurement | A | B | Change |
| --- | ---: | ---: | ---: |
| Eye-line angle from image +X, +Y down | −5.389° | −10.505° | −5.116° |
| Shoulder-line angle | 0.886° | 0.944° | +0.058° |
| Neck-to-waist angle | 98.076° | 81.783° | −16.293° |
| Image-left wrist position | (320, 592) | (524, 666) | (+204, +74) px |
| Image-right wrist position | (770, 831) | (806, 522) | (+36, −309) px |

These are drawing measurements, not recovered anatomical rotations.

## Validation and runtime boundary

- 82 Python tests passed, including eight additional optional lab tests for
  spatial pixel movement, no-crack identity, endpoint preservation,
  premultiplied-alpha translation, malformed annotations and PNG round-trip.
- 24 pose frames at 24 fps make a one-second A→B clip. A comparison loop adds
  endpoint holds and a reverse pass (70 frames, 2.917 seconds).
- Every output PNG was decoded; both delivered MP4s were fully decoded using
  FFmpeg. Animated GIF was decoded through all stored frames (identical endpoint
  holds can be consolidated by the GIF encoder).
- Images were calculated with the Work CPU Python runtime. Version details are
  recorded in the baseline report. **No Blender image render was performed.**
- LIME Blender 5.2.3 LTS / NumPy 2.3.4 independently calculated the same 24 geometry
  frames and reproduced 90 points / 170 triangles / 10 maximum folds. All values
  were finite and endpoints exact. This was numerical verification only, without
  modifying the open scene. LIME's system Python had Pillow but lacked NumPy and
  SciPy, so no packages were installed into it.

Next useful experiment: explicitly correspond **outline strokes** for one arm
and its hand, redraw the intermediate contours, and compare with the same pixel
warp. That isolates the remaining line/gesture problem before expanding scope.

## Follow-up: outer stroke morph, without paint or dissolve

`run_outline.py` thresholds dark/color foreground, closes small gaps, fills holes
and selects the largest connected silhouette. ContourPy traces that actual
silhouette. Seven manually chosen exposed anchors split each closed contour into
matching arc-length segments. 1,200 matched coordinates interpolate across 24
frames; every frame redraws one unfilled dark stroke of constant width. SVGs
retain the exact intermediate vector coordinates. No source-color pixel warps,
alpha dissolve or endpoint-image substitution are used in this experiment.

```sh
python experiments/two_pose/run_outline.py --a /input/pose-a.png --b /input/pose-b.png --output /new/outline
```

Observed: the outer stroke stays visible throughout the motion. This only tests
the **exterior silhouette**: it does not include face lines, garment seams, or
B's fist inside the body silhouette. Finger details can simplify; correspondence
and straight-line motion can still deform limbs. Constant stroke visibility is
not proof of natural animation, correct anatomy, or no self-intersections.

## Composite the existing color and outline frames

`composite_outline.py --color /color-run/layered --outline /outline-run/frames
--output /new/composite` multiplies matching 24-frame RGB images, preserving the
white-backed stroke without adding another warp. The side-by-side video shows
the colored render and its overlay. Actual inspection shows a stronger outer
stroke, but color/outline edges disagree at intermediate poses, especially around
arms and the coat. Their correspondence methods differ; this is a literal
composition comparison, not a registered or repaired animation. All produced
PNG, GIF and MP4 frames were decoded for validation.

## Joint-driven single-arm redraw — 2026-11-05

`run_joint_arm.py --output /new/joint-arm` is a separate, deliberately simplified
redraw of the **image-right arm only**. Shoulder/elbow/wrist measurements come
from the same manual key-pose annotations. Shoulder and forearm angles follow
the shortest 2D angular interpolation, projected bone lengths interpolate, and
the hand contour changes in its own rotating coordinate frame. This is not a
recovered 3D palm rotation or a fixed-length anatomical rig.

One closed sleeve polygon and one closed hand polygon each generate **both** the
paint mask and constant-width stroke. Opaque shading is clipped to that same
mask. An opaque convex connector behind the cuff joins the palm and sleeve.
This avoids the disagreement produced by separately morphed color and exterior
silhouette. The connector was enlarged to the convex hull of cuff/hand-root
vertices after an initial run exposed 1–3 unpainted pixels at two wrist poses.

The result is hand-authored flat-color artwork, not faithful recovery of the
original coat shading, emblem, hand detail or texture. It is detached from the
body, with no full-character occlusion handling. SVGs preserve base geometry and
colors; PNGs additionally include clipped shading and palm crease strokes.

Validation includes endpoint joint positions, angular rather than straight-line
wrist motion, sampled polygon crossings, connected fill, holes and opaque
interior pixels. The complete Python suite now contains 90 passing tests.
A 48-frame/24-fps CPU output and an angle-control comparison are provided; this
is not a Blender render or full-character acceptance. A common stroke/fill
boundary removes the previous *registration* mismatch within this small redraw,
while natural motion and fidelity remain separate evaluation goals.
