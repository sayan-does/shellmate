import os
import sys
import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from shellmate.config import (
    get_config,
    set_config_value,
    CREDENTIAL_KEYS,
    load_env,
    save_env,
    get_credential_status,
)
from shellmate.config.credentials import AI_CREDENTIAL_KEYS
from shellmate.providers.validate_keys import validate_api_key

console = Console()

_PROVIDER_MENU = [
    ("GROQ_API_KEY", "Groq"),
    ("OPENROUTER_API_KEY", "OpenRouter"),
    ("XAI_API_KEY", "Grok (xAI)"),
]


def _is_interactive():
    if os.environ.get("SM_NONINTERACTIVE"):
        return False
    try:
        return os.isatty(0)
    except (OSError, AttributeError):
        return False


def config():
    console.print()
    console.print(Panel(
        "[bold]ShellMate Config[/bold]\n"
        "Set up API keys for AI-powered consequence preview and risk analysis.",
        border_style="cyan",
        padding=(0, 2),
    ))
    console.print()

    args = [a for a in sys.argv[2:] if a]

    if "--show" in args:
        _show_config()
        return

    # Accept an optional leading `set` so both `sm config KEY value` and
    # `sm config set KEY value` work as the paste-free non-interactive path.
    if args and args[0].lower() == "set":
        args = args[1:]

    if args and not args[0].startswith("--"):
        key = args[0].upper()
        value = args[1] if len(args) > 1 else ""
        _config_set(key, value)
        return

    _display_config_table()
    if _is_interactive():
        _interactive_config()
    else:
        _validate_existing_keys(report_only=True)


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
    for role, role_cfg in providers.items():
        fallbacks = role_cfg.get("fallbacks") or (
            [role_cfg["fallback"]] if role_cfg.get("fallback") else []
        )
        table2.add_row(
            role,
            role_cfg.get("primary", ""),
            role_cfg.get("model", ""),
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
    console.print("[dim]Run 'sm config' interactively to select a provider and paste an API key.[/dim]")
    console.print("[dim]Or set a key non-interactively (paste-free): 'sm config set <KEY> <value>'.[/dim]")
    console.print("[dim]Use 'sm config provider <role> <primary> [model]' to set provider roles.[/dim]")
    console.print("[dim]Use 'sm config --show' to view credential values (masked).[/dim]")


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
    console.print("[dim]Run 'sm config' for guided setup (select provider, then paste key).[/dim]")


def _resolve_key_value(env: dict, key: str) -> str:
    return (env.get(key) or os.environ.get(key) or "").strip()


def _validate_existing_keys(*, report_only: bool = False) -> None:
    env = load_env()
    configured = [
        key for key in CREDENTIAL_KEYS
        if _resolve_key_value(env, key)
    ]
    if not configured:
        if not report_only:
            console.print()
            console.print("[yellow]No API keys configured yet.[/yellow]")
            console.print(
                "[dim]Select a provider below and paste a key "
                "(Groq, OpenRouter, or Grok/xAI).[/dim]"
            )
        return

    console.print()
    console.print("[bold]Checking API keys…[/bold]")
    for key in configured:
        meta = CREDENTIAL_KEYS.get(key, {})
        label = meta.get("label", key)
        value = _resolve_key_value(env, key)
        with console.status(f"[cyan]Validating {label}…[/cyan]", spinner="dots"):
            ok, message = validate_api_key(key, value)
        if ok:
            console.print(f"  [green]✔ {label}:[/green] {message}")
        else:
            console.print(f"  [red]✖ {label}:[/red] {message}")


def _interactive_config():
    env = load_env()
    _validate_existing_keys()

    has_ai_key = any(_resolve_key_value(env, k) for k in AI_CREDENTIAL_KEYS)
    if not has_ai_key:
        console.print()
        console.print(
            "[yellow]At least one of Groq, OpenRouter, or Grok (xAI) is recommended.[/yellow]"
        )

    changed = False
    # Bounded + EOF-safe: a closed/redirected stdin or a terminal that keeps
    # feeding input must never spin this loop forever.
    MAX_ROUNDS = 50
    for _ in range(MAX_ROUNDS):
        console.print()
        console.print("[bold]Add or replace an API key[/bold]")
        for i, (key, name) in enumerate(_PROVIDER_MENU, start=1):
            current = _resolve_key_value(env, key)
            status = (
                f"[green]set ({_mask_key_for_prompt(current)})[/green]"
                if current
                else "[dim]not set[/dim]"
            )
            console.print(f"  [cyan]{i}.[/cyan] {name}  {status}")
        console.print("  [cyan]0.[/cyan] Done")

        try:
            choice = click.prompt("Select provider", default="0", show_default=True).strip()
        except (EOFError, click.Abort):
            break
        if choice.lower() in ("0", "", "done", "q", "quit", "exit"):
            break

        try:
            idx = int(choice)
        except ValueError:
            console.print("[red]Invalid selection[/red]")
            continue

        if idx < 1 or idx > len(_PROVIDER_MENU):
            console.print("[red]Invalid selection[/red]")
            continue

        key, name = _PROVIDER_MENU[idx - 1]
        if _prompt_and_save_key(env, key, name):
            changed = True
            env = load_env()

    console.print()
    if changed:
        console.print("[green]✔ Credentials saved![/green]")
        console.print("[dim]Next step:[/dim] run [bold cyan]sm enable[/bold cyan] to start the daemon.")
    else:
        console.print("[dim]No changes made[/dim]")


def _prompt_and_save_key(env: dict, key: str, name: str) -> bool:
    meta = CREDENTIAL_KEYS.get(key, {})
    label = meta.get("label", name)
    doc_url = meta.get("doc_url", "")
    description = meta.get("description", "")
    current = _resolve_key_value(env, key)

    guidance_lines = [f"[bold]{label}[/bold]", f"  {description}"]
    if doc_url:
        guidance_lines.append(
            f"  [dim]Get your key at:[/dim] [cyan underline]{doc_url}[/cyan underline]"
        )
    if current:
        guidance_lines.append(f"  [dim]Current: {_mask_key_for_prompt(current)}[/dim]")
    console.print()
    console.print(Panel("\n".join(guidance_lines), border_style="dim", padding=(0, 2)))

    # Input is intentionally NOT hidden: hide_input=True breaks clipboard paste
    # on Windows ConPTY and other restricted terminals (the original paste bug).
    # The key is stored in a local .env (0o600) anyway, so masking the echo adds
    # no real secrecy while actively breaking the primary way users enter a key.
    try:
        value = click.prompt(
            f"  Paste {label} (leave empty to cancel)",
            default="",
            show_default=False,
        ).strip()
    except (EOFError, click.Abort):
        console.print("  [dim]Cancelled[/dim]")
        return False
    if not value:
        console.print("  [dim]Cancelled[/dim]")
        return False

    with console.status(f"[cyan]Validating {label}…[/cyan]", spinner="dots"):
        ok, message = validate_api_key(key, value)

    if not ok:
        console.print(f"  [red]✖ {message}[/red]")
        if not click.confirm("  Save this key anyway?", default=False):
            console.print("  [dim]Not saved[/dim]")
            return False
        console.print(f"  [yellow]Saved without successful validation[/yellow]")
    else:
        console.print(f"  [green]✔ {message}[/green]")

    env[key] = value
    save_env(env)
    console.print(f"  [green]✔ {label} saved[/green]")
    return True


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

    from shellmate.config.manager import get_config_manager
    get_config_manager().save(cfg)
    console.print(f"[green]Updated provider {role}: {primary} ({model})[/green]")
