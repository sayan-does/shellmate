from rich.console import Console

from daemon.lifecycle import stop_daemon

console = Console()


def disable():
    console.print("[bold]Stopping ShellMate daemon...[/bold]")
    stop_daemon()
    console.print("[green]Daemon stopped.[/green]")