from rich.console import Console
from rich.text import Text
from rich.panel import Panel

from shellmate.cli.version import VERSION
from shellmate.ui.runtime import tokens
from shellmate.ui.runtime.console_factory import ConsoleFactory
from shellmate.ui.scenes.help import print_help, render_help

console = ConsoleFactory().create()

# Kept for any external imports; enable scene uses its own compact logo.
BANNER_ART = "[bold cyan]ShellMate[/]"


def print_banner():
    """Minimal wordmark banner (no giant ASCII). Bold logo lives on sm enable only."""
    width = tokens.content_width(console.width)
    body = Text.assemble(
        Text("ShellMate", style=f"bold {tokens.ACCENT}"),
        Text(f"  v{VERSION}", style=tokens.MUTED),
        Text("\n"),
        Text("Intelligent command safety layer", style=tokens.MUTED),
    )
    console.print(
        Panel(body, border_style=tokens.ACCENT, padding=(1, 2), width=width, expand=False)
    )


def render_enable_panel(stages: list[tuple[str, bool]]) -> Panel:
    """Deprecated compatibility wrapper — prefer ui.scenes.enable.render_enable_frame."""
    from shellmate.ui.scenes.stages import StageStatus, StageView, EnableViewState
    from shellmate.ui.scenes.enable import render_enable_frame

    views = [
        StageView(
            key=label,
            label=label,
            status=StageStatus.DONE if done else StageStatus.INCOMPLETE,
        )
        for label, done in stages
    ]
    state = EnableViewState(stages=views, ready=all(d for _, d in stages), timed_out=not all(d for _, d in stages))
    frame = render_enable_frame(state, console_width=console.width, settled=True)
    return frame  # type: ignore[return-value]


def print_usage():
    print_help(console)
