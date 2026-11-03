"""Data-only callable facade for a trusted CLI or existing Blender MCP adapter.

This is an application API, not an MCP transport, grant or authentication layer.
Only the trusted host constructs RenderJobs with its own configuration. Remote
requests cannot register files, choose URLs/roots, prune or execute Python.
"""
from .render_jobs import fields


class JobApi:
    def __init__(self, service):
        self.service = service

    def call(self, request):
        fields(request, ("method", "params"))
        method, params = request["method"], request["params"]
        if method == "render.submit":
            return self.service.submit(params)
        if method in ("job.status", "job.cancel", "job.result"):
            fields(params, ("job_id",))
            return getattr(self.service, method.split(".")[1])(params["job_id"])
        if method == "job.list":
            fields(params, (), ("limit",))
            return self.service.list_jobs(params.get("limit", 20))
        raise ValueError("unsupported job method")
