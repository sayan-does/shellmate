import os
import sys
import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config import (
    get_config,
    get_config_value,
    set_config_value,
    CREDENTIAL_KEYS,
    load_env,
    save_env,
    get_credential_status,
    get_api_key,
)

console = Console()


def _is_interactive():
    if os.environ.get("SM_NONINTERACTIVE"):
        return False
    try:
        return os.isatty(0)
    except (OSError, AttributeError):
        return False


def config():
    args = [a for a in sys.argv[2:] if a]

    if "--show" in args:
        _show_config()
        return

    if args and not args[0].startswith("--"):
        key = args[0].upper()
        value = args[1] if len(args) > 1 else ""
        _config_set(key, value)
        return

    _display_config_table()
    show_all = "--all" in args
    if _is_interactive():
        _interactive_config(show_all)


def _display_config_table():
    cfg = get_config()
    creds = get_credential_status()

    console.print("[bold]ShellMate Configuration[/bold]")
    console.print()

    table = Table(title="Credentials")
    table.add_column("Key", style="cyan")
    table.add_column("Configured", style="green")
    table.add_column("Value", style="yellow")
    table.add_column("Description", style="white")

    for key, info in creds.items():
        meta = CREDENTIAL_KEYS.get(key, {})
        desc = meta.get("description", "")
        value_display = info.get("masked", "") if info["configured"] else "[dim]not set[/dim]"
        table.add_row(key, str(info["configured"]), value_display, desc)

    console.print(table)
    console.print()

    table2 = Table(title="Providers")
    table2.add_column("Role", style="cyan")
    table2.add_column("Primary", style="green")
    table2.add_column("Model", style="white")
    table2.add_column("Fallbacks", style="dim")

    providers = cfg.get("providers", {})
    for role, config in providers.items():
        fallbacks = config.get("fallbacks") or ([config["fallback"]] if config.get("fallback") else [])
        table2.add_row(
            role,
            config.get("primary", ""),
            config.get("model", ""),
            ", ".join(fallbacks) if fallbacks else "none",
        )

    console.print(table2)
    console.print()

    console.print("[bold]Settings:[/bold]")
    for section, values in cfg.items():
        if section == "providers":
            continue
        if isinstance(values, dict):
            console.print(f"  [cyan]{section}:[/cyan]")
            for k, v in values.items():
                console.print(f"    {k}: {v}")
        else:
            console.print(f"  {section}: {values}")

    console.print()
    console.print("[dim]Use 'sm config <KEY> <VALUE>' to set a credential[/dim]")
    console.print("[dim]Use 'sm config provider <role> <primary> <model>' to set provider[/dim]")
    console.print("[dim]Use 'sm config --all' to update all credentials (including already-set)[/dim]")
    console.print("[dim]Use 'sm config --show' to view credential values (masked)[/dim]")
    console.print("[dim]Run 'sm config' with no args for guided credential setup[/dim]")


def _show_config():
    creds = get_credential_status()
    console.print("[bold]ShellMate Credentials[/bold]")
    console.print()
    for key, info in creds.items():
        meta = CREDENTIAL_KEYS.get(key, {})
        label = meta.get("label", key)
        if info["configured"]:
            console.print(f"  [cyan]{label}:[/cyan] {info['masked']}")
        else:
            console.print(f"  [cyan]{label}:[/cyan] [dim]not set[/dim]")
    console.print()
    console.print("[dim]Use 'sm config <KEY> <VALUE>' to set a credential[/dim]")
    console.print("[dim]Run 'sm config' for guided setup[/dim]")


def _interactive_config(show_all: bool = False):
    env = load_env()
    changed = False

    for key, meta in CREDENTIAL_KEYS.items():
        current = env.get(key, "")
        if current and not show_all:
            continue

        label = meta.get("label", key)
        doc_url = meta.get("doc_url", "")
        description = meta.get("description", "")
        required = meta.get("required", False)

        console.print()
        console.print(f"[bold]{label}[/bold]")
        console.print(f"  {description}")
        if current:
            masked = _mask_key_for_prompt(current)
            console.print(f"  [dim]Current: {masked}[/dim]")

        prompt_text = f"Enter {label}" + (" (leave empty to skip)" if not required else "")
        value = click.prompt(prompt_text, default="", hide_input=True, show_default=False)

        if value:
            env[key] = value
            changed = True
            console.print(f"  [green]✓ {label} updated[/green]")
        elif current:
            console.print(f"  [dim]Keeping existing value[/dim]")
        else:
            console.print(f"  [dim]Skipped (not configured)[/dim]")

    if changed:
        save_env(env)
        console.print()
        console.print("[green]Credentials saved![/green]")
    else:
        console.print()
        console.print("[dim]No changes made[/dim]")


def _mask_key_for_prompt(key: str) -> str:
    if len(key) <= 8:
        return key[:2] + "*" * (len(key) - 4) + key[-2:] if len(key) > 4 else "****"
    return key[:2] + "*" * (len(key) - 6) + key[-4:]


def _config_set(key: str, value: str):
    key = key.upper()
    if key in CREDENTIAL_KEYS:
        env = load_env()
        env[key] = value
        save_env(env)
        console.print(f"[green]Updated {key}[/green]")
        return

    if key.lower() == "provider" and len(sys.argv) >= 5:
        role = sys.argv[3].lower()
        primary = sys.argv[4]
        model = sys.argv[5] if len(sys.argv) > 5 else ""
        _set_provider(role, primary, model)
        return

    if "." in key:
        set_config_value(key, value)
        console.print(f"[green]Set {key} = {value}[/green]")
        return

    console.print(f"[red]Unknown config key: {key}[/red]")
    console.print(f"Credential keys: {', '.join(CREDENTIAL_KEYS.keys())}")
    console.print("Or use dotted notation: sm config cache.similarity_threshold 0.95")


def _set_provider(role: str, primary: str, model: str):
    cfg = get_config()
    if "providers" not in cfg:
        cfg["providers"] = {}

    if role not in cfg["providers"]:
        cfg["providers"][role] = {}

    cfg["providers"][role]["primary"] = primary
    if model:
        cfg["providers"][role]["model"] = model

    from config.manager import get_config_manager
    get_config_manager().save(cfg)
    console.print(f"[green]Updated provider {role}: {primary} ({model})[/green]")
