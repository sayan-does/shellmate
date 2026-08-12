"""Status scene — quiet assemble, no hardcoded width."""

from __future__ import annotations

import time
from typing import Callable, Optional

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from shellmate.ui.runtime import tokens
from shellmate.ui.runtime.console_factory import ConsoleFactory
from shellmate.ui.runtime.live_scene import LiveScene
from shellmate.ui.runtime.motion_policy import MotionPolicy


def _status_tag(status: str) -> Text:
    if status in ("running", "ready"):
        return Text(" * ", style="bold green") + Text("Running", style="green")
    if status == "stopped":
        return Text(" o ", style="bold red") + Text("Stopped", style="red")
    if status == "error":
        return Text(" x ", style="bold red") + Text("Error", style="red")
    if status == "starting":
        return Text(" ~ ", style="bold yellow") + Text("Starting", style="yellow")
    return Text(f" {status}", style="dim")


def build_status_renderable(
    daemon_status: dict,
    provider_status: dict,
    credential_status: dict,
    agent_status: dict | None = None,
    config: dict | None = None,
    *,
    console_width: int = 96,
) -> Group:
    width = tokens.content_width(console_width)
    daemon_stat = daemon_status.get("status", "stopped")
    status_indicator = _status_tag(daemon_stat)

    info_lines = [status_indicator]
    if daemon_stat == "running":
        pid = daemon_status.get("pid", "?")
        cwd = daemon_status.get("cwd", "?")
        uptime = daemon_status.get("uptime_seconds", 0)
        last_check = daemon_status.get("last_health_check")
        info_lines.append(Text(f"  PID: {pid}", style=tokens.MUTED))
        info_lines.append(Text(f"  CWD: {cwd}", style=tokens.MUTED))
        if uptime:
            uptime_str = (
                f"{int(uptime // 3600):02d}:"
                f"{int((uptime % 3600) // 60):02d}:"
                f"{int(uptime % 60):02d}"
            )
            info_lines.append(Text(f"  Uptime: {uptime_str}", style=tokens.MUTED))
        if last_check:
            info_lines.append(Text(f"  Health: {last_check:.0f}s ago", style=tokens.MUTED))

    panels: list[Panel] = [
        Panel(
            Group(*info_lines),
            border_style="green" if daemon_stat == "running" else "red",
            title="[bold]Daemon[/]",
            padding=(1, 2),
            width=width,
            expand=False,
        )
    ]

    if agent_status:
        agent_table = Table(show_header=False, box=None, padding=(0, 2))
        agent_table.add_column("Agent", style=tokens.ACCENT)
        agent_table.add_column("Status")
        for name, st in agent_status.items():
            agent_table.add_row(f"  {name}", _status_tag(st))
        panels.append(
            Panel(
                Group(Text("Agent Status", style=tokens.TITLE), Text(""), agent_table),
                border_style=tokens.ACCENT,
                title="[bold]Agents[/]",
                padding=(1, 2),
                width=width,
                expand=False,
            )
        )

    provider_table = Table(show_header=False, box=None, padding=(0, 2))
    provider_table.add_column("Provider", style=tokens.ACCENT)
    provider_table.add_column("Configured")
    provider_table.add_column("Status")
    for name, info in provider_status.items():
        configured = info.get("configured", False)
        conf_tag = Text("+", style=tokens.SUCCESS) if configured else Text("x", style=tokens.ERROR)
        provider_table.add_row(f"  {name}", conf_tag, info.get("status", "unknown"))
    panels.append(
        Panel(
            Group(Text("Providers", style=tokens.TITLE), Text(""), provider_table),
            border_style=tokens.ACCENT,
            title="[bold]Providers[/]",
            padding=(1, 2),
            width=width,
            expand=False,
        )
    )

    cred_table = Table(show_header=False, box=None, padding=(0, 2))
    cred_table.add_column("Key", style=tokens.ACCENT)
    cred_table.add_column("Configured")
    cred_table.add_column("Label")
    for key, info in credential_status.items():
        configured = info.get("configured", False)
        conf_tag = Text("+", style=tokens.SUCCESS) if configured else Text("x", style=tokens.ERROR)
        cred_table.add_row(f"  {key}", conf_tag, info.get("label", ""))
    panels.append(
        Panel(
            Group(Text("Credentials", style=tokens.TITLE), Text(""), cred_table),
            border_style=tokens.ACCENT,
            title="[bold]Credentials[/]",
            padding=(1, 2),
            width=width,
            expand=False,
        )
    )

    if config:
        latency = config.get("latency_targets", {})
        lat_lines = [Text("Latency Targets", style=tokens.TITLE)]
        for key, value in latency.items():
            lat_lines.append(Text(f"  {key}: {value}ms", style=tokens.MUTED))
        panels.append(
            Panel(Group(*lat_lines), border_style=tokens.ACCENT, padding=(1, 2), width=width, expand=False)
        )

    # Separate with blank lines via Group of panels + empty Text
    parts: list = []
    for i, p in enumerate(panels):
        if i:
            parts.append(Text(""))
        parts.append(p)
    return Group(*parts)


def render_status(
    daemon_status: dict,
    provider_status: dict,
    credential_status: dict,
    agent_status: dict = None,
    config: dict = None,
    *,
    console: Console | None = None,
    plain: bool | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
):
    """Render status with a light assemble animation when interactive."""
    cf = ConsoleFactory(no_color=bool(plain))
    c = console or cf.create()
    is_plain = cf.is_plain() if plain is None else plain

    full = build_status_renderable(
        daemon_status,
        provider_status,
        credential_status,
        agent_status,
        config,
        console_width=c.width,
    )

    policy = MotionPolicy(plain=is_plain, min_dwell_ms=60, stagger_ms=20, max_artificial_ms_after_ready=400)
    scene = LiveScene(c, plain=is_plain)
    header = Text(f"ShellMate status", style=f"bold {tokens.ACCENT}")
    try:
        scene.start(header)
        sleep_fn(policy.stagger_seconds())
        scene.update(Group(header, Text(""), full))
        sleep_fn(policy.dwell_seconds())
    except Exception:
        pass
    scene.settle(full)
