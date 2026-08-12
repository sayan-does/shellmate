"""Migrate from deprecated interception hooks to autocomplete mode."""

import os

import click

from shellmate.cli.commands.init import (
    _check_blesh_installed,
    _confirm,
    _echo,
    _install_autocomplete_hook,
    _install_blesh,
    _install_powershell_hook,
    _is_windows_target,
    _powershell_profile_paths,
    _profile_integration_ok,
)


@click.command(name="migrate-to-autocomplete")
def migrate():
    """Migrate from deprecated interception mode to autocomplete mode"""

    _echo("\nShellMate Migration Tool\n", bold=True, fg="cyan")
    _echo("Interception mode (preexec hooks) has been removed.")
    _echo("This migration sets up autocomplete mode for your shell.\n")

    windows = _is_windows_target()
    home = os.path.expanduser("~")
    bashrc = os.path.join(home, ".bashrc")

    has_old_bash = _has_legacy_bash_hooks(bashrc)
    has_old_ps = _has_legacy_powershell_hooks()

    if not has_old_bash and not has_old_ps:
        _echo("[OK] No interception mode hooks found.")
        if _profile_integration_ok():
            _echo("[OK] Autocomplete mode already configured!")
            return
        _echo("[!] Autocomplete mode not configured. Run: sm init")
        return

    if has_old_bash:
        _echo("Found old interception mode hooks in .bashrc")
    if has_old_ps:
        _echo("Found old ShellMate hooks in a PowerShell profile")

    if not _confirm("Continue with migration?", default=True):
        return

    if windows:
        if has_old_ps:
            _echo("\nRemoving old PowerShell hooks...")
            for path in _powershell_profile_paths():
                if os.path.exists(path):
                    _remove_legacy_marker_sections(path, markers=("# ShellMate hook",))
        _echo("Installing PowerShell autocomplete hooks...")
        _install_powershell_hook()
    else:
        if not _check_blesh_installed():
            _echo("\nble.sh is required for autocomplete mode.")
            if _confirm("Install ble.sh now?", default=True):
                if not _install_blesh():
                    _echo("Migration aborted.")
                    return
            else:
                _echo("Migration aborted.")
                return

        if has_old_bash:
            _echo("\nRemoving old interception mode hooks from .bashrc...")
            _remove_old_hooks(bashrc)

        _echo("Installing autocomplete hooks...")
        _install_autocomplete_hook()

    _echo("\n[OK] Migration complete!", bold=True, fg="green")
    _echo("\nWhat changed:")
    _echo("  - Removed preexec-based interception hooks (if present)")
    if windows:
        _echo("  - Installed PowerShell adapter for real-time annotations")
    else:
        _echo("  - Installed ble.sh autocomplete integration")
    _echo("  - Preserved FAISS semantic cache for fast lookups")
    _echo("\nNext steps:")
    if windows:
        _echo("  1. Restart PowerShell (or reload your profile)")
    else:
        _echo("  1. Restart your shell (or run: source ~/.bashrc)")
    _echo("  2. Run: sm enable")
    _echo("  3. Start typing commands to see autocomplete!\n")


def _has_legacy_bash_hooks(bashrc_path: str) -> bool:
    if not os.path.exists(bashrc_path):
        return False
    with open(bashrc_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    return "bash_adapter.sh" in content and (
        "preexec" in content or "# ShellMate hook" in content
    )


def _has_legacy_powershell_hooks() -> bool:
    for path in _powershell_profile_paths():
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        # Legacy install.py wrote "# ShellMate hook" without autocomplete marker
        if "# ShellMate hook" in content and "ShellMate Autocomplete" not in content:
            return True
        if "powershell_adapter.ps1" in content and "ShellMate Autocomplete" not in content:
            return True
    return False


def _remove_legacy_marker_sections(path: str, markers=("# ShellMate hook",)):
    """Remove simple one/two-line hook blocks starting with markers."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    new_lines = []
    skip_section = False
    for line in lines:
        if any(marker in line for marker in markers):
            skip_section = True
            continue
        if skip_section:
            stripped = line.strip()
            if not stripped:
                skip_section = False
                continue
            if stripped.startswith("source") or stripped.startswith("."):
                skip_section = False
                continue
            skip_section = False
        new_lines.append(line)

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    _echo(f"[OK] Cleaned hooks in {path}")


def _remove_old_hooks(bashrc_path):
    """Remove old ShellMate preexec hooks from .bashrc"""
    _remove_legacy_marker_sections(bashrc_path, markers=("# ShellMate hook",))
