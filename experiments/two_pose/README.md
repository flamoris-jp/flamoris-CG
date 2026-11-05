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

## Thumb-root overlap and a chosen hand turn — 2026-11-05

`run_thumb_turn.py --output /new/thumb-turn` keeps the earlier arm motion and
introduces a manually authored thick palm and a **separate thumb**. A selected
180-degree turn about the hand's longitudinal axis takes the back through an
edge view to the palm. This angle/depth/proportion is an authored hypothesis,
not recovered from two images. One fixed model is used throughout, rather than
substituting a mirrored hand halfway through.

Triangles are depth-buffered before drawing outlines and thumb/palm boundaries.
Dorsal thumbnail/finger cues are visible at the start; the palmar thenar arc and
selected folds appear at the end. Detail strokes are depth-tested against the
surface. Occluded lines are hidden, with no image dissolve. Opaque paint and
outline derive from the same projected surfaces. An opaque cuff connector joins
the rotating palm to the existing sleeve.

This follows drawing references discussed with Akino: the thumb base as its own
form, visible overlapping boundaries, and distinguishing palmar/dorsal details:

- https://www.proko.com/course-lesson/how-to-draw-hands-from-imagination-step-by-step
- https://www.proko.com/course-lesson/how-to-draw-hands-details-for-realistic-hands
- https://www.proko.com/course-lesson/how-to-draw-arm-bones-anatomy-for-artists/
- https://tips.clip-studio.com/en-us/articles/3278

No illustrations, assets or tutorial code were copied. The implementation is an
independent small geometry/rasterization study, not a Glyph morphing fork or a
copy of Cinema's bridge. Original reference-pose fidelity, anatomical forearm
motion, natural animation and whole-character acceptance remain unproven.

The comparison shows a fixed dorsal view without details versus the turning
hand with thumb boundaries and surface details. It changes both geometry and
ink cues; it cannot establish the isolated causal benefit of a single line.

A raw trial found up to two pinhole samples in the 3× supersampled coverage.
The final rasterizer explicitly fills enclosed pinholes with opaque skin color
and rejects holes larger than 16 supersampled samples for manual inspection.
Raw repair counts are recorded separately from remaining holes. This is a
bounded raster coverage correction, not an assertion of exact geometric
watertightness. Depth/visibility changes may still cause small popping artifacts.

Tests cover preservation of the projected hand axis during twist, cross-section
reversal, opaque connected paint in three views, hidden surface-detail strokes
in the edge view, and concave cap triangulation area. All 94 Python tests pass.
PNG/GIF/MP4 results use the Work CPU runtime; Blender rendering was not involved.

## Attach the arm to original Akino A — 2026-11-05

`run_attached_arm.py --source /input/pose-a.png --output /new/attached-arm`
composites the existing simplified turning arm onto the fixed original
illustration. Source A must be 1122×1402. The same manual arm/hand masks remove
the original image-right sleeve and hand, with a seven-pixel margin and white
background fill. A declared small flat coat patch supports the shoulder. These
are manual cleanup assumptions; original hidden coat texture/emblem is not
recovered. The other arm, face, hair and torso remain still.

The optional transparent/open-shoulder export of `render_turn` is backward
compatible with its existing opaque output. The arm's root cut-line is omitted,
then the rendered RGBA arm is transformed back into original image coordinates.
The moving shoulder is translated to the original shoulder anchor (646,590).
The original head is restored in front with a fixed manual mask. This is a
bounded scene-specific compositing order, not inferred general occlusion.

Before resizing or encoding, each frame measures changed pixels outside the
explicit arm/cleanup edit region and changed pixels within the protected head.
A shoulder-center alpha probe checks coverage. This validates isolation and
attachment coverage, not artistic seamlessness. Sleeve style mismatch and the
simplified shoulder patch remain visible review points. The endpoint is not
original pose B: only one arm moves on pose A's fixed body.

The output has 48 motion frames at 24 fps and 560×700 pixels. Its comparison
shows original A beside the attached-arm result. All 98 Python tests pass,
including alpha export, fixed shoulder registration and preservation of original
pixels/head. Actual PNG/GIF/MP4 output frames are fully decoded separately.
Image generation here is CPU compositing; no Blender render is claimed.

## Source-art finishing pass — 2026-11-05

`run_original_art_arm.py --a /input/pose-a.png --b /input/pose-b.png
--output /new/original-art` implements the four requested refinements on the
same fixed-body/image-right-arm study:

1. **Original artwork:** A's sleeve, cuff, emblem, linework and shading are cut
   out and warped with an inverse thin-plate-spline cage driven by 2D joints.
   There is no whole-frame color dissolve. The root/cap has reduced deformation.
2. **Shoulder:** the manually corrected pivot is (642,625), with an original-A
   shoulder-cap foreground patch retained. The proximal coat is anchored while
   elbow/wrist guides move. This replaces the simplified study's higher pivot.
3. **Missing clothing:** the old arm is cleared using an expanded manual mask.
   A narrow, explicit region under the arm reuses B's visible coat with manually
   matched donor coordinates; both images' hashes are retained. The surrounding
   original A, its head and cap are preserved. This is not inferred hidden art.
4. **Hand lines:** the dorsal surface uses original A and the palmar surface uses
   original B, each moved relative to its original wrist and direction. The
   surface switches at the thin edge rather than dissolving two hands. Internal
   thumb/finger/palm lines therefore come from the source drawings. An opaque
   source-derived silhouette outline is redrawn for readability after warping.

The edge-on hand uses an authored width floor of 0.16. Below width factor 0.30,
its projected silhouette is made continuous with a convex envelope and skin
color sampled from the selected original. A concealed wrist connector also uses
flat skin fill. These are declared completion assumptions, not source pixels.
Isolated cutout fragments are removed. Enclosed pinholes of at most 32 original
resolution pixels may be filled from nearest painted pixels; larger holes are
rejected for geometry inspection. Repair counts are recorded per frame.

Outputs are 48 motion frames, 24 fps, 720×900 MP4/PNG, plus a 560×700 GIF and a
comparison with original A. One reusable GIF palette avoids color-table changes
between frames and expensive per-frame palette optimization. This is CPU image
processing, not a Blender render. No model or dependencies were installed.

The current suite has 104 passing tests, including input/time bounds, identity
preservation of original sleeve colors, fixed cap/pivot, original A/B hand view
selection, connected opaque paint and original/head pixel preservation on
synthetic source images. Real source-image frames are inspected separately.

Remaining artistic limits: the torso, face, hair and other arm stay fixed; the
sleeve's hidden backside reuses A rather than recovering unseen cloth; B's donor
coat is a small warped patch; the hand-view transition and extreme edge profile
can still need retouching. It is a finished **single-arm prototype clip**, not a
claim that arbitrary two drawings now yield finished full-body animation.

The source-art hand pass additionally matches its projected longitudinal length
continuously across the A/B surface switch. A regression test compares the
projected tip extents immediately before and after the switch. This avoids a
length pop caused by the two source drawings having different hand proportions.
It does not guarantee identical interior linework across those two views.

## Joint refinement: side thickness, wrist and coat seam — 2026-11-05

`refine_original_art_joints.py --a /input/pose-a.png --b /input/pose-b.png
--output /new/refined-joints` addresses three visible defects in the source-art
clip without replacing its source sleeve/hand surfaces:

- The edge-on hand now exposes a shaded side volume. Its depth is an authored
  `14*sin(pi*t)^2` original-resolution pixels, tapering to zero at the front/back
  endpoints. Source-sampled skin colors and the swept projected silhouette form
  the side. Compressed dark face rails are suppressed near the exact edge so
  they do not become multiple black outlines inside that new side surface.
- The photographed sleeve cutout's baked orange wrist oval is removed while the
  cuff fabric and dark lining remain. Its aperture is retained only as hidden
  skin-colored coverage following the cuff warp. A six-point wrist narrows from
  inside the cuff to the hand, replacing the old constant-width connector. This
  is an authored transition, not a recovered anatomical wrist cross-section.
- A donor-textured dynamic coat strip overlaps both the original body seam and
  the sleeve's moving inner edge, filling the open underarm/shoulder boundary.
  A deliberately selected unmarked fabric strip from B provides its color and
  texture. Only the exterior continuation of the coat edge is inked; internal
  overlaps remain behind the coat/sleeve. This completes unseen fabric manually.

The previous isolated-arm hole check could not detect a background slit between
arm and body. This iteration separately records unpainted samples in the new
joint band, as well as remaining closed holes, original-head preservation and
changes outside the explicit edit region. Tiny interpolation fragments are
removed and pinholes up to 32 pixels are recorded/repaired; larger holes fail.

New tests cover exposed side volume in the edge view, narrowing/non-crossing
wrist geometry, opaque cloth coverage following the arm, and joint/source
preservation in five sampled poses. All 108 Python tests pass. Output remains a
48-frame, 24-fps CPU single-arm study, not a Blender render or anatomical model.
Source-view switching and artistic seam/shading choices remain review points.
