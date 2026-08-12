import os

import click
from shellmate.daemon.lifecycle import start_daemon
from shellmate.daemon.startup_ui import run_startup_ui


def enable():
    """Start ShellMate daemon (autocomplete mode only)"""

    click.echo("Starting daemon in autocomplete mode")

    # Unix autocomplete surface needs ble.sh; Windows uses PowerShell adapter.
    if os.name != "nt" and not _check_blesh_installed():
        click.echo("[!] ble.sh not found. Autocomplete mode requires ble.sh.")
        click.echo("   Run: sm init")
        return

    if os.name == "nt" and not _powershell_adapter_present():
        click.echo("[!] PowerShell adapter not found.")
        click.echo("   Run: sm init --skip-keys --install-hooks")
        return

    # Spawn without waiting — Live scene polls stages as the daemon boots.
    if start_daemon(wait_ready=False):
        ok = run_startup_ui(timeout=30)
        if not ok:
            click.echo("Daemon may still be starting. Run 'sm status' to check.")


def _check_blesh_installed():
    """Check if ble.sh is already installed"""
    blesh_paths = [
        os.path.expanduser("~/.local/share/blesh/ble.sh"),
        os.path.expanduser("~/ble.sh/out/ble.sh"),
    ]
    return any(os.path.exists(p) for p in blesh_paths)


def _powershell_adapter_present():
    try:
        from shellmate.cli.commands.init import _adapter_exists

        return _adapter_exists()
    except Exception:
        return False
