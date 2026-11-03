# MCP Events experiment acceptance — 2026-11-03

## Accepted source and local integration

- 58 Python tests pass on Linux, including the original 40 render/batch tests.
  The three new POSIX installation-permission regressions are skipped on Windows.
  Notification cases cover signature bytes, callback address filtering,
  challenge failure, duplicate subscription/refresh, fresh-process state,
  late subscription, no unrequested polling, Retry-After/restart, expiry,
  unsubscribe, rotation, permanent errors and retry limits.
- In the initial local integration, LIME's installed Python 3.12 / official MCP
  SDK **1.30.0** exercised the actual gateway ASGI application and its SDK Streamable HTTP manager with an HTTP
  test client. No public socket or production tunnel change was made.
- `initialize` returned `events`; `tools/list` preserved all **26 installed
  Blender tools** and added `cg.job_status`.
- A real read-only `get_blendfile_summary_datablocks` call went through the SDK
  stdio client to the existing persistent Blender, and job status was read.
- `events/list`, subscribe/challenge, terminal delivery, duplicate suppression
  and unsubscribe worked. The webhook receiver was an **injected test double**,
  not ChatGPT. The existing job database was consistently copied to a temporary
  fixture; test subscriptions and keys were not put into the live job authority.
- Invalid authentication, Host and an oversized body were rejected (401/403/413).
- The supervised test exited 0, the SDK closed its stdio child and the Blender
  parent had no remaining children. No Blender render/GPU job was launched by
  this acceptance.

## An unsuccessful trial and its correction

The first integration test was synchronously awaited inside the Blender MCP
instance it queried, producing a circular wait and reaching the test timeout.
It was not evidence of a render failure. The corrected trial ran the test in a
separate bounded supervisor thread so the Blender request could return before
the query. The supervisor owned a process group, killed it on timeout and
waited/reaped it. The successful trial completed in approximately one second.
The persistent Blender process and Flamenco services were not restarted.

The first administrative activation then failed before transport switching:
the code root was root-owned mode 0700 because umask 0077 reduced `mkdir`'s 0755.
Nested directories had been corrected but the root itself had been omitted.
The service's ordinary user could not discover `flamoris_cg`, and readiness
timed out. The gateway was stopped/disabled, the original tunnel stayed active
and no tunnel override was present. The installer now explicitly sets the code
root and nested directory modes, and an integrity-checked `--resume` handles the
verified partial installation. Regression tests reproduce the restrictive
umask, retain private permissions outside the code tree, and reject changed code.
The corrected administrative resume was subsequently run by the local operator
and passed readiness before switching the tunnel. Unit tests alone did not
establish that success; the real acceptance is recorded below.

## Accepted: real tunnel, ChatGPT subscription and conversation

On **2026-11-03**, the local operator completed the corrected administrative
resume. The gateway and tunnel reached active/running; the existing tunnel's
main target became the gateway's localhost HTTP endpoint, with protected headers
for ordinary and discovery requests. The persistent Blender and Flamenco were
not restarted for that switch. No public inbound port, Hub catalog change or
change to the independent Mango connection was needed. This records that
acceptance, not the services' future live status or a request to repeat activation.

After plugin rescan, ChatGPT discovered the Blender - LIME event source and
`cg.job.terminal` schema. An actual subscription supplied its callback and
signing secret and completed the signed challenge. This was not an injected
receiver or an ordinary tool pretending to subscribe.

| Evidence | Observed result |
| --- | --- |
| Accepted source | JOB layer `4e5cfbc9da8cd6a621079224676bfcc1870fd73f`; notification runtime `710a5458dc8e26cfb4b5b8f46a2541699217ae24`; installation/resume correction `159eea0ade6bb1250b9dfe24fa097e3049c678fd` |
| CG job ID | `b5d6921a-a4fd-44a7-a010-18637c024f7f` |
| Request | Registered native scene, 320x180, frame 1 only, chunk size 1; queued ID returned in approximately 0.080 s |
| Authoritative result | `succeeded`, `terminal=true`, backend steps 2/2; these are backend steps, not two rendered frames |
| Event ID | `evt_d4b7e0f63d878ff176932b85e88acbb4c2781a5a80e5f5c116e2967da0ffdf7d` |
| Durable outbox | `attempts=1`, `state=delivered` |
| ChatGPT processing | Event-triggered execution reached `completed`, checked the same job once with `cg.job_status`, and generated its success report |
| Human acceptance | Akino saw the report in the conversation and confirmed completion |

| Time (2026-11-03 JST / UTC+09:00) | Evidence |
| --- | --- |
| 22:11:39 | Job submitted |
| 22:11:47 | Flamenco completed update |
| 22:12:37 | CG terminal detection and event timestamp / payload `finished_at` |
| 22:12:43 | Event-triggered ChatGPT processing started |
| 22:13:35 | Processing completed and success report generated |

The recorded report said the tunnel notification had arrived and the one-frame
render job succeeded. Acceptance includes both the event-triggered execution's
recorded result and its visible conversation response, beyond an HTTP 2xx receipt.
The platform Automations `delivery_status` itself remained **`unknown`**; that
field is not interpreted as `delivered`. Phone/OS-banner delivery was not observed.

`finished_at` is CG's terminal-detection time, not the backend render-end time.
Status cache, worker intervals and ChatGPT processing contribute to latency;
the timing above does not mean rendering took 58 seconds or guarantee immediate
notifications. Only this exact job was subscribed, with the default one-hour
TTL and no periodic schedule. Automatic monitoring of every new job and other
applications was not configured.

## Still pending / limits of this acceptance

- Phone/OS-banner delivery; actual subscription expiry/renewal, key rotation or
  revoked-access behavior against ChatGPT; multiple-owner authentication.
- Delivery during a live gateway/service restart or tunnel disconnection.
- Long-running, GPU or many concurrent jobs, other applications, and automatic
  output-video retrieval as part of the notification path.
- Failed/canceled jobs were accepted in the earlier JOB experiment, while event
  retries, duplicates, backoff and other protocol cases have deterministic tests.
  This real ChatGPT webhook trial covered a successful job on its first delivery;
  it does not establish live retry/restart or failure/cancellation notification.

This remains an optional single-owner experiment with one accepted deployment
and one successful end-to-end job, not general notification-service certification.
Integration into GitHub main does not require reactivation, a service restart or
production configuration changes. Deployment paths and credentials remain private.
