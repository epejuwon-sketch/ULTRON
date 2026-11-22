"""Honest Antigravity Runtime Plugin Adapter.

Inspects ONLY documented, sanctioned Antigravity plugin CLI launchers in `/opt/antigravity/bin`
and reports live authentication status for connected plugins without reading token files
or inventing undocumented Antigravity APIs.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

_OFFICIAL_PLUGIN_BIN_DIR = Path("/opt/antigravity/bin")

# Documented official plugin CLI health checks (read-only)
_SUPPORTED_PLUGINS: dict[str, tuple[str, list[str]]] = {
    "github": ("gh", ["gh", "auth", "status"]),
    "gdrive": ("gdrive", ["gdrive", "auth", "status"]),
    "gmail": ("gmail", ["gmail", "auth", "status"]),
}

# Installed binaries that are NOT assumed connected unless explicitly authorized
_OPTIONAL_PLUGIN_CLIS = ("gcalendar", "gdocs", "gsheets", "gslides")


def inspect_antigravity_environment(*, run_live_auth_checks: bool = False) -> dict[str, Any]:
    """Return an honest inventory of Antigravity plugin CLI availability and unsupported interfaces."""
    is_antigravity_vm = _OFFICIAL_PLUGIN_BIN_DIR.exists()
    connected_plugins: dict[str, Any] = {}

    for name, (binary, check_cmd) in _SUPPORTED_PLUGINS.items():
        bin_path = shutil.which(binary)
        if not bin_path:
            connected_plugins[name] = {
                "cli": binary,
                "installed": False,
                "status": "UNAVAILABLE",
                "detail": f"Official '{binary}' CLI not found on PATH.",
            }
            continue

        if not run_live_auth_checks:
            connected_plugins[name] = {
                "cli": binary,
                "installed": True,
                "status": "IMPLEMENTED_NOT_LIVE",
                "detail": f"Official '{binary}' CLI present; run live check to confirm authentication.",
            }
            continue

        try:
            proc = subprocess.run(check_cmd, capture_output=True, text=True, timeout=8, check=False)
            combined = (proc.stdout + "\n" + proc.stderr).strip()
            ok = proc.returncode == 0 and (
                "Logged in" in combined or "authenticated" in combined.lower() or "active account" in combined.lower()
            )
            connected_plugins[name] = {
                "cli": binary,
                "installed": True,
                "status": "AVAILABLE" if ok else "REQUIRES_CONFIGURATION",
                "detail": "Authenticated via Antigravity plugin bridge." if ok else "CLI present but not authenticated.",
            }
        except Exception as exc:
            connected_plugins[name] = {
                "cli": binary,
                "installed": True,
                "status": "DEGRADED",
                "detail": f"Auth check failed: {type(exc).__name__}",
            }

    optional_plugins: dict[str, Any] = {}
    for binary in _OPTIONAL_PLUGIN_CLIS:
        installed = bool(shutil.which(binary))
        optional_plugins[binary] = {
            "cli": binary,
            "installed": installed,
            "status": "REQUIRES_CONFIGURATION" if installed else "UNAVAILABLE",
            "detail": (
                "CLI binary installed in VM but plugin is not connected in this session; "
                "configure Google OAuth 2.0 in ULTRON IntegrationManager or connect the plugin."
                if installed
                else "CLI not installed."
            ),
        }

    return {
        "runtime_detected": is_antigravity_vm,
        "connected_plugin_adapters": connected_plugins,
        "disconnected_or_optional_clis": optional_plugins,
        "unsupported_interfaces": {
            "antigravity_rest_control_plane": {
                "status": "UNAVAILABLE",
                "detail": "No public documented Antigravity REST control-plane API exists; ULTRON does not invent or probe undocumented host endpoints.",
            },
            "direct_token_file_access": {
                "status": "UNAVAILABLE",
                "detail": "Direct reading or exporting of Antigravity plugin token files is strictly prohibited by security policy.",
            },
        },
    }
