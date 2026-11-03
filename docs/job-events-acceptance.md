# MCP Events experiment acceptance — 2026-11-03

## Accepted source and local integration

- 58 Python tests pass on Linux, including the original 40 render/batch tests.
  The three new POSIX installation-permission regressions are skipped on Windows.
  Notification cases cover signature bytes, callback address filtering,
  challenge failure, duplicate subscription/refresh, fresh-process state,
  late subscription, no unrequested polling, Retry-After/restart, expiry,
  unsubscribe, rotation, permanent errors and retry limits.
- LIME's installed Python 3.12 / official MCP SDK **1.30.0** exercised the actual
  gateway ASGI application and its SDK Streamable HTTP manager with an HTTP
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
The corrected administrative resume still requires the local operator; no
successful activation or real notification is claimed from these unit tests.

## Still pending: real tunnel and Work chat

The existing installed tunnel uses a protected, root-owned stdio launcher.
The installed tunnel client advertises `--mcp.server-url`,
`--mcp.extra-headers` and `--mcp.discovery-extra-headers`, supporting preparation
of a localhost HTTP target without public inbound access. A reviewed local
activation script and rollback can switch only the tunnel path and start the
optional gateway; this requires an operator's administrative action.

At inspection, ChatGPT's event-source discovery returned GitHub only; the
existing Blender connection had no discovered event catalog. Its callback URL
and signing secret must come from a real ChatGPT subscription after activation
and plugin rescan, not from an invented URL or a tool call pretending to be a
subscription.

**Not accepted yet:** production tunnel forwarding of `events/*`, a real
ChatGPT callback/challenge, a Work chat responding to a render completion,
phone/banner delivery, multiple-owner authentication, a real revoked-access
test, or live gateway/tunnel restart while an event is in flight.

The code is an optional single-owner experiment, not a claim of deployed push
notifications. Do not replace this pending record with success based only on
unit tests, a fake receiver or an HTTP 2xx receipt.
