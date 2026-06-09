import json
import sys
import click
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from cli.parser import parse_argv, ParsedCommand, Action, ExitCode
from cli.commands.enable import enable
from cli.commands.disable import disable
from cli.commands.status import status
from cli.commands.config import config
from cli.version import VERSION

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


def print_usage():
    from ui.banner import print_banner as _print_banner
    _print_banner()


def main():
    parsed = parse_argv(sys.argv[1:])
    c = _get_console(parsed)

    if parsed.exit_code != ExitCode.SUCCESS:
        print_error_panel(parsed.error, parsed.suggestion, _console=c)
        sys.exit(parsed.exit_code.value)

    try:
        if parsed.action == Action.ANALYZE:
            from cli.commands.analyze import analyze_command
            from ui.progress import analysis_progress
            if parsed.quiet:
                result = analyze_command(parsed.raw_command)
            else:
                with analysis_progress(c):
                    result = analyze_command(parsed.raw_command)
            if result.get("status") == "error":
                if parsed.quiet:
                    print(json.dumps({"risk": "UNKNOWN", "error": result.get("error", "Unknown error")}))
                else:
                    print_error_panel(result.get("error", "Unknown error"), _console=c)
                sys.exit(ExitCode.TEMP_ERROR.value)
            if parsed.quiet:
                print(json.dumps(result))
            else:
                _print_analysis_result(result, c)
            sys.exit(ExitCode.SUCCESS.value)

        elif parsed.action == Action.ENABLE:
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
            from cli.commands.install import install
            install(dry_run=parsed.dry_run)
            sys.exit(ExitCode.SUCCESS.value)

        elif parsed.action == Action.UNINSTALL:
            from cli.commands.uninstall import uninstall
            uninstall(dry_run=parsed.dry_run)
            sys.exit(ExitCode.SUCCESS.value)

        elif parsed.action == Action.HELP:
            print_usage()
            sys.exit(ExitCode.SUCCESS.value)

        elif parsed.action == Action.VERSION:
            c.print(f"ShellMate v{VERSION}")
            sys.exit(ExitCode.SUCCESS.value)

    except KeyboardInterrupt:
        c.print("\n[yellow]Interrupted[/]")
        sys.exit(ExitCode.TEMP_ERROR.value)
    except Exception as e:
        print_error_panel(f"Internal error: {e}", "Run 'sm --help' or check logs", _console=c)
        sys.exit(ExitCode.INTERNAL_ERROR.value)


def _print_analysis_result(result: dict, c: Console = None):
    c = c or console
    import ui.analysis as analysis_mod
    orig = analysis_mod.console
    analysis_mod.console = c
    try:
        analysis_mod.render_analysis(result)
    finally:
        analysis_mod.console = orig


if __name__ == "__main__":
    main()