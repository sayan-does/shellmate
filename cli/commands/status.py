import json
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from daemon.lifecycle import check_daemon_status
from providers.router import get_provider_status
from config.credentials import get_credential_status
from config.defaults import get_default_config

console = Console()


def status():
    daemon_status = check_daemon_status()
    provider_status = get_provider_status()
    credential_status = get_credential_status()
    config = get_default_config()

    if daemon_status["status"] == "running":
        console.print("[green]Daemon: Running[/green]")
        console.print(f"  PID: {daemon_status['pid']}")
    else:
        console.print("[red]Daemon: Stopped[/red]")

    console.print()

    table = Table(title="Providers")
    table.add_column("Provider", style="cyan")
    table.add_column("Configured", style="green")
    table.add_column("Status", style="yellow")

    for name, info in provider_status.items():
        table.add_row(name, str(info["configured"]), info["status"])

    console.print(table)
    console.print()

    table2 = Table(title="Credentials")
    table2.add_column("Key", style="cyan")
    table2.add_column("Configured", style="green")
    table2.add_column("Label", style="white")

    for key, info in credential_status.items():
        table2.add_row(key, str(info["configured"]), info["label"])

    console.print(table2)
    console.print()

    latency = config.get("latency_targets", {})
    console.print("[bold]Latency Targets:[/bold]")
    for key, value in latency.items():
        console.print(f"  {key}: {value}ms")