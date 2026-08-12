import os
import click
from shellmate.config.credentials import CREDENTIAL_KEYS, load_env, save_env, get_credential_status
from shellmate.config.paths import CREDENTIALS_FILE
from shellmate.environment.detector import detect_environment


def print_header():
    click.echo()
    click.echo(click.style("  +================================================+", fg="cyan"))
    click.echo(click.style("  |         ShellMate Credential Setup              |", fg="cyan"))
    click.echo(click.style("  +================================================+", fg="cyan"))
    click.echo()
    click.echo("  Configure your API keys to enable AI-powered features.")
    click.echo("  Keys are stored in: " + click.style(str(CREDENTIALS_FILE), bold=True))
    click.echo()


def print_status():
    status = get_credential_status()
    click.echo("  Current status:")
    for key, info in status.items():
        if info["configured"]:
            icon = click.style("[OK]", fg="green")
            value = click.style(info["masked"], fg="green")
        else:
            icon = click.style("[--]", fg="red")
            value = click.style("not set", fg="red", dim=True)
        click.echo(f"    {icon} {info['label']}: {value}")
    click.echo()


def prompt_for_key(key_name, current_value):
    info = CREDENTIAL_KEYS[key_name]
    label = info["label"]
    description = info["description"]
    doc_url = info.get("doc_url", "")

    click.echo(click.style(f"  -- {label} --", bold=True))
    click.echo(f"     {description}")
    if doc_url:
        click.echo(f"     Get it at: {click.style(doc_url, fg='cyan')}")
    click.echo()

    if current_value:
        masked = current_value[:4] + "****" + current_value[-4:]
        prompt_text = f"  Enter key (leave empty to keep [{masked}]): "
    else:
        prompt_text = f"  Enter key (leave empty to skip): "

    new_value = click.prompt(prompt_text, default="", show_default=False)
    new_value = new_value.strip()

    if not new_value and current_value:
        return current_value
    if not new_value:
        return ""

    return new_value


@click.command()
@click.option("--show", is_flag=True, help="Show current credential status without editing")
def configure(show):
    """Configure API credentials for AI providers"""
    shell = detect_environment()["shell"]

    if show:
        print_header()
        print_status()
        return

    env = load_env()

    print_header()
    print_status()

    click.echo("  Enter your API keys below. You can skip any key by leaving it empty.")
    click.echo()

    for key_name in CREDENTIAL_KEYS:
        current = env.get(key_name, os.environ.get(key_name, ""))
        new_value = prompt_for_key(key_name, current)
        env[key_name] = new_value

    save_env(env)

    click.echo()
    click.echo(click.style("  ✓ Credentials saved!", fg="green"))

    print_status()

    has_keys = any(env.values())
    if has_keys:
        click.echo()
        click.echo("  " + click.style("Next steps:", bold=True))
        click.echo("    1. Start the daemon:  " + click.style("shellmate enable", bold=True))
        click.echo("    2. Use Tab completion for consequence preview")

        missing = [k for k in CREDENTIAL_KEYS if not env.get(k)]
        if missing:
            click.echo()
            click.echo("  " + click.style("Note:", bold=True) + " Some keys are still missing. AI analysis will use fallback mode.")

        shell_source = {
            "bash": "source ~/.shellmate/.env",
            "zsh": "source ~/.shellmate/.env",
            "powershell": ". ~\\.shellmate\\.env",
        }
        src_cmd = shell_source.get(shell, "source ~/.shellmate/.env")
        if shell == "powershell":
            src_cmd = ". $HOME\\.shellmate\\.env"
        click.echo(f"    3. Load credentials: {click.style(src_cmd, bold=True)}")
        click.echo(f"    4. Or restart your shell to pick up the .env file")
    else:
        click.echo()
        click.echo("  " + click.style("No keys configured.", bold=True) + " AI features will use fallback mode.")
        click.echo("  Run " + click.style("shellmate configure", bold=True) + " anytime to set them up.")
