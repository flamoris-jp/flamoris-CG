"""Trusted local operator only: review/apply/rollback an exact service plan.

Never expose this CLI or its plan as an MCP tool. A plan is privileged operator
configuration, not remotely supplied data. No API/tunnel credential is read.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import time
import urllib.request


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def command(*args):
    return subprocess.run(args, check=True, timeout=30, capture_output=True, text=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--apply", action="store_true")
    action.add_argument("--rollback", action="store_true")
    args = parser.parse_args()
    plan = json.loads(Path(args.plan).read_text())
    source = Path(plan["source"])
    target = Path(plan["target"])
    baseline = Path(plan["baseline_unit"])
    service = Path(plan["gateway_unit"])
    override = Path(plan["tunnel_override"])
    # Before privileged writes, check the exact observed baseline and source bytes.
    if digest(baseline) != plan["baseline_sha256"]:
        raise ValueError("tunnel unit changed; inspect and regenerate the plan")
    if not args.rollback:
        for name, expected in plan["source_hashes"].items():
            path = source/name
            if path.is_symlink() or not path.is_file() or digest(path) != expected:
                raise ValueError("source changed; inspect and regenerate the plan")
    if not args.apply and not args.rollback:
        print(json.dumps({"action": "review", "source": str(source), "target": str(target),
            "gateway_unit": plan["gateway_unit_text"], "tunnel_override": plan["tunnel_override_text"],
            "rollback": "Run this same command with --rollback", "source_hashes": plan["source_hashes"]}, indent=2))
        return
    if os.geteuid() != 0:
        raise PermissionError("administrative rights are required for service configuration")
    os.umask(0o077)
    if args.rollback:
        if not override.exists() or override.read_text() != plan["tunnel_override_text"]:
            raise ValueError("override changed or absent; inspect before rollback")
        override.unlink()
        command("systemctl", "daemon-reload")
        command("systemctl", "restart", baseline.name)
        command("systemctl", "disable", "--now", service.name)
        print("Original tunnel transport restored; gateway stopped. Files retained for review.")
        return
    # Refuse pre-existing deployments and unrelated drop-ins; never overwrite them.
    if target.exists() or service.exists() or override.exists():
        raise ValueError("deployment destination already exists; inspect instead of repeating apply")
    if override.parent.exists() and list(override.parent.iterdir()):
        raise ValueError("unreviewed tunnel drop-ins exist")
    command("systemctl", "is-active", "--quiet", baseline.name)
    target.mkdir(mode=0o755)
    for name, expected in plan["source_hashes"].items():
        destination = target/name
        destination.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        # Copy by bytes into the new version root. Never chown a user-owned tree.
        with (source/name).open("rb") as incoming, destination.open("xb") as outgoing:
            shutil.copyfileobj(incoming, outgoing)
        if digest(destination) != expected:
            raise ValueError("source changed during copy; new inactive files retained")
        destination.chmod(0o444)
    for directory in target.rglob("*"):
        if directory.is_dir():
            directory.chmod(0o755)
    account = pwd.getpwnam(plan["user"])
    for config_name in ("gateway.json", "ingress-token", "ingress-header"):
        path = source/config_name
        if path.is_symlink() or not path.is_file():
            raise ValueError("invalid private configuration")
        os.chown(path, account.pw_uid, account.pw_gid)
        path.chmod(0o600)
    with service.open("x") as stream:
        stream.write(plan["gateway_unit_text"])
    service.chmod(0o644)
    switched = False
    try:
        command("systemctl", "daemon-reload")
        command("systemctl", "enable", "--now", service.name)
        # One local bounded readiness check loop, independent of ChatGPT polling.
        token = (source/"ingress-token").read_text().strip()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        ready = False
        for _ in range(20):
            try:
                request = urllib.request.Request(plan["local_url"], data=json.dumps({
                    "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                        "protocolVersion": "2025-03-26", "capabilities": {},
                        "clientInfo": {"name": "cg-event-readiness", "version": "1"}}}).encode(),
                    headers={"Authorization": "Bearer "+token, "Content-Type": "application/json",
                             "Accept": "application/json, text/event-stream"})
                with opener.open(request, timeout=2) as response:
                    value = json.loads(response.read(16384))
                ready = "events" in value["result"]["capabilities"]
                if ready:
                    break
            except (OSError, ValueError, KeyError):
                pass
            time.sleep(1)
        if not ready:
            raise RuntimeError("gateway not ready; tunnel has not been changed")
        override.parent.mkdir(mode=0o755, exist_ok=True)
        with override.open("x") as stream:
            stream.write(plan["tunnel_override_text"])
        override.chmod(0o644)
        switched = True
        command("systemctl", "daemon-reload")
        command("systemctl", "restart", baseline.name)
        command("systemctl", "is-active", "--quiet", baseline.name)
    except BaseException:
        if switched:
            override.unlink()
            command("systemctl", "daemon-reload")
            command("systemctl", "restart", baseline.name)
        command("systemctl", "disable", "--now", service.name)
        raise
    print("Gateway started and tunnel switched to private HTTP. Rescan the plugin, then test a real event subscription. ChatGPT delivery is not yet accepted.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Do not print subprocess output, callback data or any secret.
        print("Activation stopped:", type(exc).__name__, str(exc) if isinstance(exc, (ValueError, PermissionError, RuntimeError)) else "inspect the exact failed operation locally")
        raise SystemExit(1)
