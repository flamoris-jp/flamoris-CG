"""Invoke the CG stdio adapter using the official Python MCP client.

This is a local diagnostic/Blender-MCP bridge helper, not a public file-path tool.
The resulting dict retains the standard MCP content array, including image blocks.
Requires mcp>=1.28,<2 (compatible with the existing Blender Lab client environment).
"""
import argparse
import asyncio
import json
import os
from datetime import timedelta
from pathlib import Path


async def fetch(executable, root, clip_id, *, max_edge=1280, image_format="png"):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    executable = str(Path(executable).resolve(strict=True))
    root = str(Path(root).resolve(strict=True))
    # Pass only process essentials, never tunnel keys or ambient API credentials.
    keep = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "HOME", "LANG", "LC_ALL", "DOTNET_ROOT", "XDG_RUNTIME_DIR"}
    environment = {k: v for k, v in os.environ.items() if k.upper() in keep}
    environment["DOTNET_CLI_TELEMETRY_OPTOUT"] = "1"
    parameters = StdioServerParameters(command=executable, args=["--root", root], env=environment)
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=40)) as session:
            await session.initialize()
            tools = await session.list_tools()
            if not any(t.name == "preview.get" for t in tools.tools):
                raise RuntimeError("preview tool missing")
            result = await session.call_tool("preview.get", {"input": {"clipId": clip_id, "maxEdge": max_edge, "format": image_format}})
            return result.model_dump(mode="json", by_alias=True, exclude_none=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--executable", required=True)
    p.add_argument("--root", required=True)
    p.add_argument("--clip-id", required=True)
    p.add_argument("--max-edge", type=int, default=1280)
    p.add_argument("--format", choices=["png", "jpeg"], default="png")
    args = p.parse_args()
    result = asyncio.run(fetch(args.executable, args.root, args.clip_id, max_edge=args.max_edge, image_format=args.format))
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result.get("isError") else 0


if __name__ == "__main__":
    raise SystemExit(main())
