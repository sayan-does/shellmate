import click
from ipc.client import analyze_command as send_to_daemon


@click.command()
@click.argument("command", nargs=-1, required=True)
@click.option("--quiet", is_flag=True, help="Suppress warnings for scripts")
def analyze(command, quiet):
    """Analyze a shell command for safety"""
    cmd = " ".join(command)
    result = send_to_daemon(cmd)

    if result.get("status") == "error":
        click.echo(f"Error: {result.get('error', 'Unknown error')}", err=True)
        return

    risk = result.get("risk", "UNKNOWN")
    message = result.get("message", "") or result.get("explanation", "")
    alternatives = result.get("alternatives", [])

    risk_colors = {
        "SAFE": "green",
        "LOW": "blue",
        "MEDIUM": "yellow",
        "HIGH": "red",
        "CRITICAL": "red",
    }

    color = risk_colors.get(risk, "white")

    if quiet:
        click.echo(result)
        return

    if risk == "SAFE":
        click.echo(click.style("[OK] SAFE", fg="green"))
    elif risk == "LOW":
        click.echo(click.style(f"[i] LOW: {message}", fg="blue"))
    elif risk == "MEDIUM":
        click.echo(click.style(f"[!] MEDIUM: {message}", fg="yellow"))
    elif risk == "HIGH":
        click.echo(click.style(f"[!!] HIGH: {message}", fg="red"))
    elif risk == "CRITICAL":
        click.echo(click.style(f"[!!] CRITICAL: {message}", fg="red", bold=True))
        click.echo()
        if not click.confirm(click.style("Do you want to proceed?", fg="red"), default=False):
            click.echo("Command cancelled.")
            return

    if alternatives:
        click.echo()
        click.echo("Safer alternatives:")
        for i, alt in enumerate(alternatives, 1):
            click.echo(f"  {i}. {alt}")

    if "latency" in result:
        click.echo()
        click.echo(f"Analysis completed in {result.get('total_ms', 0):.0f}ms")
