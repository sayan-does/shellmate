import time
import json
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.table import Table

from ipc.client import ShellMateClient

console = Console()


def run_startup_ui(timeout: int = 30):
    client = ShellMateClient()

    stages = [
        ("binding_ipc", "Binding IPC..."),
        ("watcher_starting", "Starting Watcher agent..."),
        ("watcher_ready", "Watcher ready"),
        ("librarian_scanning", "Scanning project files..."),
        ("librarian_ready", "Librarian ready"),
        ("providers_checked", "Checking providers..."),
        ("ready", "Ready"),
    ]

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Starting daemon...", total=len(stages))

        start_time = time.time()
        last_stage = 0

        while time.time() - start_time < timeout:
            try:
                import asyncio
                result = asyncio.run(client.send_command("status", timeout=2.0))
            except Exception:
                result = None

            if result and result.get("status") == "ok":
                data = result.get("data", {})
                stage = data.get("startup_stage", "unknown")
                stage_idx = next((i for i, (s, _) in enumerate(stages) if s == stage), 0)

                if stage_idx > last_stage:
                    progress.update(task, completed=stage_idx)
                    last_stage = stage_idx

                if stage == "ready":
                    progress.update(task, completed=len(stages))
                    break
            else:
                pass

            time.sleep(0.5)

        if last_stage < len(stages) - 1:
            console.print("[red]Startup timed out. Daemon may not be ready.[/red]")
            console.print("Run 'sm status' to check daemon state.")
            return False

    console.print("[green]Daemon ready![/green]")
    return True