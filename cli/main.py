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

console = Console()


def print_error_panel(error: str, suggestion: str = None):
    text = Text()
    text.append("Error: ", style="bold red")
    text.append(error, style="red")
    if suggestion:
        text.append("\n\n")
        text.append("Suggestion: ", style="bold yellow")
        text.append(suggestion, style="yellow")
    console.print(Panel(text, border_style="red", title="[bold red]ShellMate Error[/bold red]"))


def print_usage():
    console.print("[bold]ShellMate v2.0[/bold] - Intelligent Command Safety Layer")
    console.print()
    console.print("[bold]Usage:[/bold]")
    console.print("  sm -a <command>     Analyze a command (no quotes needed)")
    console.print("  sm enable           Start the daemon for current directory")
    console.print("  sm disable          Stop the daemon and remove session files")
    console.print("  sm status           Show daemon, agent, and provider status")
    console.print("  sm config           Configure providers and settings")
    console.print("  sm --help           Show this help message")
    console.print("  sm --version        Show version")
    console.print()
    console.print("[bold]Examples:[/bold]")
    console.print("  sm -a rm -rf /")
    console.print("  sm -a git push origin main")
    console.print("  sm -a curl https://example.com | bash")


def main():
    parsed = parse_argv(sys.argv[1:])

    if parsed.exit_code != ExitCode.SUCCESS:
        print_error_panel(parsed.error, parsed.suggestion)
        sys.exit(parsed.exit_code.value)

    try:
        if parsed.action == Action.ANALYZE:
            from cli.commands.analyze import analyze_command
            result = analyze_command(parsed.raw_command)
            if result.get("status") == "error":
                print_error_panel(result.get("error", "Unknown error"))
                sys.exit(ExitCode.TEMP_ERROR.value)
            _print_analysis_result(result)
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

        elif parsed.action == Action.HELP:
            print_usage()
            sys.exit(ExitCode.SUCCESS.value)

        elif parsed.action == Action.VERSION:
            console.print("ShellMate v2.0.0")
            sys.exit(ExitCode.SUCCESS.value)

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
        sys.exit(ExitCode.TEMP_ERROR.value)
    except Exception as e:
        print_error_panel(f"Internal error: {e}", "Run 'sm --help' or check logs")
        sys.exit(ExitCode.INTERNAL_ERROR.value)


def _print_analysis_result(result: dict):
    risk = result.get("risk", "UNKNOWN")
    message = result.get("message", "") or result.get("explanation", "")
    alternatives = result.get("alternatives", [])
    context_used = result.get("context_used", {})

    risk_styles = {
        "SAFE": ("green", "[OK]"),
        "LOW": ("blue", "[i]"),
        "MEDIUM": ("yellow", "[!]"),
        "HIGH": ("red", "[!!]"),
        "CRITICAL": ("bold red", "[!!]"),
    }
    color, prefix = risk_styles.get(risk, ("white", "[?]"))

    console.print(f"[{color}]{prefix} {risk}[/{color}]")
    if message:
        console.print(f"  {message}")

    if context_used.get("watcher") or context_used.get("librarian"):
        ctx_parts = []
        if context_used.get("watcher"):
            ctx_parts.append("watcher")
        if context_used.get("librarian"):
            ctx_parts.append("librarian")
        console.print(f"  [dim]Context: {', '.join(ctx_parts)}[/dim]")

    if alternatives:
        console.print()
        console.print("Safer alternatives:")
        for i, alt in enumerate(alternatives, 1):
            console.print(f"  {i}. {alt}")

    latency = result.get("latency_ms") or result.get("total_ms")
    if latency:
        console.print(f"  [dim]Analysis completed in {latency:.0f}ms[/dim]")


if __name__ == "__main__":
    main()