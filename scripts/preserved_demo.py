#!/usr/bin/env python3
"""Check or start captured demo containers; never build, migrate, or recreate."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener


def command(*args: str) -> str:
    return subprocess.check_output(args, text=True).strip()


def inspect_demo(state: Path) -> tuple[dict, list[dict]]:
    manifest = json.loads((state / "manifest.json").read_text())
    config = state / "compose.demo.json"
    if hashlib.sha256(config.read_bytes()).hexdigest() != manifest["compose_sha256"]:
        raise ValueError("Captured recovery configuration changed; review required")
    checkout = manifest["checkout"]
    git = ("git", "-c", f"safe.directory={checkout}", "-C", checkout)
    if command(*git, "rev-parse", "HEAD") != manifest["revision"]:
        raise ValueError("Preserved checkout revision changed")
    if command(*git, "status", "--porcelain", "--untracked-files=no"):
        raise ValueError("Preserved checkout has tracked changes")
    expected = manifest["containers"]
    rows = json.loads(command("docker", "inspect", *(c["name"] for c in expected)))
    actual = {c["Name"].lstrip("/"): c for c in rows}
    ordered = []
    for record in expected:
        container = actual[record["name"]]
        ordered_mounts = sorted(container["Mounts"], key=lambda mount: mount["Destination"])
        mounts = hashlib.sha256(json.dumps(ordered_mounts, sort_keys=True).encode()).hexdigest()
        if (
            container["Id"] != record["id"]
            or container["Image"] != record["image"]
            or mounts != record["mounts_sha256"]
        ):
            raise ValueError(f"{record['name']} no longer matches the preserved demo")
        ordered.append(container)
    return manifest, ordered


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) == 2 else ""
    if mode not in {"check", "plan", "start"}:
        raise ValueError("Usage: preserved_demo.py check|plan|start")
    manifest, containers = inspect_demo(Path(__file__).resolve().parent)
    stopped = [c for c in containers if not c["State"]["Running"]]
    if mode == "plan":
        print(json.dumps({"url": manifest["url"], "start_only": [c["Name"] for c in stopped]}))
        return
    if mode == "start":
        for container in stopped:
            command("docker", "start", container["Id"])
        if stopped:
            print("Started captured containers only; run check after dependencies warm up.")
            return
    for container in containers:
        health = container["State"].get("Health", {}).get("Status", "healthy")
        if not container["State"]["Running"] or health != "healthy":
            raise ValueError(f"{container['Name']} is not ready; no running container was changed")
    opener = build_opener(ProxyHandler({}))
    with opener.open(Request(manifest["url"] + "/ready"), timeout=20) as response:
        if json.load(response).get("status") != "ok":
            raise ValueError("Gateway is not ready; inspect logs before recovery")
    print(f"Preserved demo ready: {manifest['url']}/demo.html ({manifest['revision'][:7]})")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print(f"Demo check refused: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
