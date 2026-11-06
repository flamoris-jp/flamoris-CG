# Original-art contour volume study

The second experiment fits the two supplied Akino hand drawings rather than
refining the generic primitive hand into an anatomical model. It is a closed
2.5D volume with original artwork on its two surfaces, manually designed depth,
and shape keys matching the two different drawn silhouettes. This is not
multi-view 3D reconstruction, an anatomical hand rig, or autonomous segmentation.

`fit_source_hand.py` records ten corresponding contour arcs. A common positive
triangulation is refined into one closed skin, with both painted sides sharing
their rim. Interior rim-to-rim chords are split to prevent non-manifold seams.
Depth has a 0.075-unit maximum half-thickness; source scale is 100 pixels/unit.
The source PNGs are user-supplied generated artwork; their hashes are recorded
in the accepted output. No third-party model or generated 3D asset is used.

```sh
python fit_source_hand.py SOURCE_A.png SOURCE_B.png NEW_MESH_DIR
blender --background --factory-startup --python build_fitted_hand.py -- NEW_MESH_DIR/mesh.json NEW_NATIVE_DIR
```

The native builder validates bounded mesh data, packs both texture crops and
exports only the new scene. Rendering uses the existing durable JOB service,
explicitly selecting `scene.json`'s scene. No Blender rendering subprocess or
service configuration is created by these builders. `mesh.json` is a trusted
operator intermediate, not an extension of the public scene/JOB API.

The camera stays on world +Z. Source A starts at -14.826 degrees in screen plane;
source B ends at +24.305 degrees. Local X runs from wrist toward fingers. A
**negative** 180-degree X roll brings the thumb's negative Y towards the viewer;
the previous generic experiment used the opposite roll. The wrist stays fixed.
The forearm and sleeve are omitted rather than rotating a rigid cuff with it.

Two preview revisions exposed a surface-paint artifact: original dark lines
stretched across the newly exposed side. The accepted material retains exact
surface artwork at either endpoint and blends it into an authored side colour
at grazing angles (absolute cosine exposure 0.12–0.52). This is an explicit
view-dependent painting rule, not recovered unseen artwork. Two shape keys
also compensate for differences between the source drawings.

`package_fitted_preview.py` takes a trusted transfer ZIP containing the completed
`render-result.zip`, `hand.blend`, `scene.json` and `build-receipt.json`. It checks
32 consecutive readable 800×600 frames and camera margin, then adds a 2-pixel
alpha-derived silhouette ink pass. The presentation plays the native 24-fps
frames at 16 fps, adds endpoint holds and reverses. Raw and inked PNGs remain
separate, and the `.blend` does not include the offline ink pass.

The resulting shape is tailored to these views. The thumb/fingers have designed
thickness but no skeletal joints or realistic webbing. Other camera directions
are unvalidated, and the 2D character-arm connection is not part of this study.
Python tests check correspondence orientation and thumb direction; acceptance
requires real Blender frames in addition to those tests.
