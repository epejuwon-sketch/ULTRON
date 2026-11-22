#!/usr/bin/env python3
"""ULTRON OS 2026 — Lightweight Cross-Platform Desktop Device Agent.

Exposes ONLY explicitly authorized capabilities:
- Real OS/host status telemetry (platform, CPU count, disk usage).
- Read/list file operations strictly sandboxed inside `--authorized-folder`
  (path traversal outside authorized roots is unconditionally blocked).
- Polls approved device tasks via authenticated `X-Device-Token`.

No covert monitoring, hidden recording, unrestricted shell access, or permission bypassing.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import httpx


def resolve_sandboxed_path(requested_path: str, authorized_folders: list[Path]) -> Path:
    """Resolve path and enforce strict containment within at least one authorized folder."""
    if not authorized_folders:
        raise PermissionError("No authorized folders are configured on this desktop agent.")
    candidate = Path(requested_path).expanduser().resolve()
    for root in authorized_folders:
        resolved_root = root.expanduser().resolve()
        try:
            candidate.relative_to(resolved_root)
            return candidate
        except ValueError:
            continue
    raise PermissionError(f"Access denied: '{candidate}' is outside authorized folders.")


def collect_host_status() -> dict[str, Any]:
    disk = shutil.disk_usage(Path.home())
    return {
        "os": platform.system(),
        "os_release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count() or 1,
        "disk_free_gb": round(disk.free / (1024**3), 2),
        "disk_total_gb": round(disk.total / (1024**3), 2),
    }


def execute_sandboxed_task(action: str, payload: dict[str, Any], authorized_folders: list[Path]) -> dict[str, Any]:
    """Execute an approved desktop task inside strict folder and permission boundaries."""
    if action == "status_check":
        return collect_host_status()
    if action == "folder_list":
        target = resolve_sandboxed_path(str(payload.get("path", "")), authorized_folders)
        if not target.is_dir():
            raise ValueError(f"'{target}' is not a directory.")
        entries = sorted(p.name for p in target.iterdir())[:200]
        return {"path": str(target), "entries": entries, "count": len(entries)}
    if action == "folder_read":
        target = resolve_sandboxed_path(str(payload.get("path", "")), authorized_folders)
        if not target.is_file():
            raise ValueError(f"'{target}' is not a readable file.")
        content = target.read_text(encoding="utf-8", errors="replace")[:32000]
        return {"path": str(target), "bytes": target.stat().st_size, "content": content}
    raise PermissionError(f"Action '{action}' is not permitted for unattended desktop agent execution.")


def main() -> int:
    parser = argparse.ArgumentParser(description="ULTRON OS 2026 Desktop Device Agent")
    parser.add_argument("--server", required=True, help="ULTRON backend base URL (e.g. http://127.0.0.1:8000)")
    parser.add_argument("--device-name", default=platform.node() or "ULTRON Desktop")
    parser.add_argument("--pair-code", default="", help="One-time pairing code from /api/v1/devices/pair/init")
    parser.add_argument("--token-file", default=str(Path.home() / ".ultron_device_token.json"))
    parser.add_argument("--authorized-folder", action="append", default=[], help="Explicitly authorized folder path (repeatable)")
    parser.add_argument("--once", action="store_true", help="Run one heartbeat + poll cycle and exit")
    args = parser.parse_args()

    server = args.server.rstrip("/")
    token_path = Path(args.token_file)
    auth_folders = [Path(f) for f in args.authorized_folder]

    device_id = ""
    device_token = ""

    if args.pair_code:
        plat = "windows" if sys.platform.startswith("win") else ("macos" if sys.platform == "darwin" else "windows")
        resp = httpx.post(
            f"{server}/api/v1/devices/pair/complete",
            json={
                "pairing_code": args.pair_code,
                "device_name": args.device_name,
                "platform": plat,
                "os_version": f"{platform.system()} {platform.release()}",
                "app_version": "2026.3.0",
                "capabilities": ["device_status", "notifications", "task_sync", "authorized_folder_read"],
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        device_id = data["device_id"]
        device_token = data["device_token"]
        token_path.write_text(json.dumps({"device_id": device_id, "device_token": device_token}), encoding="utf-8")
        os.chmod(token_path, 0o600)
        print(f"Paired device '{args.device_name}' ({device_id})")
    elif token_path.exists():
        saved = json.loads(token_path.read_text(encoding="utf-8"))
        device_id = saved["device_id"]
        device_token = saved["device_token"]
    else:
        print("Provide --pair-code to pair this device first.", file=sys.stderr)
        return 1

    headers = {"X-Device-Token": device_token}
    while True:
        httpx.post(
            f"{server}/api/v1/devices/{device_id}/heartbeat",
            headers=headers,
            json={"telemetry": collect_host_status()},
            timeout=10.0,
        ).raise_for_status()

        pending = httpx.get(
            f"{server}/api/v1/devices/{device_id}/tasks/pending",
            headers=headers,
            timeout=10.0,
        ).json().get("tasks", [])

        for task in pending:
            dt_id = task["device_task_id"]
            try:
                res = execute_sandboxed_task(task["action"], task["payload"], auth_folders)
                httpx.post(
                    f"{server}/api/v1/devices/{device_id}/tasks/{dt_id}/report",
                    headers=headers,
                    json={"status": "COMPLETED", "result": res},
                    timeout=10.0,
                ).raise_for_status()
            except Exception as exc:
                httpx.post(
                    f"{server}/api/v1/devices/{device_id}/tasks/{dt_id}/report",
                    headers=headers,
                    json={"status": "FAILED", "result": {}, "error_detail": str(exc)},
                    timeout=10.0,
                ).raise_for_status()

        if args.once:
            break
        time.sleep(5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
