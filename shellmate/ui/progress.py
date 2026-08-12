import time
import threading
from contextlib import contextmanager
from rich.console import Console
from rich.status import Status
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich import box

from shellmate.ui.runtime import tokens

STAGES = [
    (">  Routing command...", "dots12"),
    ("*  Gathering context...", "dots12"),
    ("*  Analyzing risk...", "dots12"),
    (">  Building usage guide...", "dots12"),
    ("*  Formatting result...", "dots12"),
]

STAGE_TIMINGS = {
    "sanitizer": 2,
    "parser": 5,
    "rules": 10,
    "cache": 1,
    "command_chain": 10,
    "supervisor": 50,
    "watcher": 200,
    "environment": 30,
    "librarian": 300,
    "risk_analyzer": 200,
    "remediation": 150,
    "command_guide": 100,
    "formatter": 5,
    "query_agent": 100,
}


@contextmanager
def analysis_progress(console: Console, interval: float = 0.4, verbose: bool = False):
    """Progress indicator with optional live agent view."""
    # Plain / non-TTY: no animation
    if not console.is_terminal or console.no_color:
        yield
        return

    if verbose:
        with _live_progress_table(console):
            yield
    else:
        stop = threading.Event()
        idx = [0]

        def cycle(status: Status):
            while not stop.is_set():
                text, spinner = STAGES[idx[0] % len(STAGES)]
                status.update(text, spinner=spinner)
                idx[0] += 1
                stop.wait(interval)

        with console.status(STAGES[0][0], spinner=STAGES[0][1]) as status:
            t = threading.Thread(target=cycle, args=(status,), daemon=True)
            t.start()
            try:
                yield
            finally:
                stop.set()
                t.join(timeout=1.0)


@contextmanager
def _live_progress_table(console: Console):
    icon_map = tokens.icons(ascii_safe=console.no_color)
    status_icons = {
        "pending": icon_map["pending"],
        "running": icon_map["running"],
        "done": icon_map["done"],
        "cached": icon_map["done"],
        "skipped": icon_map["skip"],
        "error": icon_map["error"],
    }

    agent_state = {
        stage: {"status": "pending", "elapsed_ms": 0}
        for stage in STAGE_TIMINGS.keys()
    }

    def build_table() -> Panel:
        table = Table(show_header=True, box=box.SIMPLE, expand=False)
        table.add_column("Stage", style=tokens.ACCENT, no_wrap=True)
        table.add_column("Status", style="white", justify="center", width=8)
        table.add_column("Time", justify="right", style=tokens.WARNING, width=10)

        for stage, data in agent_state.items():
            status = data["status"]
            icon = status_icons.get(status, "·")
            elapsed = f"{data['elapsed_ms']}ms" if data["elapsed_ms"] > 0 else "—"
            stage_name = stage.replace("_", " ").title()
            table.add_row(stage_name, icon, elapsed)

        width = tokens.content_width(console.width)
        return Panel(
            table,
            title="[bold]Analysis[/]",
            border_style=tokens.ACCENT,
            width=width,
            expand=False,
        )

    with Live(build_table(), console=console, refresh_per_second=8, transient=True) as live:
        try:
            for stage, duration_ms in STAGE_TIMINGS.items():
                agent_state[stage]["status"] = "running"
                live.update(build_table())
                # Cap simulated waits so verbose mode cannot dominate wall clock
                time.sleep(min(duration_ms, 40) / 1000.0)
                agent_state[stage]["status"] = "done"
                agent_state[stage]["elapsed_ms"] = duration_ms
                live.update(build_table())
            yield
        except KeyboardInterrupt:
            for stage in agent_state:
                if agent_state[stage]["status"] == "running":
                    agent_state[stage]["status"] = "error"
            live.update(build_table())
            raise
