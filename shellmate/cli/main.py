import sys
import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from shellmate.cli.parser import parse_argv, ParsedCommand, Action, ExitCode
from shellmate.cli.commands.enable import enable
from shellmate.cli.commands.disable import disable
from shellmate.cli.commands.status import status
from shellmate.cli.commands.config import config
from shellmate.cli.version import VERSION

console = Console()

_plain_console = Console(no_color=True)


def _get_console(parsed=None):
    if parsed and getattr(parsed, 'no_color', False):
        return _plain_console
    return console


def print_error_panel(error: str, suggestion: str = None, next_steps: list = None, _console=None):
    c = _console or console
    text = Text()
    text.append("Error: ", style="bold red")
    text.append(error, style="red")
    if suggestion:
        text.append("\n\n")
        text.append("Suggestion: ", style="bold yellow")
        text.append(suggestion, style="yellow")
    if next_steps:
        text.append("\n\n")
        text.append("Next steps:", style="bold cyan")
        for i, step in enumerate(next_steps, 1):
            text.append(f"\n  {i}. {step}", style="cyan")
    c.print(Panel(text, border_style="red", title="[bold red]ShellMate Error[/bold red]"))


def print_usage(c: Console = None):
    from shellmate.ui.scenes.help import print_help
    print_help(c or console)


def _safe_echo(message: str):
    """click.echo that survives Windows consoles rejecting emoji/codepoints."""
    try:
        click.echo(message)
    except UnicodeEncodeError:
        click.echo(message.encode("ascii", errors="replace").decode("ascii"))


def main():
    parsed = parse_argv(sys.argv[1:])
    c = _get_console(parsed)

    if parsed.exit_code != ExitCode.SUCCESS:
        print_error_panel(parsed.error, parsed.suggestion, _console=c)
        sys.exit(parsed.exit_code.value)

    try:
        if parsed.action == Action.ENABLE:
            enable()
            sys.exit(ExitCode.SUCCESS.value)

        elif parsed.action == Action.DISABLE:
            disable()
            sys.exit(ExitCode.SUCCESS.value)

        elif parsed.action == Action.STATUS:
            status()
            sys.exit(ExitCode.SUCCESS.value)

        elif parsed.action == Action.CONFIG:
            config()
            sys.exit(ExitCode.SUCCESS.value)

        elif parsed.action == Action.INSTALL:
            from shellmate.cli.commands.install import install
            # Click Command: invoke underlying callback, not Command.__call__
            # Accept --dry-run before or after the subcommand
            dry_run = parsed.dry_run or ("--dry-run" in (getattr(parsed, "tokens", None) or []))
            install.callback(dry_run=dry_run)
            sys.exit(ExitCode.SUCCESS.value)

        elif parsed.action == Action.UNINSTALL:
            from shellmate.cli.commands.uninstall import uninstall
            dry_run = parsed.dry_run or ("--dry-run" in (getattr(parsed, "tokens", None) or []))
            uninstall.callback(dry_run=dry_run)
            sys.exit(ExitCode.SUCCESS.value)

        elif parsed.action == Action.HELP:
            print_usage(c)
            sys.exit(ExitCode.SUCCESS.value)

        elif parsed.action == Action.VERSION:
            c.print(f"ShellMate v{VERSION}")
            sys.exit(ExitCode.SUCCESS.value)

    except KeyboardInterrupt:
        c.print("\n[yellow]Interrupted[/]")
        sys.exit(ExitCode.TEMP_ERROR.value)
    except click.Abort:
        c.print("\n[yellow]Aborted[/]")
        sys.exit(ExitCode.TEMP_ERROR.value)
    except Exception as e:
        print_error_panel(f"Internal error: {e}", "Run 'sm --help' or check logs", _console=c)
        sys.exit(ExitCode.INTERNAL_ERROR.value)


if __name__ == "__main__":
    main()
