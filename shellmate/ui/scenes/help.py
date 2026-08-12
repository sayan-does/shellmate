"""Help / usage scene — static, minimal (no logo)."""

from __future__ import annotations

from rich.console import Console, Group
from rich.table import Table
from rich.text import Text

from shellmate.cli.version import VERSION
from shellmate.ui.runtime import tokens


def render_help(*, console_width: int | None = None) -> Group:
    width_hint = console_width or tokens.CONTENT_MAX_WIDTH
    _ = tokens.content_width(width_hint)

    usage = Table(show_header=False, box=None, padding=(0, 2))
    usage.add_column(style=tokens.ACCENT, no_wrap=True)
    usage.add_column(overflow="fold")
    rows = [
        ("sm install", "Install shell hooks"),
        ("sm config", "Configure providers and settings"),
        ("sm enable", "Start the daemon for current directory"),
        ("sm disable", "Stop the daemon and remove session files"),
        ("sm status", "Show daemon, agent, and provider status"),
        ("sm uninstall", "Remove shell hooks"),
        ("sm --help", "Show this help message"),
        ("sm --version", "Show version"),
        ("sm --no-color <cmd>", "Plain text output (no animation)"),
    ]
    for cmd, desc in rows:
        usage.add_row(cmd, desc)

    return Group(
        Text(f"ShellMate v{VERSION}", style=f"bold {tokens.ACCENT}"),
        Text("Intelligent command safety layer", style=tokens.MUTED),
        Text(""),
        Text("Usage", style=tokens.TITLE),
        usage,
        Text(""),
        Text("Examples", style=tokens.TITLE),
        Text("  $ sm enable", style=tokens.MUTED),
        Text("  $ sm status", style=tokens.MUTED),
        Text(""),
        Text("Run sm enable to start the daemon.", style=tokens.MUTED),
    )


def print_help(console: Console | None = None) -> None:
    from shellmate.ui.runtime.console_factory import ConsoleFactory

    c = console or ConsoleFactory().create()
    c.print(render_help(console_width=c.width))
