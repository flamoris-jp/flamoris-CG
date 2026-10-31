# CG saved-preview acceptance — 2026-11-01 JST

Scope: one headless CG scene/clip, bounded image processing and MCP disclosure.
This is not generic Blender modeling, a new renderer, full animation acceptance,
a Hub deployment, a screen capture port, or a Cinema restart.

## Observed end-to-end evidence

- Blender 5.2.3 LTS, background mode, Cycles **CPU**, two CPU threads.
- Existing `hello_motion.json` contract: 640x360, 72 frames, 24 fps; 8 samples.
- Run the existing builder with `--background --factory-startup --disable-autoexec
  --threads 2 --python-exit-code 1 --python blender/build_scene.py -- --spec
  <spec.json> --output <new-root>/clip-red --preview`.
- A red sphere over a dark floor rendered at frame 36. PNG existed alongside
  editable `.blend` and manifest; the render took about 4.3 seconds.
- A second spec changed the sphere to blue and adjusted the camera. A distinct
  `clip-blue` directory was created, leaving the red output intact; about 4.4 s.
- Published self-contained CG stdio adapter ran on the same Linux machine.
  The official Python MCP client initialized, discovered and invoked `preview.get`.
  Core's real same-user pipe/stdio path returned text + **image** content.
- Red result: PNG 640x360, 155867 bytes, output SHA-256
  `3171cccbea448ad9c6aa50929cb0d3ecca7613699e733dda113e661dcb3a0ca7`.
- Blue result: JPEG 480x270, 3488 bytes, output SHA-256
  `0fbf7fdfda9853582cbbadad97a8ea8a72615f63ee32b72d13f762d0e215366b`.
- Both image blocks were forwarded through the existing Blender MCP connection
  and displayed/visually inspected in ChatGPT. Red/blue sphere, faceting, dark
  floor and separated shadow were visible. This is direct observation, not
  success inferred from file paths or JSON metadata.

Rendered spheres are visibly faceted and the scene is dark. Those are properties
of the existing low-sample lab spec/materials, not an image-transfer failure.
No lighting/modeling quality claim is made. No image assets are checked into Git.

## Verification boundaries

Linux .NET 10.0.403 / runtime 10.0.14 executed seven portable imaging cases and
eight CG boundary cases successfully. Existing Capture tests: 34 passed, one
optional external-bridge test skipped without its separately published bridge.
Windows/Linux CI additionally runs the new imaging matrix and CG boundary tests;
Windows Capture's existing complete build/platform suite remains the regression
gate. Python scene-contract tests: eight passed without Blender.

Portable cases include real decoded pixels, alpha/JPEG matte, ROI, hashes,
corruption, input bounds, incompressible output caps and cancellation. CG cases
include traversal, unknown/null/duplicate JSON, symlinks on Linux, missing/stale
artifacts, malformed manifest, revocation, small envelopes and separate clip IDs.
The actual stdio and Linux Blender observations above are separate from these
synthetic tests. A physical Windows Blender/render pass, dedicated Hub/tunnel
registration, multi-view/contact sheets, GPU selection and long jobs are not
certified here.

The installed helper requires the existing Blender MCP Python environment;
the self-contained CG executable itself requires no Python or system .NET SDK.
Host-specific paths, installation receipts and recovery notes belong in private
operations documentation, not in this public record.
