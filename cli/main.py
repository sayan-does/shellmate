import click


@click.group()
@click.version_option(version="0.1.0", prog_name="shellmate")
def cli():
    """ShellMate - Intelligent Command Safety Layer for Modern Terminals"""
    pass


@cli.command()
def enable():
    """Enable ShellMate daemon and command interception"""
    click.echo("Enabling ShellMate...")
    from daemon.lifecycle import start_daemon
    start_daemon()
    click.echo("ShellMate daemon started.")


@cli.command()
def disable():
    """Disable ShellMate daemon and command interception"""
    click.echo("Disabling ShellMate...")
    from daemon.lifecycle import stop_daemon
    stop_daemon()
    click.echo("ShellMate daemon stopped.")


@cli.command()
def status():
    """Show ShellMate daemon and provider status"""
    from daemon.lifecycle import check_daemon_status
    from providers.router import get_provider_status
    import json
    result = check_daemon_status()
    result["providers"] = get_provider_status()
    click.echo(json.dumps(result, indent=2))


@cli.command()
@click.option("--verbose", is_flag=True, help="Output detailed health report")
def doctor(verbose):
    """Run environment diagnostics"""
    from environment.detector import detect_environment
    from daemon.lifecycle import check_daemon_status
    from providers.router import get_provider_status
    import json
    env = detect_environment()
    if verbose:
        report = {
            "environment": env,
            "daemon": check_daemon_status(),
            "providers": get_provider_status(),
        }
        from daemon.observability import get_metrics_summary
        report["metrics"] = get_metrics_summary()
        click.echo(json.dumps(report, indent=2))
    else:
        click.echo(json.dumps(env, indent=2))


@cli.command()
@click.argument("key", required=False)
@click.argument("value", required=False)
def config(key, value):
    """View or edit ShellMate configuration"""
    from config.defaults import get_default_config
    from config.credentials import CREDENTIAL_KEYS, load_env, save_env, get_credential_status
    import json

    if key and key.upper() in CREDENTIAL_KEYS:
        env = load_env()
        env[key.upper()] = value or ""
        save_env(env)
        click.echo(click.style(f"[OK] {key.upper()} updated", fg="green"))
        return

    if key and value:
        click.echo(f"Config update: {key}={value}")
        return

    cfg = get_default_config()
    creds = get_credential_status()
    output = {
        "credentials": {
            k: {
                "configured": v["configured"],
                "key": v["masked"] if v["configured"] else None,
            }
            for k, v in creds.items()
        },
        "settings": cfg,
    }
    click.echo(json.dumps(output, indent=2))


@cli.command()
def logs():
    """Tail ShellMate daemon logs"""
    from daemon.lifecycle import tail_logs
    tail_logs()


@cli.command(name="cache")
@click.argument("action", type=click.Choice(["clear"]))
def cache_command(action):
    """Manage ShellMate semantic cache"""
    from cache.semantic_cache import clear_cache
    clear_cache()
    click.echo("Cache cleared.")


@cli.command()
def providers():
    """List configured AI providers"""
    from providers.router import get_provider_status
    import json
    status = get_provider_status()
    click.echo(json.dumps(status, indent=2))


@cli.command(name="update-rules")
def update_rules():
    """Validate and reload local rule packs"""
    from rules.engine import load_rules
    rules = load_rules()
    click.echo(f"Validated {len(rules)} rules. Reloaded successfully.")


from cli.commands.analyze import analyze
from cli.commands.install import install
from cli.commands.uninstall import uninstall
from cli.commands.configure import configure

cli.add_command(analyze)
cli.add_command(install)
cli.add_command(uninstall)
cli.add_command(configure)


if __name__ == "__main__":
    cli()
