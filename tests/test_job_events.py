"""Notification acceptance without ChatGPT/network or Blender execution."""
import base64
import hashlib
import hmac
import json
from pathlib import Path
import socket
import sys
import unittest
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"src"))
from flamoris_cg.job_events import (JobEvents, EVENT, CallbackError, callback_address,
                                   signing_key, signed_headers)
import test_render_jobs as fixtures


class Receiver:
    def __init__(self):
        self.calls = []; self.status = 204; self.retry = None; self.bad_challenge = False

    def __call__(self, url, body, headers):
        self.calls.append((url, body, headers))
        value = json.loads(body)
        if value.get("type") == "verification":
            return 200, json.dumps({"challenge": "wrong" if self.bad_challenge else value["challenge"]}).encode(), None
        return self.status, b"", self.retry


class EventTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.RenderJobTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.jobs = self.fixture.api
        self.clock = self.fixture.clock
        self.receiver = Receiver()
        self.events = JobEvents(self.jobs, "operator", self.receiver, self.clock)
        self.job = self.fixture.submit()
        self.params = {"name": EVENT, "arguments": {"job_id": self.job["job_id"]},
            "delivery": {"mode": "webhook", "url": "https://receiver.example/callback",
                         "secret": "whsec_" + base64.b64encode(b"x"*32).decode()}}

    def subscribe(self):
        return self.events.subscribe(self.params)

    def complete(self, status="completed"):
        return self.fixture.complete(self.job, status)

    def test_signing_known_message_and_rotation(self):
        sub = {"id": "sub_1", "secret": self.params["delivery"]["secret"]}
        body = b'{"a":1}'
        headers = signed_headers(sub, body, "evt_1", 123)
        expected = base64.b64encode(hmac.digest(b"x"*32, b'evt_1.123.{"a":1}', "sha256")).decode()
        self.assertEqual(headers["webhook-signature"], "v1,"+expected)
        for invalid in ("x", "whsec_bad", "whsec_"+base64.b64encode(b"short").decode()):
            with self.assertRaises(ValueError): signing_key(invalid)

    def test_reconnect_and_duplicate_refresh_deliver_once(self):
        first = self.subscribe()
        self.assertEqual(first["id"], self.subscribe()["id"])
        self.assertEqual(len(self.receiver.calls), 1)  # cached challenge
        self.complete()
        self.events = JobEvents(self.jobs, "operator", self.receiver, self.clock)
        self.assertEqual(self.events.tick(), {"delivered": 1})
        self.assertEqual(self.events.tick(), {"delivered": 0})
        event = json.loads(self.receiver.calls[-1][1])
        self.assertEqual(event["data"]["status"], "succeeded")
        self.assertEqual(set(event["data"]), {"job_id", "status", "finished_at"})
        self.assertEqual(self.receiver.calls[-1][2]["webhook-id"], event["eventId"])

    def test_late_subscription_observes_already_finished_job(self):
        self.complete(); self.subscribe()
        self.assertEqual(self.events.tick()["delivered"], 1)

    def test_no_progress_poll_before_due_or_without_subscription(self):
        self.clock.advance(); self.events.tick()
        self.assertEqual(self.fixture.backend.gets, 0)
        self.subscribe(); self.events.tick(); self.events.tick()
        self.assertEqual(self.fixture.backend.gets, 1)
        self.assertEqual(len(self.receiver.calls), 1)

    def test_verification_fail_leaves_no_subscription(self):
        self.receiver.bad_challenge = True
        with self.assertRaises(CallbackError): self.subscribe()
        with self.events.db() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM subscriptions").fetchone()[0], 0)

    def test_unknown_job_owner_cursor_and_ttl_rejected(self):
        original = self.params["arguments"]["job_id"]
        self.params["arguments"]["job_id"] = str(uuid4())
        with self.assertRaises(ValueError): self.subscribe()
        self.params["arguments"]["job_id"] = original
        self.params["cursor"] = "old"
        with self.assertRaises(ValueError): self.subscribe()
        self.params.pop("cursor"); self.params["ttlMs"] = 59999
        with self.assertRaises(ValueError): self.subscribe()
        with self.assertRaises(ValueError): JobEvents(self.jobs, "other", self.receiver, self.clock)

    def test_unsubscribe_and_expiration_stop_delivery(self):
        self.subscribe(); self.complete()
        params = json.loads(json.dumps(self.params)); params["delivery"].pop("secret")
        self.events.unsubscribe(params); self.events.unsubscribe(params)
        self.assertEqual(self.events.tick()["delivered"], 0)
        self.params["ttlMs"] = 60000; self.subscribe(); self.clock.advance(61)
        self.assertEqual(self.events.tick()["delivered"], 0)

    def test_429_retry_after_restart_preserves_id_body_and_updates_signature(self):
        self.subscribe(); self.complete()
        self.receiver.status = 429; self.receiver.retry = "120"
        self.events.tick(); first = self.receiver.calls[-1]
        self.clock.advance(60); self.events.tick()
        self.assertEqual(len(self.receiver.calls), 2)
        self.clock.advance(61); self.receiver.status = 204
        self.events = JobEvents(self.jobs, "operator", self.receiver, self.clock)
        self.assertEqual(self.events.tick()["delivered"], 1)
        last = self.receiver.calls[-1]
        self.assertEqual(first[1], last[1])
        self.assertEqual(first[2]["webhook-id"], last[2]["webhook-id"])
        self.assertNotEqual(first[2]["webhook-signature"], last[2]["webhook-signature"])

    def test_410_413_and_redirect_are_never_retried(self):
        self.complete()
        for status in (410, 413, 302):
            self.params["delivery"]["url"] = "https://receiver.example/callback/"+str(status)
            self.subscribe(); self.receiver.status = status
            self.events.tick(); self.clock.advance(200); self.events.tick()
        self.assertEqual(len(self.receiver.calls), 6)
        with self.events.db() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM outbox WHERE state='failed'").fetchone()[0], 3)

    def test_retry_attempt_cap(self):
        self.subscribe(); self.complete(); self.receiver.status = 503
        for _ in range(8): self.events.tick(); self.clock.advance(601)
        self.assertEqual(len(self.receiver.calls), 6)  # one challenge + five sends

    def test_long_retry_after_is_not_shortened_by_local_backoff_cap(self):
        self.subscribe(); self.complete(); self.receiver.status = 429; self.receiver.retry = "7200"
        self.events.tick()
        with self.events.db() as db:
            self.assertEqual(db.execute("SELECT next_at FROM outbox").fetchone()[0], self.clock()+7200)

    def test_both_keys_signed_during_rotation(self):
        self.subscribe()
        self.params["delivery"]["secret"] = "whsec_"+base64.b64encode(b"y"*32).decode()
        self.subscribe(); self.complete(); self.events.tick()
        self.assertEqual(len(self.receiver.calls[-1][2]["webhook-signature"].split()), 2)

    def test_failed_is_terminal_event(self):
        self.subscribe(); self.complete("failed"); self.events.tick()
        self.assertEqual(json.loads(self.receiver.calls[-1][1])["data"]["status"], "failed")

    def test_canceled_is_terminal_event(self):
        self.subscribe(); self.complete("canceled"); self.events.tick()
        self.assertEqual(json.loads(self.receiver.calls[-1][1])["data"]["status"], "canceled")


class AddressTests(unittest.TestCase):
    def resolve(self, *addresses):
        return lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (x, 443)) for x in addresses]

    def test_https_only_and_reject_all_mixed_private_dns(self):
        for url in ("http://example.com/x", "https://a:b@example.com/x", "https://example.com:444/x",
                    "https://example.com/#fragment", "https://example.com/\r\nx"):
            with self.assertRaises(ValueError): callback_address(url, self.resolve("8.8.8.8"))
        for address in ("127.0.0.1", "192.168.1.1", "169.254.169.254", "::1", "::ffff:127.0.0.1", "0.0.0.0"):
            with self.assertRaises(ValueError): callback_address("https://example.com/x", self.resolve("8.8.8.8", address))
        parsed, address = callback_address("https://example.com/x?q=1", self.resolve("8.8.8.8"))
        self.assertEqual((parsed.hostname, address), ("example.com", "8.8.8.8"))


if __name__ == "__main__":
    unittest.main()
