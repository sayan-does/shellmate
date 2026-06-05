import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config.defaults import get_default_config
from config.credentials import CREDENTIAL_KEYS, load_env, save_env, get_credential_status

console = Console()


def config():
    import sys
    if len(sys.argv) > 2 and sys.argv[1] == "config":
        _config_set(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "")
        return

    cfg = get_default_config()
    creds = get_credential_status()

    console.print("[bold]ShellMate Configuration[/bold]")
    console.print()

    table = Table(title="Credentials")
    table.add_column("Key", style="cyan")
    table.add_column("Configured", style="green")
    table.add_column("Description", style="white")

    for key, info in creds.items():
        desc = CREDENTIAL_KEYS[key]["description"]
        table.add_row(key, str(info["configured"]), desc)

    console.print(table)
    console.print()

    console.print("[bold]Settings:[/bold]")
    for section, values in cfg.items():
        if isinstance(values, dict):
            console.print(f"  [cyan]{section}:[/cyan]")
            for k, v in values.items():
                console.print(f"    {k}: {v}")
        else:
            console.print(f"  {section}: {values}")

    console.print()
    console.print("[dim]Use 'sm config <KEY> <VALUE>' to set a credential[/dim]")


def _config_set(key: str, value: str):
    key = key.upper()
    if key not in CREDENTIAL_KEYS:
        console.print(f"[red]Unknown credential key: {key}[/red]")
        console.print(f"Valid keys: {', '.join(CREDENTIAL_KEYS.keys())}")
        return

    env = load_env()
    env[key] = value
    save_env(env)
    console.print(f"[green]Updated {key}[/green]")