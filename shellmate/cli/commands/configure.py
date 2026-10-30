import click
from shellmate.config.credentials import CREDENTIAL_KEYS, get_credential_status
from shellmate.config.paths import CREDENTIALS_FILE


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
