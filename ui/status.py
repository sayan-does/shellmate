from rich.console import Console, Group
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.columns import Columns
from rich.layout import Layout

console = Console(width=120)


def _status_tag(status: str) -> Text:
    if status == "running" or status == "ready":
        return Text(" * ", style="bold green") + Text("Running", style="green")
    elif status == "stopped":
        return Text(" o ", style="bold red") + Text("Stopped", style="red")
    elif status == "error":
        return Text(" x ", style="bold red") + Text("Error", style="red")
    elif status == "starting":
        return Text(" ~ ", style="bold yellow") + Text("Starting", style="yellow")
    return Text(f" {status}", style="dim")


def render_status(
    daemon_status: dict,
    provider_status: dict,
    credential_status: dict,
    agent_status: dict = None,
    config: dict = None,
):
    daemon_stat = daemon_status.get("status", "stopped")
    status_indicator = _status_tag(daemon_stat)

    info_lines = [status_indicator]
    if daemon_stat == "running":
        pid = daemon_status.get("pid", "?")
        cwd = daemon_status.get("cwd", "?")
        uptime = daemon_status.get("uptime_seconds", 0)
        last_check = daemon_status.get("last_health_check")

        info_lines.append(Text(f"  PID: {pid}", style="dim"))
        info_lines.append(Text(f"  CWD: {cwd}", style="dim"))
        if uptime:
            uptime_str = f"{int(uptime // 3600):02d}:{int((uptime % 3600) // 60):02d}:{int(uptime % 60):02d}"
            info_lines.append(Text(f"  Uptime: {uptime_str}", style="dim"))
        if last_check:
            info_lines.append(Text(f"  Health: {last_check:.0f}s ago", style="dim"))

    daemon_panel = Panel(
        Group(*info_lines),
        border_style="green" if daemon_stat == "running" else "red",
        title="[bold]Daemon[/]",
        padding=(1, 2),
    )

    panels = [daemon_panel]

    if agent_status:
        agent_table = Table(show_header=False, box=None, padding=(0, 2))
        agent_table.add_column("Agent", style="cyan")
        agent_table.add_column("Status")
        for name, st in agent_status.items():
            tag = _status_tag(st)
            agent_table.add_row(f"  {name}", tag)
        agent_panel = Panel(
            Group(Text("Agent Status", style="bold"), Text(""), agent_table),
            border_style="blue",
            title="[bold]Agents[/]",
            padding=(1, 2),
        )
        panels.append(agent_panel)

    provider_table = Table(show_header=False, box=None, padding=(0, 2))
    provider_table.add_column("Provider", style="cyan")
    provider_table.add_column("Configured")
    provider_table.add_column("Status")

    for name, info in provider_status.items():
        configured = info.get("configured", False)
        conf_tag = Text("+", style="green") if configured else Text("x", style="red")
        provider_table.add_row(f"  {name}", conf_tag, info.get("status", "unknown"))

    provider_panel = Panel(
        Group(Text("Providers", style="bold"), Text(""), provider_table),
        border_style="blue",
        title="[bold]Providers[/]",
        padding=(1, 2),
    )
    panels.append(provider_panel)

    cred_table = Table(show_header=False, box=None, padding=(0, 2))
    cred_table.add_column("Key", style="cyan")
    cred_table.add_column("Configured")
    cred_table.add_column("Label")

    for key, info in credential_status.items():
        configured = info.get("configured", False)
        conf_tag = Text("+", style="green") if configured else Text("x", style="red")
        cred_table.add_row(f"  {key}", conf_tag, info.get("label", ""))

    cred_panel = Panel(
        Group(Text("Credentials", style="bold"), Text(""), cred_table),
        border_style="blue",
        title="[bold]Credentials[/]",
        padding=(1, 2),
    )
    panels.append(cred_panel)

    if config:
        latency = config.get("latency_targets", {})
        lat_lines = [Text("Latency Targets", style="bold")]
        for key, value in latency.items():
            lat_lines.append(Text(f"  {key}: {value}ms", style="dim"))
        lat_panel = Panel(
            Group(*lat_lines),
            border_style="blue",
            padding=(1, 2),
        )
        panels.append(lat_panel)

    for p in panels:
        console.print(p)
        console.print()
