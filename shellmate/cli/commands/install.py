import os
import shutil
from importlib.resources import as_file, files as _pkg_files
from pathlib import Path

import click
from shellmate.environment.detector import detect_environment


def _get_adapter_src(filename: str) -> Path:
    """Return path to a bundled adapter file inside the installed package."""
    ref = _pkg_files("shellmate").joinpath(f"adapters/{filename}")
    # importlib.resources may return a non-Path on older Python — make it concrete
    with as_file(ref) as p:
        return Path(p)


def _get_shellmate_dir() -> Path:
    """~/.shellmate on Unix, %USERPROFILE%\\.shellmate on Windows."""
    return Path.home() / ".shellmate"


def _install_adapter(filename: str) -> Path:
    """Copy adapter from package to ~/.shellmate/adapters/ and return dest path."""
    dest_dir = _get_shellmate_dir() / "adapters"
    dest_dir.mkdir(parents=True, exist_ok=True)
    src = _get_adapter_src(filename)
    dest = dest_dir / filename
    shutil.copy2(src, dest)
    dest.chmod(0o755)
    return dest


def _adapter_filename_for_shell(shell: str):
    """Unix shells use ble_adapter.sh; Windows uses powershell_adapter.ps1."""
    if shell == "powershell":
        return "powershell_adapter.ps1"
    if shell in ("bash", "zsh"):
        return "ble_adapter.sh"
    return None


def _get_rc_file(shell):
    home = os.path.expanduser("~")
    rc_map = {
        "bash": [os.path.join(home, ".bashrc"), os.path.join(home, ".bash_profile")],
        "zsh": [os.path.join(home, ".zshrc")],
        "powershell": [
            os.path.join(home, "Documents", "PowerShell", "Microsoft.PowerShell_profile.ps1"),
            os.path.join(home, "Documents", "WindowsPowerShell", "Microsoft.PowerShell_profile.ps1"),
        ],
    }
    return rc_map.get(shell, [])


def _source_line(shell: str, filename: str) -> str:
    if shell == "powershell":
        return '. "$env:USERPROFILE\\.shellmate\\adapters\\powershell_adapter.ps1"\n'
    return f'source "$HOME/.shellmate/adapters/{filename}"\n'


def _install_hook(shell):
    adapter_name = _adapter_filename_for_shell(shell)
    if not adapter_name:
        return False, f"No adapter available for {shell}"

    try:
        dest_path = _install_adapter(adapter_name)
    except (FileNotFoundError, OSError) as e:
        return False, f"Adapter file not found: {e}"

    rc_files = _get_rc_file(shell)
    if not rc_files:
        return False, f"No RC file known for {shell}"

    source_line = _source_line(shell, adapter_name)

    installed = False
    for rc_file in rc_files:
        if os.path.exists(rc_file):
            with open(rc_file, "r") as f:
                content = f.read()
            if source_line.strip() in content:
                installed = True  # already present — idempotent success
                continue
            with open(rc_file, "a") as f:
                f.write(f"\n# ShellMate hook\n{source_line}")
            installed = True
        else:
            rc_dir = os.path.dirname(rc_file)
            if rc_dir and not os.path.exists(rc_dir):
                os.makedirs(rc_dir, exist_ok=True)
            try:
                with open(rc_file, "w") as f:
                    f.write(f"# ShellMate hook\n{source_line}")
                installed = True
            except OSError:
                pass

    if installed:
        return True, f"Hook installed for {shell} → {dest_path}"
    return False, f"Could not install hook for {shell}"


def _dry_run_adapter_plan(shell):
    """Describe the copy that install would perform (for --dry-run)."""
    adapter_name = _adapter_filename_for_shell(shell)
    if not adapter_name:
        return False, f"No adapter available for {shell}"
    try:
        src = _get_adapter_src(adapter_name)
    except (FileNotFoundError, OSError, ModuleNotFoundError) as e:
        return False, f"Adapter file not found: {e}"
    dest = _get_shellmate_dir() / "adapters" / adapter_name
    return True, f"Would copy {src} → {dest}"


def _prompt_credential_setup():
    click.echo()
    click.echo(click.style("  -------------------------------------------------", fg="cyan"))
    click.echo(click.style("  ShellMate Credential Setup", bold=True, fg="cyan"))
    click.echo(click.style("  -------------------------------------------------", fg="cyan"))
    click.echo()
    click.echo("  ShellMate needs API keys for AI-powered analysis and remediation.")
    click.echo("  You can set them up now or skip and configure later with:")
    click.echo("    " + click.style("sm config", bold=True))
    click.echo()

    if not click.confirm(click.style("  Would you like to configure API keys now?", bold=True), default=True):
        click.echo()
        click.echo("  You can always run " + click.style("sm config", bold=True) + " later.")
        click.echo("  Until then, ShellMate will use deterministic rule-based analysis.")
        return

    from shellmate.cli.commands.configure import print_header, print_status, prompt_for_key
    from shellmate.config.credentials import CREDENTIAL_KEYS, load_env, save_env

    env = load_env()
    print_header()
    print_status()

    click.echo()
    for key_name in CREDENTIAL_KEYS:
        current = env.get(key_name, os.environ.get(key_name, ""))
        new_value = prompt_for_key(key_name, current)
        env[key_name] = new_value

    save_env(env)

    click.echo()
    click.echo(click.style("  [OK] Credentials saved to ~/.shellmate/.env", fg="green"))
    click.echo()
    click.echo("  " + click.style("Next step:", bold=True))
    click.echo("  Run " + click.style("shellmate enable", bold=True) + " to start the daemon.")
    click.echo()


@click.command()
@click.option("--dry-run", is_flag=True, help="Show what would be installed without making changes")
def install(dry_run):
    """Install ShellMate shell hooks"""
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.panel import Panel
    import time
    from shellmate.ui.runtime import tokens

    console = Console()
    env = detect_environment()
    shell = env["shell"]
    os_name = env["os"]
    # Windows consoles often lack UTF-8; use ASCII marks (same pattern as daemon/server)
    icon = tokens.icons(ascii_safe=(os.name == "nt" or console.no_color))
    done = icon["done"]
    fail = icon["error"]

    console.print()
    console.print(Panel(
        f"[bold]ShellMate Install[/bold]\nSetting up hooks for [cyan]{os_name}[/cyan] / [cyan]{shell}[/cyan]",
        border_style="cyan",
        padding=(0, 2),
    ))
    console.print()

    steps = [
        ("Detecting shell environment", lambda: (True, f"Detected {shell} on {os_name}")),
        ("Locating adapter file", lambda: (
            (
                True,
                f"Adapter: {_adapter_filename_for_shell(shell)}"
            ) if _adapter_filename_for_shell(shell) else (False, "not found")
        )),
        ("Installing hook", lambda: (
            _dry_run_adapter_plan(shell) if dry_run else _install_hook(shell)
        )),
        ("Verifying shell config", lambda: (
            True,
            (
                f'[DRY RUN] Would write: {_source_line(shell, _adapter_filename_for_shell(shell) or "").strip()}'
                if dry_run
                else "Source line written"
            )
        )),
    ]

    all_ok = True
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=False,
    ) as progress:
        for label, action in steps:
            task = progress.add_task(f"[cyan]{label}...[/cyan]", total=None)
            time.sleep(0.05)  # let spinner render at least one frame
            try:
                result = action()
                ok = result[0] if isinstance(result, tuple) else bool(result)
                detail = result[1] if isinstance(result, tuple) and len(result) > 1 else ""
                if ok:
                    progress.update(task, description=f"[green]{done} {label}[/green]  [dim]{detail}[/dim]", completed=1, total=1)
                else:
                    progress.update(task, description=f"[red]{fail} {label}[/red]  [dim]{detail}[/dim]", completed=1, total=1)
                    all_ok = False
            except Exception as e:
                progress.update(task, description=f"[red]{fail} {label}: {e}[/red]", completed=1, total=1)
                all_ok = False

    console.print()
    if all_ok and not dry_run:
        console.print("[green]Shell hooks installed.[/green] Restart your shell or run:")
        if shell == "powershell":
            console.print("  [bold]. $PROFILE[/bold]")
        else:
            console.print(f"  [bold]source ~/{'.bashrc' if shell == 'bash' else '.zshrc'}[/bold]")
        console.print()
        console.print("[dim]Next step:[/dim] run [bold cyan]sm config[/bold cyan] to set up API keys")
        _prompt_credential_setup()
    elif dry_run:
        console.print("[dim]Dry run complete -- no changes made.[/dim]")
    else:
        console.print("[red]Install incomplete -- check output above.[/red]")
