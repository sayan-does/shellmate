import os
import click
from shellmate.environment.detector import detect_environment

SHELLMATE_DIR = os.path.expanduser("~/.shellmate")
HOOKS_DIR = os.path.join(SHELLMATE_DIR, "hooks")


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


def _remove_hook(shell):
    rc_files = _get_rc_file(shell)
    removed = False

    for rc_file in rc_files:
        if not os.path.exists(rc_file):
            continue
        try:
            with open(rc_file, "r") as f:
                lines = f.readlines()

            new_lines = []
            skip_next = False
            for line in lines:
                if "# ShellMate hook" in line:
                    skip_next = True
                    removed = True
                    continue
                if skip_next:
                    skip_next = False
                    removed = True
                    continue
                if "shellmate" in line.lower() and ("source" in line or ". " in line):
                    if HOOKS_DIR in line:
                        removed = True
                        continue
                new_lines.append(line)

            with open(rc_file, "w") as f:
                f.writelines(new_lines)
        except OSError:
            pass

    return removed


@click.command()
@click.option("--dry-run", is_flag=True, help="Show what would be removed without making changes")
def uninstall(dry_run):
    """Remove ShellMate and all hooks"""
    env = detect_environment()
    shell = env["shell"]

    if dry_run:
        rc_files = _get_rc_file(shell)
        click.echo(f"[DRY RUN] Would remove ShellMate hooks for {shell}")
        for rc in rc_files:
            click.echo(f"[DRY RUN] Would remove hooks from: {rc}")
        return

    removed = _remove_hook(shell)
    if removed:
        click.echo("Shell hooks removed from RC files.")
    else:
        click.echo("No ShellMate hooks found in RC files.")

    click.echo("ShellMate uninstalled.")
