import os
import click
from environment.detector import detect_environment

SHELLMATE_DIR = os.path.expanduser("~/.shellmate")
HOOKS_DIR = os.path.join(SHELLMATE_DIR, "hooks")


def _get_adapter_source(shell):
    adapter_map = {
        "bash": "bash_adapter.sh",
        "zsh": "zsh_adapter.zsh",
        "powershell": "powershell_adapter.ps1",
    }
    return adapter_map.get(shell)


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


def _install_hook(shell):
    os.makedirs(HOOKS_DIR, exist_ok=True)

    adapter_name = _get_adapter_source(shell)
    if not adapter_name:
        return False, f"No adapter available for {shell}"

    adapter_path = os.path.join(os.path.dirname(__file__), "..", "..", "adapters", adapter_name)
    adapter_path = os.path.abspath(adapter_path)

    if not os.path.exists(adapter_path):
        return False, f"Adapter file not found: {adapter_path}"

    dest_path = os.path.join(HOOKS_DIR, adapter_name)
    with open(adapter_path, "r") as src:
        with open(dest_path, "w") as dst:
            dst.write(src.read())

    rc_files = _get_rc_file(shell)
    if not rc_files:
        return False, f"No RC file known for {shell}"

    source_line = ""
    if shell == "powershell":
        source_line = f". '{dest_path}'\n"
    else:
        source_line = f"source {dest_path}\n"

    installed = False
    for rc_file in rc_files:
        if os.path.exists(rc_file):
            with open(rc_file, "r") as f:
                content = f.read()
            if source_line.strip() in content:
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
        return True, f"Hook installed for {shell}"
    return False, f"Could not install hook for {shell}"


def _prompt_credential_setup():
    click.echo()
    click.echo(click.style("  -------------------------------------------------", fg="cyan"))
    click.echo(click.style("  ShellMate Credential Setup", bold=True, fg="cyan"))
    click.echo(click.style("  -------------------------------------------------", fg="cyan"))
    click.echo()
    click.echo("  ShellMate needs API keys for AI-powered analysis and remediation.")
    click.echo("  You can set them up now or skip and configure later with:")
    click.echo("    " + click.style("shellmate configure", bold=True))
    click.echo()

    if not click.confirm(click.style("  Would you like to configure API keys now?", bold=True), default=True):
        click.echo()
        click.echo("  You can always run " + click.style("shellmate configure", bold=True) + " later.")
        click.echo("  Until then, ShellMate will use deterministic rule-based analysis.")
        return

    from cli.commands.configure import print_header, print_status, prompt_for_key
    from config.credentials import CREDENTIAL_KEYS, load_env, save_env

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
def install():
    """Install ShellMate and shell hooks"""
    env = detect_environment()
    shell = env["shell"]
    click.echo(f"Detected: {env['os']} / {shell}")

    success, message = _install_hook(shell)
    if success:
        click.echo(click.style(f"[OK] {message}", fg="green"))
        click.echo("Shell hooks installed. Restart your shell or source the RC file.")
        _prompt_credential_setup()
    else:
        click.echo(click.style(f"[!!] {message}", fg="red"), err=True)
