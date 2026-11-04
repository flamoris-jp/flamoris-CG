# One completed JOB → MP4 → isolated Kachinco test project

Status: **offline CLI implementation; real LIME/Kachinco acceptance pending**.
This is a single-clip handoff, not a completion-event subscriber or Cinema planner.
Related: [Kachinco #124](https://github.com/flamoris-jp/flamoris-kachinco/issues/124),
[CG #8](https://github.com/flamoris-jp/flamoris-CG/issues/8).

## Contract comparison and choice

Reviewed CG main `d934edf1e0bc65e4d64a45d4c4c8343adca13420`, Kachinco
`d86f862f1d15f12dc340e129559dbcbf08381e9d`, and Cinema's existing `tools/run_blender_smoke.py`.

| Existing interface | Actual contract | Decision |
| --- | --- | --- |
| CG `RenderJobs.result` / `cg.job_result` | Result ZIP with `job.json`, `diagnostics.json` and canonical `frames/NNNNNN.png`; receipt carries ZIP SHA-256. Failed jobs can also have diagnostic ZIPs; successful requests can be sparse samples. | Consume an exported ZIP, pinned by explicit JOB UUID **and** its result SHA-256. Require succeeded, retained, uncanceled, consecutive frames. Never pick latest. No ZIP means no handoff. |
| November 3 pudding production | 180 frames / 12fps → 15s H.264/yuv420p, then guarded Kachinco upload; preview, bilingual edit and export accepted in that production. | Reuse the FFmpeg image-sequence approach. That authored script used `frame_` names; it is not a durable JOB result. No implicit conversion of old loose frames to a JOB. |
| Cinema smoke encoder | Explicit image2 input framerate/start number/count, libx264, bounded threads, ffprobe verification; coupled to two fixed 1280×720/30fps/150-frame camera takes. | Compare and independently implement the small variable-JOB adapter; no Cinema schemas, render commands, scheduler or scene/take code copied. Cinema remains paused. |
| [Linux CLI](https://github.com/flamoris-jp/flamoris-kachinco/blob/main/product/Kachinco.Cli/Program.cs) `project new`, `media import SOURCE_PROJECT --source MP4 --output NEW_PROJECT` | Kachinco probes the media, executes ordinary `RegisterMedia`, saves to a new path; source project is locked, not overwritten. Import registers an asset, not a timeline clip. | **Selected path.** Only create a new empty test project, import the verified local MP4, validate and reopen through CLI. No new transport, credentials or service changes. |
| [MCP upload](https://github.com/flamoris-jp/flamoris-kachinco/blob/main/docs/decisions/0018-mcp-media-upload.md) | Edit grant plus runtime/document/revision guard on begin/write/finish/cancel. ≤512MiB; ordered ≤131072-byte chunks with SHA-256; Int64 offsets/sizes are decimal strings. Finish rehashes, probes, checks guard and registers in shared Undo/Redo. | Retain unchanged for a future remote/live-editor adapter. It requires selecting/authorizing a live document and transfer lifecycle, unnecessary for this isolated local test. Never bypass guards or encode PNGs as a purported video upload. |

The new adapter uses only Python's standard library and trusted installed FFmpeg,
ffprobe and Kachinco executables. It never parses/writes Kachinco projects to edit
them: project observations come from `project info`, mutations only from CLI.
No third-party source code, fonts, models or media are bundled.

## Two explicit operations

Run from a reviewed CG checkout on a host where these executables are already
installed. Paths below are **placeholders**, not verified deployment paths.
Use a private, durable operator directory without concurrent writers. Parent
directories must exist; each output directory must be new. Never use a service's
live project directory. These commands do not install or restart anything.

1. Select **one known completed JOB**, inspect `cg.job_status`, and obtain its
   `cg.job_result` receipt. Export/download that exact `result.zip` through the
   existing result transfer. A local operator can use
   `tools/render_jobs.py --config OPERATOR_CONFIG result JOB_UUID --export NEW_ZIP`.
   That operation collects results/diagnostics; it does not submit a new JOB.
   Do not use the local file's self-computed hash as a substitute for comparing
   the SHA-256 received from the trusted JOB result authority.
2. Prepare the MP4, using the selected UUID and receipt digest:

```sh
python tools/handoff.py prepare \
  --result /operator/results/selected-result.zip \
  --job-id SELECTED_JOB_UUID \
  --result-sha256 RESULT_RECEIPT_SHA256 \
  --output /operator/handoffs/NEW-prepared
```

3. Register it in a separate new test project through the installed CLI:

```sh
python tools/handoff.py import-test \
  --handoff /operator/handoffs/NEW-prepared/handoff.json \
  --kachinco /installed/path/to/Kachinco.Cli \
  --output /operator/handoffs/NEW-test-project
```

`prepare` outputs `clip.mp4`, `handoff.json`, FFmpeg command/version/log and the
ffprobe JSON. Temporary PNG staging is removed, while the original ZIP is never
modified. `import-test` copies the MP4 beside `empty.fkproj` and
`imported.fkproj`, records every CLI argv/result and writes `import-receipt.json`.
Keep the test directory at its original absolute location: Kachinco CLI imports
reference the absolute MP4 path. Moving the folder needs ordinary Kachinco relink.

Only a receipt with `success: true` certifies that stage. A failure keeps its own
new directory and logs for inspection, may leave an unregistered MP4 or partial
test project, and never rolls back/deletes any user's files. Inspect, then choose
a new output directory for an explicit retry. There is no automatic replay.
The CLI exits 0 on success and 2 on failure.

## Validation and preservation

- Explicit canonical JOB UUID and ZIP SHA-256. Encrypted, duplicate, symlink,
  traversal, unexpected or missing ZIP entries are rejected; compressed and
  expanded data are bounded to 512MiB. Extraction uses generated names only.
- `succeeded` is necessary, not sufficient: require 1–240 ordered consecutive
  frames and matching PNG dimensions. Sparse `[1,78,126]` is rejected instead of
  silently shortening time. A non-one start is supported. Every PNG gets a hash;
  FFmpeg must actually decode it. A plausible PNG header alone is not success.
- Even dimensions 2–1920 × 2–1080, with no implicit resize; H.264/libx264,
  yuv420p, no audio. Alpha is deliberately composited **over black**. This is
  lossy opaque video, not an alpha/colour-managed master format.
- FPS is `Fraction(str(job.scene.fps))`, preserving the registered decimal;
  no NTSC inference or frame interpolation. Exact numerator must fit Int32 and
  denominator ≤1,000,000. Existing JOB metadata has numeric FPS, not a rational
  pair: high-precision floats outside this subset fail explicitly.
- ffprobe counts decoded frames and checks declared count, average and nominal
  rational FPS, codec, pixel format, dimensions, one video stream, exact stream
  duration in MP4 timebase, container duration (≤1ms rounding) and size ≤512MiB.
  Expected duration is `frame_count / fps`, including rational seconds and exact
  `duration × 35,280,000` ticks in the receipt. No timeline tick placement occurs.
- MP4 SHA-256 is checked after encoding, before import, after copying and after
  import. `import-test` probes the copied MP4 again, and checks Kachinco's imported
  duration within 1ms (its probe reads decimal container duration).
- No existing-project input is supported. The seed is created by `project new`;
  it must contain no assets. `media import` writes a different new file. The
  source seed hash must remain unchanged. `project validate` and `project info`
  reopen the saved result and require exactly one available media asset, the
  expected local MP4 path, and unchanged project ID/name/sequences/tracks,
  authoring and generated-assets state. The seed remains available separately.
- No live editor/Hub is attached and no Undo/Redo operation is issued. Existing
  projects, assets and edit histories are outside this operation's targets.
  A saved `.fkproj` is not evidence that a live Undo stack was preserved or tested.
- The new test sequence uses the CLI's current **30fps** default. Source FPS is
  retained in the MP4/receipt. No clip is inserted; preview/export would otherwise
  be an empty timeline. Placement, sequence-rate editing, subtitles and final
  export remain ordinary later Kachinco actions.

## Code tests versus real acceptance

| Evidence | Scope |
| --- | --- |
| Portable contract tests | Rejection before mutation, JOB identity/status, unsafe ZIPs, byte budgets, sparse frames, invalid timing, header mismatch, metadata mismatch, no overwrite. |
| Real FFmpeg integration in CI/local test host | Generated 8×8 PNG fixture, 180 frames / 12fps / 15s, decoded count, hashes, fractional 23.976fps, non-one start, transparency over black, corrupt PNG failure. This is codec evidence, **not a Blender render**. |
| Simulated CLI JSON boundary | Checks exact CLI invocation order, new seed/output paths, MP4 copy, hash checks, save/reopen observations and unchanged timeline checks; detects a simulated unwanted edit. **Not actual Kachinco import acceptance.** |
| November 3 production | Earlier manual pudding render/upload/edit/export evidence; does not certify this new adapter. |
| New LIME/Kachinco acceptance | **Pending.** No LIME JOB was submitted, no production project imported, no deployment/service configuration changed for these code tests. |

Run `python -m unittest discover -s tests -v`. FFmpeg integration tests skip
when ffmpeg/ffprobe are absent; the dedicated Ubuntu workflow installs them
and executes this file with actual codecs. CLI emulation is always labelled.

2026-11-04 code-validation host: Python 3.12.14, FFmpeg/ffprobe 6.1.1;
**74 tests passed**, including 16 new handoff tests (6 real-codec/CLI-boundary
tests and 10 portable rejection/metadata/process-output tests). Both `hello_motion.json` and
`sprite_stage.json` validated; `git diff --check` passed. No installed Kachinco
CLI/.NET SDK was available on that host, so no real Kachinco import is claimed.

### Real acceptance procedure (not performed)

1. Inspect live LIME state with server-manager; locate the reviewed checkout,
   installed Kachinco CLI, FFmpeg/ffprobe and one retained completed JOB. Record
   their actual versions/paths and the result receipt. Do not infer from docs.
2. Choose a contiguous result already present; the old 180-frame loose pudding
   sequence is not automatically a JOB. The sparse three-frame JOB is ineligible.
   If no suitable result exists, present the exact scene ID, frame range, output
   budget and submit command for approval **before any new LIME JOB**.
3. Present the two handoff commands with concrete UUID/hash and fresh test paths.
   Run only the test-project path authorized here. If deployment, service changes
   or a production target become necessary, show the exact operation and wait
   for approval first; do not substitute the running production MCP document.
4. Retain `handoff.json`, both probe reports, both project hashes, CLI version,
   import receipt and before/after observations. Confirm original ZIP, original
   projects and unrelated material were unchanged. Report each failure honestly.
5. Registration/save/reopen is this slice's acceptance. Optional later timeline
   placement/preview/export needs its own recorded Kachinco commands; do not
   claim those from media-bin registration.

This makes the bed-to-CG-to-editing workflow two inspectable operations today.
An eventual MCP action can call this application layer after the isolated path
has real acceptance; automatic terminal-event import remains out of scope.
