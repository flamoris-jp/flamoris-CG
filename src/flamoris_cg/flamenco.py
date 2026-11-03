"""Bounded Flamenco 3 API adapter. No child processes, retries or Worker control.

The operator supplies the Manager URL. Job requests never supply URLs, paths,
commands, code or credentials. A lost POST response is an unknown outcome.
"""
import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from uuid import UUID


class BackendUnavailable(RuntimeError):
    def __init__(self, code="backend_unavailable", retry_after=60):
        super().__init__(code)
        self.code, self.retry_after = code, max(30, retry_after)


class SubmissionRejected(RuntimeError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _uuid(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError("invalid backend ID")
    return value


class Flamenco:
    def __init__(self, base_url, timeout=10):
        url = urllib.parse.urlsplit(base_url)
        if (url.scheme not in ("http", "https") or not url.hostname or url.username
                or url.password or url.query or url.fragment or url.path not in ("", "/")):
            raise ValueError("Manager must be a trusted HTTP(S) origin without credentials")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        # Do not send internal requests through ambient proxies or redirects.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())

    def request(self, method, path, payload=None, text=False):
        data = None if payload is None else json.dumps(payload, allow_nan=False).encode()
        req = urllib.request.Request(self.base_url + path, data=data, method=method,
            headers={"Content-Type": "application/json", "Accept": "text/plain" if text else "application/json"})
        try:
            with self.opener.open(req, timeout=self.timeout) as response:
                limit = 65536 if text else 8 * 1024 * 1024
                raw = response.read(limit + 1)
                if len(raw) > limit:
                    raise BackendUnavailable("backend_response_limit")
            if text:
                return raw.decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            retry = 60
            value = exc.headers.get("Retry-After", "")
            try:
                retry = int(value)
            except ValueError:
                try:
                    retry = int((parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
                except (ValueError, TypeError, OverflowError):
                    pass
            if method == "POST" and exc.code in (400, 401, 403, 404, 409, 422):
                raise SubmissionRejected("backend_rejected_" + str(exc.code)) from None
            raise BackendUnavailable("backend_http_" + str(exc.code), retry) from None
        except (urllib.error.URLError, TimeoutError, socket.timeout, OSError,
                ValueError, UnicodeError) as exc:
            raise BackendUnavailable() from exc

    def job_type(self):
        return self.request("GET", "/api/v3/jobs/type/simple-blender-render")

    def submit(self, payload):
        return self.request("POST", "/api/v3/jobs", payload)

    def get(self, job_id):
        return self.request("GET", "/api/v3/jobs/" + _uuid(job_id))

    def find(self, namespace, job_id):
        jobs = self.request("GET", "/api/v3/jobs").get("jobs", [])
        if not isinstance(jobs, list):
            raise BackendUnavailable("invalid_job_list")
        return [job for job in jobs if job.get("metadata", {}).get("flamoris.cg.namespace") == namespace
                and job.get("metadata", {}).get("flamoris.cg.job_id") == job_id]

    def cancel(self, job_id):
        return self.request("POST", "/api/v3/jobs/" + _uuid(job_id) + "/setstatus",
                            {"status": "canceled", "reason": "Owner requested cancellation through CG"})

    def tasks(self, job_id):
        return self.request("GET", "/api/v3/jobs/" + _uuid(job_id) + "/tasks")

    def log_tail(self, task_id):
        return self.request("GET", "/api/v3/tasks/" + _uuid(task_id) + "/logtail", text=True)
