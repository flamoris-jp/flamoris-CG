"""Single-owner MCP Events experiment; RenderJobs remains the job authority.

The outbox survives reconnect/restart. Only subscribed jobs are observed, using
RenderJobs' durable cache/backoff. No render processes or ChatGPT polling loop.
"""
import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import http.client
import ipaddress
import json
import secrets
import socket
import sqlite3
import ssl
import time
from urllib.parse import urlsplit

from .data_contract import canonical, fields
from .render_jobs import TERMINAL, checked_uuid, contained

EVENT = "cg.job.terminal"


def iso(stamp):
    return datetime.fromtimestamp(stamp, timezone.utc).isoformat().replace("+00:00", "Z")


def signing_key(secret):
    if not isinstance(secret, str) or not secret.startswith("whsec_"):
        raise ValueError("invalid signing secret")
    try:
        key = base64.b64decode(secret[6:], validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid signing secret") from exc
    if not 24 <= len(key) <= 64:
        raise ValueError("invalid signing secret length")
    return key


def signed_headers(subscription, body, event_id, now):
    timestamp = str(int(now))
    message = event_id.encode() + b"." + timestamp.encode() + b"." + body
    keys = [subscription["secret"]]
    if subscription.get("previous_until", 0) > now:
        keys.append(subscription["previous_secret"])
    signatures = ["v1," + base64.b64encode(hmac.digest(signing_key(k), message, "sha256")).decode()
                  for k in keys]
    return {"Content-Type": "application/json", "webhook-id": event_id,
            "webhook-timestamp": timestamp, "webhook-signature": " ".join(signatures),
            "X-MCP-Subscription-Id": subscription["id"]}


def callback_address(url, resolver=socket.getaddrinfo):
    if not isinstance(url, str) or len(url) > 2048 or any(ord(c) <= 32 for c in url):
        raise ValueError("invalid callback URL")
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.port not in (None, 443)
            or parsed.username is not None or parsed.password is not None or parsed.fragment):
        raise ValueError("public HTTPS callback on port 443 required")
    addresses = list(dict.fromkeys(r[4][0] for r in resolver(
        parsed.hostname, 443, type=socket.SOCK_STREAM)))
    if not addresses:
        raise ValueError("callback has no addresses")
    for value in addresses:
        address = ipaddress.ip_address(value)
        mapped = getattr(address, "ipv4_mapped", None)
        if not address.is_global or (mapped and not mapped.is_global):
            raise ValueError("callback address is not public")
    return parsed, addresses[0]


class PinnedHTTPS(http.client.HTTPSConnection):
    """Connect to a validated IP; retain original hostname for TLS and Host."""
    def __init__(self, host, address, timeout):
        super().__init__(host, timeout=timeout, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        raw = socket.create_connection((self.address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def webhook_post(url, body, headers):
    # Resolve on EVERY connection. Never use ambient proxies or follow redirects.
    parsed, address = callback_address(url)
    connection = PinnedHTTPS(parsed.hostname, address, 5)
    try:
        target = (parsed.path or "/") + ("?" + parsed.query if parsed.query else "")
        connection.request("POST", target,
                           body=body, headers=headers)
        response = connection.getresponse()
        data = response.read(8193)
        if len(data) > 8192:
            data = b""
        return response.status, data, response.getheader("Retry-After")
    finally:
        connection.close()


class CallbackError(Exception):
    """Categorical error only: never expose callback URL, secret or body."""


class JobEvents:
    def __init__(self, jobs, owner, post=webhook_post, clock=time.time):
        if not isinstance(owner, str) or not 1 <= len(owner) <= 64:
            raise ValueError("one configured owner required")
        self.jobs, self.owner, self.post, self.clock = jobs, owner, post, clock
        self.path = contained(jobs.state, jobs.state / "events.sqlite3")
        with self.db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS identity (owner TEXT NOT NULL)")
            row = db.execute("SELECT owner FROM identity").fetchone()
            if row and row[0] != owner:
                raise ValueError("event state belongs to another owner")
            if not row:
                db.execute("INSERT INTO identity VALUES (?)", (owner,))
            db.execute("CREATE TABLE IF NOT EXISTS subscriptions (id TEXT PRIMARY KEY, record TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS outbox (sid TEXT, eid TEXT, body TEXT NOT NULL, attempts INTEGER NOT NULL, next_at REAL NOT NULL, state TEXT NOT NULL, PRIMARY KEY(sid,eid))")

    @contextmanager
    def db(self):
        contained(self.jobs.state, self.path)
        db = sqlite3.connect(self.path, timeout=15)
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def catalog(self):
        return {"events": [{"name": EVENT,
            "description": "Completion, failure or cancellation of one owned CG render job.",
            "delivery": ["webhook"], "inputSchema": {
                "type": "object", "properties": {"job_id": {"type": "string", "format": "uuid"}},
                "required": ["job_id"], "additionalProperties": False},
            "payloadSchema": {"type": "object", "properties": {
                "job_id": {"type": "string"}, "status": {"enum": sorted(TERMINAL)},
                "finished_at": {"type": "string"}},
                "required": ["job_id", "status", "finished_at"], "additionalProperties": False}}]}

    def _identity(self, params, subscribe):
        fields(params, ("name", "arguments", "delivery"), ("cursor", "ttlMs") if subscribe else ())
        if params["name"] != EVENT or params.get("cursor") is not None:
            raise ValueError("unsupported event or cursor")
        fields(params["arguments"], ("job_id",))
        checked_uuid(params["arguments"]["job_id"])
        # This experiment serves one RenderJobs authority and one authenticated owner.
        # Verify exact ownership through its state, never caller-supplied paths/owner.
        with self.jobs.db() as db:
            self.jobs._row(db, params["arguments"]["job_id"])
        fields(params["delivery"], ("mode", "url", "secret") if subscribe else ("mode", "url"))
        if params["delivery"]["mode"] != "webhook":
            raise ValueError("only webhook delivery is supported")
        url = params["delivery"]["url"]
        if not isinstance(url, str) or len(url) > 2048:
            raise ValueError("invalid callback URL")
        identity = canonical([self.owner, url, EVENT, params["arguments"]])
        return "sub_" + hashlib.sha256(identity.encode()).hexdigest()

    def subscribe(self, params):
        sid = self._identity(params, True)
        signing_key(params["delivery"]["secret"])
        ttl = params.get("ttlMs", 3600000)
        if type(ttl) is not int or not 60000 <= ttl <= 3600000:
            raise ValueError("ttlMs must be 60000..3600000")
        now = self.clock()
        with self.db() as db:
            # Bound retained history as well as active records.
            for key, raw in db.execute("SELECT id,record FROM subscriptions").fetchall():
                if json.loads(raw)["expires"] < now - 86400:
                    db.execute("DELETE FROM outbox WHERE sid=?", (key,))
                    db.execute("DELETE FROM subscriptions WHERE id=?", (key,))
            row = db.execute("SELECT record FROM subscriptions WHERE id=?", (sid,)).fetchone()
            old = json.loads(row[0]) if row else {}
            if not old and db.execute("SELECT count(*) FROM subscriptions").fetchone()[0] >= 64:
                raise ValueError("subscription capacity reached")
            record = {"id": sid, "owner": self.owner, "job_id": params["arguments"]["job_id"],
                      "url": params["delivery"]["url"], "secret": params["delivery"]["secret"],
                      "expires": now + ttl/1000, "active": True, "verified_at": now}
            # Cache verification only for this exact owner/URL/secret and for five minutes.
            if not (old.get("active") and old.get("secret") == record["secret"]
                    and old.get("verified_at", 0) > now - 300):
                challenge = secrets.token_urlsafe(32)
                body = canonical({"type": "verification", "challenge": challenge}).encode()
                try:
                    status, reply, _ = self.post(record["url"], body,
                        signed_headers(record, body, "msg_" + secrets.token_hex(16), now))
                    received = json.loads(reply).get("challenge", "")
                    if not 200 <= status < 300 or not isinstance(received, str) or not hmac.compare_digest(challenge, received):
                        raise CallbackError("challenge_failed")
                except (OSError, ValueError, TypeError, AttributeError) as exc:
                    raise CallbackError("verification_failed") from exc
            else:
                record["verified_at"] = old["verified_at"]
            if old.get("secret") and old["secret"] != record["secret"]:
                record.update(previous_secret=old["secret"], previous_until=now+300)
            elif old.get("previous_until", 0) > now:
                record.update(previous_secret=old["previous_secret"], previous_until=old["previous_until"])
            db.execute("INSERT OR REPLACE INTO subscriptions VALUES (?,?)", (sid, canonical(record)))
        return {"id": sid, "refreshBefore": iso(record["expires"]), "cursor": None, "truncated": False}

    def unsubscribe(self, params):
        sid = self._identity(params, False)
        with self.db() as db:
            row = db.execute("SELECT record FROM subscriptions WHERE id=?", (sid,)).fetchone()
            if row:
                record = json.loads(row[0]); record["active"] = False
                db.execute("UPDATE subscriptions SET record=? WHERE id=?", (canonical(record), sid))
        return {}

    def tick(self):
        """One bounded worker iteration; service calls this at most once per 30s."""
        now = self.clock()
        sent = 0
        with self.db() as db:
            rows = db.execute("SELECT id,record FROM subscriptions ORDER BY id").fetchall()
            for sid, raw in rows:
                record = json.loads(raw)
                if not record["active"] or record["expires"] <= now or record["owner"] != self.owner:
                    continue
                try:
                    job = self.jobs.status(record["job_id"])
                except (LookupError, ValueError):
                    record["active"] = False
                    db.execute("UPDATE subscriptions SET record=? WHERE id=?", (canonical(record), sid))
                    continue
                if job["status"] not in TERMINAL:
                    continue
                eid = "evt_" + hashlib.sha256(canonical(
                    [self.jobs.namespace, job["job_id"], job["status"]]).encode()).hexdigest()
                event = {"eventId": eid, "name": EVENT, "timestamp": iso(job["finished_at"]),
                         "data": {"job_id": job["job_id"], "status": job["status"],
                                  "finished_at": iso(job["finished_at"])}, "cursor": None}
                db.execute("INSERT OR IGNORE INTO outbox VALUES (?,?,?,0,?,'pending')",
                           (sid, eid, canonical(event), now))
            # Commit the outbox before making any application delivery.
        with self.db() as db:
            rows = db.execute("SELECT o.sid,o.eid,o.body,o.attempts,s.record FROM outbox o JOIN subscriptions s ON s.id=o.sid WHERE o.state='pending' AND o.next_at<=? ORDER BY o.next_at,o.sid LIMIT 8", (now,)).fetchall()
            for sid, eid, raw, attempts, subscription in rows:
                record = json.loads(subscription)
                if not record["active"] or record["expires"] <= now or record["owner"] != self.owner:
                    continue
                # Recheck the authority immediately before delivery. No event on unknown/error.
                try:
                    job = self.jobs.status(record["job_id"])
                    if job["status"] not in TERMINAL:
                        continue
                except (LookupError, ValueError):
                    continue
                body = raw.encode()
                try:
                    status, _, retry = self.post(record["url"], body, signed_headers(record, body, eid, self.clock()))
                except (OSError, ValueError, http.client.HTTPException):
                    status, retry = 503, None
                attempts += 1
                state = "delivered" if 200 <= status < 300 else "pending"
                if state == "pending" and (attempts >= 5 or
                        (400 <= status < 500 and status not in (408, 425, 429)) or 300 <= status < 400):
                    state = "failed"
                delay = min(600, 30 * 2**(attempts-1))
                try:
                    delay = max(delay, max(30, int(retry)))
                except (ValueError, TypeError):
                    if retry:
                        from email.utils import parsedate_to_datetime
                        try:
                            delay = max(delay, max(30, parsedate_to_datetime(retry).timestamp()-now))
                        except (ValueError, TypeError, OverflowError):
                            pass
                try:
                    next_at = now+delay
                except OverflowError:
                    next_at = float("inf")  # Never retry earlier than a huge Retry-After.
                db.execute("UPDATE outbox SET attempts=?,next_at=?,state=? WHERE sid=? AND eid=?",
                           (attempts, next_at, state, sid, eid))
                if status == 410:
                    record["active"] = False
                    db.execute("UPDATE subscriptions SET record=? WHERE id=?", (canonical(record), sid))
                sent += state == "delivered"
        return {"delivered": sent}

    def diagnostics(self):
        """Counters only; never return callbacks, secrets or event bodies."""
        with self.db() as db:
            states = dict(db.execute("SELECT state,count(*) FROM outbox GROUP BY state"))
        return {"outbox": states}
