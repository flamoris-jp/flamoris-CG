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
