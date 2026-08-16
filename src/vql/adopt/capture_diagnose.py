"""Per-backend capture diagnostics."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from vql.adopt.capture_backends import PORTAL_CAPTURE_SCRIPT, capture_backends, finalize_capture
from vql.adopt.capture_image import image_is_blank, image_stats
from vql.adopt.capture_policy import (
    capture_permission_hint,
    is_wayland,
    portal_python,
    session_type,
    should_use_interactive_portal,
)
from vql.adopt.capture_types import CaptureAttempt, CaptureInfo, require_pillow


def _run_portal_capture(
    name: str,
    probe: Path,
    *,
    interactive: bool,
) -> tuple[CaptureInfo | None, str, dict[str, Any]]:
    py = portal_python()
    if not py or not PORTAL_CAPTURE_SCRIPT.is_file():
        return None, "portal python (python3-dbus, python3-gi) not found", {}

    cmd = [py, str(PORTAL_CAPTURE_SCRIPT), "--out", str(probe)]
    if name == "portal-interactive" or interactive:
        cmd.append("--interactive")
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=45, check=False)
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        payload = {"error": (proc.stderr or proc.stdout or "").strip()}
    if payload.get("ok") and probe.is_file() and not image_is_blank(probe):
        return finalize_capture(probe, source="xdg-portal"), "", payload
    return None, str(payload.get("error") or ""), payload


def _run_capture_backend(
    name: str,
    backend: Any,
    probe: Path,
    *,
    interactive: bool,
) -> tuple[CaptureInfo | None, str, dict[str, Any]]:
    try:
        if name.startswith("portal"):
            return _run_portal_capture(name, probe, interactive=interactive)
        return backend(probe), "", {}
    except Exception as exc:
        return None, str(exc), {}


def _failed_capture_attempt(
    name: str,
    probe: Path,
    *,
    error: str,
    portal_payload: dict[str, Any],
) -> CaptureAttempt:
    blank = probe.is_file() and image_is_blank(probe)
    if blank:
        error = error or "image saved but all black (GNOME Screen Recording permission?)"
    elif probe.is_file():
        error = error or "image saved but rejected"
    else:
        error = error or "backend unavailable or produced no file"

    stats = image_stats(probe) if probe.is_file() else {}
    if portal_payload:
        stats = {**stats, "portal": portal_payload}
    return CaptureAttempt(backend=name, ok=False, blank=blank, error=error, stats=stats)


def capture_diagnose(
    out: str | Path | None = None,
    *,
    monitor: int = 1,
    interactive_portal: bool | None = None,
) -> dict[str, Any]:
    """Try each capture backend and report why it failed (blank, denied, missing tool)."""
    require_pillow()
    path = Path(out or Path("/tmp/vql-capture-diagnose.png"))
    interactive = should_use_interactive_portal() if interactive_portal is None else interactive_portal
    attempts: list[CaptureAttempt] = []

    for name, backend in capture_backends(monitor=monitor, interactive_portal=interactive):
        probe = path.with_name(f"{path.stem}.{name}{path.suffix}")
        info, error, portal_payload = _run_capture_backend(
            name,
            backend,
            probe,
            interactive=interactive,
        )
        if info is not None:
            attempts.append(
                CaptureAttempt(
                    backend=name,
                    ok=True,
                    source=info.source,
                    stats=image_stats(probe),
                )
            )
            break

        attempts.append(
            _failed_capture_attempt(
                name,
                probe,
                error=error,
                portal_payload=portal_payload,
            )
        )
        if probe.is_file():
            probe.unlink(missing_ok=True)

    success = next((a for a in attempts if a.ok), None)
    return {
        "ok": success is not None,
        "session": session_type() or "unknown",
        "wayland": is_wayland(),
        "portal_python": portal_python(),
        "interactive_portal": interactive,
        "attempts": [a.to_dict() for a in attempts],
        "hint": capture_permission_hint(),
        "result": success.to_dict() if success else {},
    }
