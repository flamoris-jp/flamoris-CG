"""Optional single-owner HTTP experiment beside the installed Blender MCP.

Official Python SDK owns HTTP MCP and the stdio client; this adapter adds the
draft Events extension missing from the pinned SDK. No Blender code is copied.
Do not put this gateway on a public interface or attach multiple owners.
"""
import argparse
import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
import hmac
import json
import os
from pathlib import Path

from .job_events import CallbackError, JobEvents
from .render_jobs import JobConfig, RenderJobs


def _job_events(config, jobs, *, post=None):
    # Operator configuration only; never accept a filesystem root from MCP input.
    options = {}
    if "events_state_root" in config:
        root = config["events_state_root"]
        if not isinstance(root, str) or not root or not Path(root).is_absolute():
            raise ValueError("absolute event state root required")
        options["state_root"] = root
    if post is not None:
        options["post"] = post
    return JobEvents(jobs, config["owner"], **options)


def create_app(config, *, post=None):
    # Optional dependencies are deliberately imported only by this entrypoint.
    from mcp import ClientSession, StdioServerParameters, types
    from mcp.client.stdio import stdio_client
    from mcp.server.lowlevel import Server
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    from mcp.server.transport_security import TransportSecuritySettings
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse, Response
    from starlette.routing import Route

    token = Path(config["token_file"]).read_text().strip()
    if len(token) < 32 or any(c.isspace() for c in token):
        raise ValueError("private random ingress token required")
    jobs = RenderJobs(JobConfig(**json.loads(Path(config["jobs_config"]).read_text())))
    events = _job_events(config, jobs, post=post)
    server = Server("Blender with CG job events", version="0.1.0")
    upstream = {}
    serial = asyncio.Lock()

    @server.list_tools()
    async def list_tools():
        async with serial:
            remote = await upstream["session"].list_tools()
        if remote.nextCursor:
            raise ValueError("paginated upstream catalog requires explicit support")
        if any(t.name == "cg.job_status" for t in remote.tools):
            raise ValueError("upstream tool collision")
        return [*remote.tools, types.Tool(name="cg.job_status",
            description="Read one owned CG render job; respects durable status cache and backoff.",
            inputSchema={"type": "object", "properties": {"job_id": {"type": "string"}},
                         "required": ["job_id"], "additionalProperties": False},
            annotations=types.ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                                             idempotentHint=True, openWorldHint=False))]

    @server.call_tool()
    async def call_tool(name, arguments):
        if name == "cg.job_status":
            from .data_contract import fields
            fields(arguments, ("job_id",))
            value = await asyncio.to_thread(jobs.status, arguments["job_id"])
            return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(value))])
        # Preserve rich MCP results/errors and forward once. A dead session is
        # handled by process restart, never by replaying an uncertain mutation.
        async with serial:
            return await upstream["session"].call_tool(name, arguments)

    security = TransportSecuritySettings(enable_dns_rebinding_protection=True,
        allowed_hosts=["127.0.0.1:*", "localhost:*"],
        allowed_origins=["http://127.0.0.1:*", "http://localhost:*"])
    manager = StreamableHTTPSessionManager(server, json_response=True,
        stateless=True, security_settings=security, max_request_body_size=256*1024)
    # Pydantic's extra-capability slot is used rather than rewriting SDK responses.
    original_capabilities = server.get_capabilities

    def capabilities(*args, **kwargs):
        result = original_capabilities(*args, **kwargs)
        result.__pydantic_extra__ = {**(result.__pydantic_extra__ or {}), "events": {}}
        return result

    server.get_capabilities = capabilities

    async def mcp_endpoint(request: Request):
        if request.method == "POST":
            raw = await request.body()
            try:
                envelope = json.loads(raw)
            except (ValueError, UnicodeError):
                envelope = {}
            if isinstance(envelope, dict) and str(envelope.get("method", "")).startswith("events/"):
                method, params = envelope["method"], envelope.get("params", {})
                try:
                    if "id" not in envelope or envelope.get("jsonrpc") != "2.0":
                        raise ValueError("request ID and JSON-RPC 2.0 required")
                    if method == "events/list":
                        if not isinstance(params, dict) or set(params)-{"cursor"} or params.get("cursor") is not None:
                            raise ValueError("no list parameters supported")
                        value = events.catalog()
                    elif method == "events/subscribe":
                        value = await asyncio.to_thread(events.subscribe, params)
                    elif method == "events/unsubscribe":
                        value = await asyncio.to_thread(events.unsubscribe, params)
                    else:
                        return JSONResponse({"jsonrpc": "2.0", "id": envelope.get("id"),
                            "error": {"code": -32601, "message": "Unknown event method"}})
                    return JSONResponse({"jsonrpc": "2.0", "id": envelope["id"], "result": value})
                except CallbackError:
                    error = {"code": -32015, "message": "CallbackEndpointError",
                             "data": {"reason": "verification_failed"}}
                except (ValueError, KeyError, TypeError, LookupError):
                    error = {"code": -32602, "message": "Invalid or unauthorized event request"}
                return JSONResponse({"jsonrpc": "2.0", "id": envelope.get("id"), "error": error})
        # Request is replayed into the official ASGI transport once, not retried.
        # Starlette Request caches body only on this instance; forward cached bytes.
        raw = await request.body() if request.method == "POST" else b""
        supplied = False

        async def receive():
            nonlocal supplied
            if not supplied:
                supplied = True
                return {"type": "http.request", "body": raw, "more_body": False}
            return await request.receive()

        return _ASGIResponse(manager.handle_request, request.scope, receive)

    class _ASGIResponse(Response):
        def __init__(self, app, scope, receive):
            self.app, self.scope, self.receive = app, scope, receive

        async def __call__(self, scope, receive, send):
            await self.app(self.scope, self.receive, send)

    async def worker(stop):
        while not stop.is_set():
            try:
                await asyncio.to_thread(events.tick)
            except Exception:
                # Fixed text only. Callback requests and signing material are secrets.
                import logging
                logging.getLogger(__name__).warning("CG notification iteration failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=30)
            except TimeoutError:
                pass

    @asynccontextmanager
    async def lifespan(app):
        # Strict clean environment: never forward tunnel/API credentials upstream.
        env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8"}
        async with AsyncExitStack() as stack:
            streams = await stack.enter_async_context(stdio_client(StdioServerParameters(
                command=config["upstream_command"], env=env)))
            session = await stack.enter_async_context(ClientSession(*streams,
                read_timeout_seconds=__import__('datetime').timedelta(seconds=90)))
            await session.initialize()
            upstream["session"] = session
            await stack.enter_async_context(manager.run())
            stop = asyncio.Event()
            task = asyncio.create_task(worker(stop))
            try:
                yield
            finally:
                stop.set()
                await task  # Finish bounded delivery and reap SDK stdio child on exit.
                upstream.clear()

    inner = Starlette(routes=[Route("/mcp", mcp_endpoint, methods=["POST", "GET", "DELETE"])],
                      lifespan=lifespan)

    async def app(scope, receive, send):
        if scope["type"] != "http":
            return await inner(scope, receive, send)
        headers = dict(scope.get("headers", []))
        # Enforce these before Events interception as well as the SDK path.
        host = headers.get(b"host", b"").decode("latin-1")
        origin = headers.get(b"origin", b"").decode("latin-1")
        allowed_host = host.split(":", 1)[0] in ("127.0.0.1", "localhost")
        if not allowed_host or (origin and origin not in ("http://"+host,)):
            return await Response(status_code=403)(scope, receive, send)
        credential = headers.get(b"authorization", b"")
        if not hmac.compare_digest(credential, ("Bearer " + token).encode()):
            return await Response(status_code=401)(scope, receive, send)
        # Bound the whole request including chunked bodies, before Starlette caches it.
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > 256*1024:
                return await Response(status_code=413)(scope, receive, send)
            if not message.get("more_body", False):
                break
        consumed = False

        async def bounded_receive():
            nonlocal consumed
            if not consumed:
                consumed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await inner(scope, bounded_receive, send)

    return app


def main():
    parser = argparse.ArgumentParser(description="Single-owner CG Events HTTP experiment")
    parser.add_argument("--config", required=True)
    parser.add_argument("--port", type=int, default=9887)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("unprivileged port required")
    config = json.loads(Path(args.config).read_text())
    os.umask(0o077)
    import uvicorn
    # Access logs contain no callback data, but leave them off for this experiment.
    uvicorn.run(create_app(config), host="127.0.0.1", port=args.port, access_log=False,
                timeout_graceful_shutdown=120)


if __name__ == "__main__":
    main()
