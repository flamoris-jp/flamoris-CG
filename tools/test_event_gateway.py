"""Optional real-SDK HTTP/stdio integration acceptance; no render/network callback.

Uses a trusted local upstream launcher and an existing owned job. The injected
webhook receiver is an explicit test double, not ChatGPT delivery acceptance.
All stdio children are owned and closed by the SDK context before exit.
"""
import argparse
import asyncio
import base64
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"src"))


async def check(config_path, job_id):
    import httpx
    from flamoris_cg.event_gateway import create_app
    from flamoris_cg.job_events import EVENT
    from flamoris_cg.render_jobs import RenderJobs, JobConfig
    config = json.loads(Path(config_path).read_text())
    calls = []

    def receiver(url, body, headers):
        value = json.loads(body); calls.append(value)
        if value.get("type") == "verification":
            return 200, json.dumps({"challenge": value["challenge"]}).encode(), None
        return 204, b"", None

    # Isolate subscription secrets and history from the live deployment database.
    original = json.loads(Path(config["jobs_config"]).read_text())
    jobs = RenderJobs(JobConfig(**original))
    owned = jobs.status(job_id)
    assert owned["terminal"], "choose an existing terminal job for this acceptance"
    with tempfile.TemporaryDirectory(dir=Path(config_path).parent) as directory:
        temp = Path(directory)
        import shutil
        (temp/"state").mkdir(mode=0o700)
        # SQLite backup provides a consistent isolated authority fixture.
        import sqlite3
        with sqlite3.connect(jobs.db_path) as source, sqlite3.connect(temp/"state/jobs.sqlite3") as target:
            source.backup(target)
        original["state_root"] = str(temp/"state")
        (temp/"jobs.json").write_text(json.dumps(original))
        config["jobs_config"] = str(temp/"jobs.json")
        # Override even an explicitly configured production notification root.
        config["events_state_root"] = str(temp/"state")
        app = create_app(config, post=receiver)
        token = Path(config["token_file"]).read_text().strip()
        headers = {"Authorization": "Bearer "+token,
                   "Accept": "application/json, text/event-stream"}
        transport = httpx.ASGITransport(app=app)
        # ASGITransport intentionally does not run application lifespan itself.
        from contextlib import AsyncExitStack
        async with AsyncExitStack() as stack:
            # Drive ASGI lifespan with a tiny documented protocol harness.
            queue = asyncio.Queue(); responses = asyncio.Queue()
            await queue.put({"type": "lifespan.startup"})
            task = asyncio.create_task(app({"type": "lifespan", "asgi": {"version": "3.0"}}, queue.get, responses.put))
            async def shutdown():
                await queue.put({"type": "lifespan.shutdown"})
                response = await asyncio.wait_for(responses.get(), 20)
                assert response["type"] == "lifespan.shutdown.complete", response
                await task
            stack.push_async_callback(shutdown)
            response = await asyncio.wait_for(responses.get(), 20)
            assert response["type"] == "lifespan.startup.complete", response
            client = await stack.enter_async_context(httpx.AsyncClient(transport=transport,
                base_url="http://127.0.0.1:9887", headers=headers))
            async def rpc(method, params=None):
                response = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 1,
                    "method": method, "params": params or {}})
                assert response.status_code == 200, (response.status_code, response.text)
                value = response.json()
                assert "error" not in value, value
                return value["result"]
            init = await rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                "clientInfo": {"name": "cg-events-acceptance", "version": "1"}})
            assert "events" in init["capabilities"], init
            tools = await rpc("tools/list")
            names = [t["name"] for t in tools["tools"]]
            assert "execute_blender_code" in names and "cg.job_status" in names, names
            # Read-only upstream call proves the existing Blender connection works.
            summary = await rpc("tools/call", {"name": "get_blendfile_summary_datablocks", "arguments": {}})
            assert not summary.get("isError"), summary
            status = await rpc("tools/call", {"name": "cg.job_status", "arguments": {"job_id": job_id}})
            assert not status.get("isError"), status
            catalog = await rpc("events/list")
            assert catalog["events"][0]["name"] == EVENT
            params = {"name": EVENT, "arguments": {"job_id": job_id}, "delivery": {
                "mode": "webhook", "url": "https://receiver.example/acceptance",
                "secret": "whsec_"+base64.b64encode(b"a"*32).decode()}}
            subscription = await rpc("events/subscribe", params)
            assert calls[0]["type"] == "verification"
            from flamoris_cg.job_events import JobEvents
            outbox = JobEvents(RenderJobs(JobConfig(**original)), config["owner"], post=receiver)
            assert outbox.tick()["delivered"] == 1
            assert calls[-1]["data"]["job_id"] == job_id
            assert outbox.tick()["delivered"] == 0
            params["delivery"].pop("secret")
            await rpc("events/unsubscribe", params)
            bad = await client.post("/mcp", headers={"Authorization": "Bearer invalid"}, json={})
            assert bad.status_code == 401
            bad = await client.post("/mcp", headers={"Host": "evil.example"}, json={})
            assert bad.status_code == 403
            big = await client.post("/mcp", content=b"x"*(256*1024+1))
            assert big.status_code == 413
        return {"ok": True, "upstream_tools": len(names)-1, "events_advertised": True,
                "existing_blender_read": True, "challenge_and_delivery": "test_double",
                "auth_host_size_limits": True, "chatgpt_delivery": "not_tested"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(check(args.config, args.job_id))))
