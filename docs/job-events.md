# MCP Events: small CG completion-notification experiment

This optional **single-owner experiment** exposes one event,
`cg.job.terminal`, filtered by a required, existing `job_id`. Completion,
failure and cancellation all qualify. A terminal job that finished just before
subscription is observed as well. The notification is a wake-up: use
`cg.job_status` and the existing result API to inspect the authoritative result.
An HTTP acknowledgement does not prove that a ChatGPT task finished or that a
phone displayed a push notification.

The initial durable-render-job API and CLI remain independent of this service.
Ordinary Python tests and scene building still require no MCP dependencies.
This change does not alter the .NET read-only `preview.get` boundary.

## Boundaries and reuse

- RenderJobs owns job IDs, input/ownership checks, status and Flamenco backoff.
- Flamenco owns execution and Blender process cleanup.
- JobEvents owns subscriptions and a small durable delivery outbox. By default
  these share the local RenderJobs state root; an operator may select a separate
  private root when Blender and the notification gateway use different users.
- The official Python MCP SDK owns Streamable HTTP and its stdio client.
- The gateway forwards installed Blender MCP tools and rich results once,
  through a clean-environment SDK stdio session. It never copies Blender's GPL
  implementation, renders implicitly or retries an uncertain tool mutation.
- The Hub is not a notification database, job scheduler or internal service bus.
  No Hub source/catalog change is required by this isolated experiment.

The existing `Flamoris.Mcp.Core` 1.4.0 preview adapter was reviewed: it serves
read-only saved images on .NET, whereas the installed Blender boundary and job
API run in Python. This experiment reuses the installed official Python SDK
instead of duplicating Core's image/grant machinery or copying a transport.
Only the draft `events/*` extension absent from SDK 1.30.0 is added at the
authenticated HTTP endpoint. Generalizing it into shared MCP infrastructure
requires a subsequent review and another real consumer; no shared framework is
introduced here. Cinema stays paused.

## HTTP endpoint and tunnel

Install optional dependencies in an **isolated** environment with
`pip install '.[events]'`. The accepted local environment uses SDK 1.30.0; do not
install this pin into the Hub's MCP 2 environment. Run:

```sh
python -m flamoris_cg.event_gateway --config /private/gateway.json --port 9887
```

Set `PYTHONPATH` to this checkout's `src`, or install this package. Configuration
is trusted operator data and contains:

```json
{
  "owner": "one-local-operator",
  "jobs_config": "/private/render-jobs-config.json",
  "events_state_root": "/private/notification-state",
  "token_file": "/private/random-ingress-token",
  "upstream_command": "/trusted/clean-environment-blender-stdio-launcher"
}
```

`events_state_root` is optional, absolute, operator-only configuration. It places
`events.sqlite3` and its SQLite sidecars beneath a separately protected local
directory; RenderJobs retains its existing job database, IDs and backoff. Omit
the key to preserve the previous database location. The event directory and
database must not have symlink/reparse components. A separate path alone does
not restrict another process: apply filesystem and service permissions too.

For an existing installation, stop the gateway before switching this setting.
Back up its SQLite database consistently, including subscriptions and outbox,
and restore it into the selected private root. Merely setting a new path creates
an empty notification database and does not migrate existing subscriptions.
Retain the old database only in a protected backup; do not expose a secret-bearing
copy when making the job directory accessible to Blender. Keep the gateway's
own jobs configuration private and independently protected from Blender writes.
Verify owner identity, preserved records and startup before accepting the move.

The process sets umask 0077 and binds **127.0.0.1 only**. Every HTTP request,
including event discovery and subscription, requires the same private Bearer
token. Host/Origin checks and a 256 KiB body limit run before event handling.
The token identifies exactly the configured owner; this is not a multi-user
authorization service. Do not share this connection or attach different owners
to its credentials/state. Revoking this token at ingress stops new requests;
disable/stop the service as well to revoke existing subscriptions immediately.

The tunnel's main channel can target `http://127.0.0.1:9887/mcp` instead of its
old stdio launcher. Configure the ingress Authorization header for both normal
and discovery requests using a protected file. Keep the tunnel control-plane
credential isolated from the gateway and Blender. The gateway's SDK child is
closed and reaped on shutdown. Do not silently change an existing tunnel or
restart the persistent Blender scene. Prepare a reviewed service override and
rollback before an operator switches transports.

The code directory itself and its subdirectories must have explicit mode 0755;
`mkdir(mode=0755)` alone becomes 0700 under the installer's umask 0077. Code
files use 0444; private state/configuration and tokens retain their private
permissions. After a failed initial installation, `--resume` validates the exact
root-owned installed file set and hashes, original gateway unit and unchanged
tunnel baseline before correcting code traversal modes and repeating readiness.
It refuses changed code, different ownership, symlinks, unexpected files or an
existing tunnel override; it does not overwrite an installed code version.

The tunnel client remains running to accept MCP calls; the gateway remains
running to observe jobs and deliver events even when no chat tool call is
active. A disconnected tunnel prevents subscription renewal and future tools;
an already-stored subscription can still send its outbound HTTPS notification
until expiry if the gateway is running. Neither a new inbound firewall port nor
a public LIME listener is necessary.

## Event protocol

`initialize` advertises `capabilities.events`. On the same authenticated `/mcp`
endpoint:

| Method | Behavior |
| --- | --- |
| `events/list` | Return the one event and its input/payload schemas |
| `events/subscribe` | Validate one owned job, verify callback, persist subscription |
| `events/unsubscribe` | Idempotently stop the exact owner's subscription |

Subscribe using `name: "cg.job.terminal"`, `arguments: {"job_id": "<UUID>"}`,
and the `delivery` supplied by ChatGPT (`mode`, HTTPS `url`, `whsec_` secret).
The optional `ttlMs` is 60000..3600000; default one hour. Only `cursor: null` is
accepted; historical replay is not advertised. Subscription identity hashes the
configured owner, callback URL, event name and canonical arguments. Refresh is
idempotent, expires explicitly, and caches successful verification for five
minutes for the same secret. A rotated secret is verified and both keys sign
during a five-minute transition. At most 64 retained subscriptions are accepted;
expired history is collected during subscription after 24 hours.

The callback must echo a signed fresh challenge before activation. HTTPS
delivery validates all DNS addresses on each connection, rejects local/private
addresses including mapped IPv4, connects to the validated address with the
original TLS hostname, ignores ambient proxies, and follows no redirects.
The application HTTP socket timeout is five seconds; name resolution uses the
host resolver and its timeouts. Callback failure returns a categorical error,
never URLs, keys, bodies or raw network exception messages.

Each event contains a deterministic `eventId`, event name, occurrence timestamp,
`cursor: null`, and data containing only job ID, terminal status and finish time.
Signatures use Standard Webhooks HMAC-SHA256 over the exact serialized bytes.
The outbox commits before sending, retains its event ID/body across retries,
and uses a fresh signing time for each attempt. Delivery is **at least once**:
a crash after receiver acknowledgement but before the database commit can cause
a duplicate, so consumers must deduplicate by event ID.

One worker iteration starts at most every 30 seconds and observes only subscribed
jobs. RenderJobs' own durable `next_poll_at`/Retry-After remains authoritative.
At most eight deliveries are attempted per iteration, with no more than five
attempts per event. Retry delays are exponential (30..600 seconds), extended by
Retry-After without shortening a longer server-requested delay. Expired
subscriptions do not deliver. 410 disables the subscription; 413, redirects and
permanent 4xx errors are not retried. The worker sends no progress spam and
never calls ChatGPT tools or an OpenAI inference API.

## Acceptance and further deployment

On **2026-11-03**, the LIME operator activated this gateway and switched the
existing tunnel to its private HTTP target. After plugin rescan, a real ChatGPT
subscription verified its signed callback; one 320x180, one-frame job reached
`succeeded`, its terminal event woke ChatGPT, and `cg.job_status` was checked
before a success report appeared in the conversation. This was an actual
end-to-end acceptance, separate from the injected receiver used below. See the
[acceptance record](job-events-acceptance.md) for timing and remaining limits.
Phone/OS-banner delivery and live restart/disconnection delivery are unverified.
The platform's `delivery_status` remained `unknown`; it is not rewritten as
`delivered` based on the gateway's outbox acknowledgement.

The commands and switching guidance below are for explicit tests or a reviewed
new deployment. They are not instructions to reactivate an accepted installation
or repeat its tunnel switch. This source integration requires no LIME restart
or production configuration change.

Run standard tests:

```sh
python -m unittest discover -s tests -v
```

With the optional SDK installed, test HTTP/stdio routing, an existing owned
terminal job, challenge handling and the outbox using an explicit fake receiver:

```sh
python tools/test_event_gateway.py --config /private/gateway.json --job-id <owned-terminal-UUID>
```

This helper copies the SQLite authority consistently into a private temporary
fixture, invokes one read-only upstream Blender query, and removes the fixture
on completion. Do not synchronously wait for this helper **inside the same
Blender instance it queries**: that makes a circular wait. Run it from a shell
or a separately supervised, bounded test process. SDK context shutdown reaps
its stdio subprocess; a supervising process must also own timeout cleanup.

After switching the actual tunnel, rescan the existing plugin so ChatGPT learns
`events` and `cg.job_status`. Discover its real event source/connector ID, then
subscribe to one exact job and specify the response on completion. Never invent
a callback URL/signing secret, use ordinary tools as a pretend event subscription,
or substitute hourly polling for this event-driven acceptance. Only an actual
ChatGPT subscription, signed callback acceptance and a responding Work chat can
establish end-to-end success. See [acceptance record](job-events-acceptance.md).

Protocol reference: [OpenAI MCP Events](https://developers.openai.com/plugins/build/mcp-events).
Tunnel reference: [Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels).
