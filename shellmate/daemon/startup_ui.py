"""Startup UI — delegates to enable LiveScene (Claude Code–quiet morph)."""

from __future__ import annotations

import asyncio
from typing import Optional

from shellmate.ipc.client import ShellMateClient
from shellmate.ui.runtime.console_factory import ConsoleFactory
from shellmate.ui.runtime.motion_policy import motion_from_env
from shellmate.ui.scenes.enable import run_enable_scene


def run_startup_ui(timeout: int = 30, *, no_color: bool = False) -> bool:
    """Poll daemon status and run the enable scene. Returns True if ready."""
    client = ShellMateClient()
    factory = ConsoleFactory(no_color=no_color)
    console = factory.create()
    plain = factory.is_plain()

    def poll() -> tuple[Optional[list[str]], Optional[str]]:
        try:
            result = asyncio.run(client.send_command("/status", timeout=2.0))
        except Exception:
            return None, None
        if not result or result.get("status") != "ok":
            return None, None
        data = result.get("data") or {}
        completed = data.get("startup_stages_completed")
        current = data.get("startup_stage")
        if completed is not None and not isinstance(completed, list):
            completed = None
        return completed, current

    return run_enable_scene(
        poll=poll,
        console=console,
        plain=plain,
        ascii_safe=plain,
        timeout=float(timeout),
        policy=motion_from_env(plain=plain),
        poll_interval=0.12,
    )
