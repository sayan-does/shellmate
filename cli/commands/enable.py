from rich.console import Console

from daemon.lifecycle import start_daemon

console = Console()


def enable():
    console.print("[bold]Starting ShellMate daemon...[/bold]")
    start_daemon()
    console.print("[green]Daemon started.[/green]")