import sys
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


def config():
    if len(sys.argv) > 2 and sys.argv[1] == "config":
        _config_set(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "")
        return

    cfg = get_config()
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