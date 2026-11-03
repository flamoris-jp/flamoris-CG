# Render job acceptance — 2026-11-03

This separates source tests, actual rendering and untested operational scenarios.
Related: [CG #12](https://github.com/flamoris-jp/flamoris-CG/issues/12).

## Incident diagnosis

The original 2.5D production spawned background Blender and Python children from
the persistent Blender MCP process and returned from each launch. It was **not**
one synchronous MCP call that held the entire 10-minute render. The Work turn
continued through status queries, many segmented artifact transfers and encoding.
Some Code-mode waits used one-second yields repeatedly. These are not identical
to one-second Manager progress polling; local encoding used a one-second file
watch that did not call ChatGPT.

Two exited children remained as Z (zombie), both with exit code 0 when reaped.
They were specifically reaped by their actual parent with nonblocking waitpid;
no running job, shared Worker or service was stopped. The new CG job layer has
no child-process launch path. Short preparation CLI children are explicitly
waited; rendering is delegated to existing Flamenco.

ChatGPT Too Many Requests was reported by the user. The originating request,
rate-limit headers and account/platform logs were unavailable. Frequent waits
and numerous transfer calls are plausible contributors, **not a proven cause**.
The new API reduces backend polling, returns a next-check hint, stops polling on
terminal status and produces one bounded result ZIP. It cannot enforce the
ChatGPT-side caller's request pacing or guarantee that no platform 429 occurs.

## Source verification

- Python 3.12: **40 tests passed** including the existing scene and 2.5D contract tests.
- Examples validate; py_compile and git diff --check passed.
- Covered: return-before-render, duplicate/conflicting request IDs, concurrent
  admission, reconnect with durable IDs, lost POST response and unique metadata
  reconciliation, ambiguous outcome, unknown ID, backend unavailability / 429,
  cached status across reconstructed clients, Retry-After including >1 hour,
  owned/idempotent cancel and cancel backoff, changed input, output completeness,
  symlink containment, quota, explicit retention tombstones and data-only API.
- Batch tests cover supported edits, input preservation, all-or-nothing failure,
  unknown object and arbitrary-Python rejection.
- Windows/Linux CI is a separate check; do not infer its outcome from local tests.

## Actual Linux / Blender / Flamenco acceptance

Environment: existing Flamenco Manager + Worker **3.9.3** and Blender **5.2.3 LTS**.
No reinstall, runtime handoff, Worker stop, Manager restart, global GPU setting or
service mutation. Test snapshots use a tiny Cycles CPU profile, 320×180, 2 samples,
two render threads. Native preparation always creates new outputs.

| Scenario | Observed result |
| --- | --- |
| Data edit batch | Position, colour and render settings validated together; one short Blender build generated an editable native file with batch receipt |
| Submit / independent execution | 24 frames submitted in **0.0279 s**, returned queued before completion; Flamenco completed the job about 29 s after submission |
| Same request replay | Returned the original CG job ID; no new submission |
| Reconnect | A new API object and a separate Python CLI process both retrieved the same succeeded backend job; CLI exited 0 |
| Success result | 24 exact requested PNG files verified, diagnostics ZIP collected: 1,376,498 bytes; SHA-256 `3841f9d29b2878d538556936ada80a8340b6b19dc22c2611b048c7b4309101e9` |
| Cancel | A queued 72-frame request acknowledged cancellation in **0.0209 s**; later observed canceled with zero completed steps; diagnostics ZIP available |
| Render failure | An explicitly corrupt owner-created native fixture was submitted; Flamenco marked failed, and the CG API returned a failure record plus diagnostic/log ZIP |
| Existing 2.5D native scene | Packed snapshot of the earlier pudding clip rendered frames **1, 78, 126** through Flamenco; all three verified and the actual frame-78 image was retrieved and visually inspected |
| 2.5D result | ZIP 295,691 bytes; SHA-256 `8260c114466c2ce300c9d96e44a1a9c09274ff05c0295405f69d509bee0f182e` |

The actual frame-78 PNG retained the room, two human sprites, Chipsy, table and
pudding composition. This is rendering/integration acceptance, not new character
animation work. The original production was not overwritten.

An initial negative fixture used a nonexistent scene name but the backend still
reported completed and rendered an image. This was **not counted as failure-path
acceptance**. Therefore scene-name metadata alone is not proof of actual scene
selection; the trusted native preparation explicitly selects and saves the scene
before registration. Arbitrary hand-written registration metadata is an operator
declaration, not inspection or a safe way to render unknown files.

Flamenco created a preview MP4 in addition to requested PNGs. The CG result
collector deliberately excludes that unverified extra. `steps_total` included an
additional preview-video step; it is not labelled as rendered-frame progress.

## Reuse decision

Flamenco was already installed, reachable and had an awake Worker. Its actual
OpenAPI schema and live `simple-blender-render` ETag were inspected. It already
owns persistent scheduling and process lifetime, so a new CG render daemon would
duplicate responsibility. The adapter uses its existing jobs/type/jobs/status/
setstatus/task-log API. The paused Cinema adapter was a data-only job proposal,
without submission, retry, persistence or cancellation; it was compared but not
copied or resumed.

## Limits of acceptance

- No live Manager/Worker stop or host reboot was performed. Unavailable/restart
  client recovery is tested with persisted state and a simulated backend; real
  farm restart behaviour still belongs to Flamenco operational acceptance.
- Queued cancellation was tested live. Cancellation during an active render is
  covered at the adapter state-machine level, not a claim that every Blender
  driver/render backend always stops immediately.
- This is a CLI + callable application API reachable through the existing trusted
  Blender MCP execution surface. Dedicated Hub catalog tools and push-completion
  notifications have not been installed.
- Large output collection remains a bounded synchronous operation. This slice
  does not implement a generic archive scheduler or a universal cross-app queue.
- No dedicated per-application VRAM ownership, arbitrary asset ingestion, native
  round-trip, auto-resume, full .blend sandboxing or new 2D acting is claimed.

Reference APIs: [Flamenco API](https://flamenco.blender.org/development/flamenco-api/)
and [built-in job types](https://flamenco.blender.org/usage/job-types/builtin/).
