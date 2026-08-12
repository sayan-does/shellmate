"""Enable scene — bold logo moment + live stage morph + quiet usage settle."""

from __future__ import annotations

import time
from typing import Callable, Iterable, Optional

from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.text import Text

from shellmate.cli.version import VERSION
from shellmate.ui.runtime.console_factory import ConsoleFactory
from shellmate.ui.runtime.live_scene import LiveScene
from shellmate.ui.runtime.motion_policy import MotionPolicy, motion_from_env
from shellmate.ui.runtime import tokens
from shellmate.ui.scenes.stages import (
    CANONICAL_STAGES,
    EnableViewState,
    StageStatus,
    next_reveal_target,
    normalize_completed,
    reduce_enable_state,
)

# Compact logo (fits content max-width); dropped on narrow terminals.
_LOGO_LINES = [
    r"  ____  _          _ _ __  __       _        ",
    r" / ___|| |__   ___| | |  \/  | __ _| |_ ___ ",
    r" \___ \| '_ \ / _ \ | | |\/| |/ _` | __/ _ \\",
    r"  ___) | | | |  __/ | | |  | | (_| | ||  __/",
    r" |____/|_| |_|\___|_|_|_|  |_|\__,_|\__\___|",
]


def render_enable_frame(
    state: EnableViewState,
    *,
    console_width: int,
    ascii_safe: bool = False,
    settled: bool = False,
) -> RenderableType:
    """Build one enable-scene frame. Width-aware; no fixed 110 panels."""
    width = tokens.content_width(console_width)
    icon = tokens.icons(ascii_safe=ascii_safe)
    lines: list[Text | str] = []

    if tokens.show_logo(console_width):
        for row in _LOGO_LINES:
            lines.append(Text(row, style=tokens.ACCENT))
        lines.append("")
        lines.append(Text(f"ShellMate v{VERSION}", style=tokens.MUTED))
    else:
        lines.append(Text(f"ShellMate v{VERSION}", style=f"bold {tokens.ACCENT}"))

    lines.append("")
    lines.append(Text("Startup", style=tokens.TITLE))

    for stage in state.stages:
        if stage.status == StageStatus.DONE:
            mark = Text(f"  {icon['done']} ", style=tokens.SUCCESS)
            label = Text(stage.label, style=tokens.SUCCESS)
        elif stage.status == StageStatus.RUNNING:
            mark = Text(f"  {icon['running']} ", style=tokens.ACCENT)
            label = Text(stage.label, style=tokens.ACCENT)
        elif stage.status == StageStatus.INCOMPLETE:
            mark = Text(f"  {icon['pending']} ", style=tokens.MUTED)
            label = Text(stage.label, style=tokens.MUTED)
        else:
            mark = Text(f"  {icon['pending']} ", style=tokens.MUTED)
            label = Text(stage.label, style=tokens.MUTED)
        lines.append(Text.assemble(mark, label))

    if settled:
        lines.append("")
        if state.timed_out:
            lines.append(Text("Startup timed out. Daemon may not be ready.", style=tokens.ERROR))
            lines.append(Text("Run sm status to check daemon state.", style=tokens.MUTED))
        else:
            lines.append(Text("Active features", style=tokens.TITLE))
            lines.append(Text.assemble(
                Text(f"  {icon['done']} ", style=tokens.SUCCESS),
                Text("Autocomplete: active", style=tokens.SUCCESS),
            ))
            lines.append(Text.assemble(
                Text(f"  {icon['done']} ", style=tokens.SUCCESS),
                Text("Consequence preview: active", style=tokens.SUCCESS),
            ))
            lines.append("")
            lines.append(Text("Usage", style=tokens.TITLE))
            from rich.table import Table
            usage = Table(show_header=False, box=None, padding=(0, 2), collapse_padding=True)
            usage.add_column(style=tokens.ACCENT, no_wrap=True)
            usage.add_column(overflow="fold")
            usage.add_row("sm status", "Show daemon status")
            usage.add_row("sm disable", "Stop ShellMate")
            lines.append(usage)

    body = Group(*lines)
    return Panel(
        body,
        title=f"[bold {tokens.ACCENT}]ShellMate[/] [dim]v{VERSION}[/]",
        border_style=tokens.ACCENT,
        padding=(1, 2),
        width=width,
        expand=False,
    )


def _hold_last_completed(
    prev: list[str],
    incoming: Optional[Iterable[str]],
    current: Optional[str],
) -> list[str]:
    """IPC blip (both None) keeps previous completed set — no reset flicker."""
    if incoming is None and current is None:
        return list(prev)
    # incoming None but current set → legacy expand via normalize
    return normalize_completed(incoming, current)


StagePoll = Callable[[], tuple[Optional[list[str]], Optional[str]]]
# Returns (startup_stages_completed | None on blip, startup_stage | None)


def run_enable_scene(
    *,
    poll: StagePoll,
    console: Optional[Console] = None,
    plain: bool = False,
    ascii_safe: bool = False,
    timeout: float = 30.0,
    policy: Optional[MotionPolicy] = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    poll_interval: float = 0.15,
) -> bool:
    """Live enable scene. Returns True if ready, False on timeout.

    Animation failure never raises — falls back to static settle.
    """
    factory_plain = plain
    if console is None:
        cf = ConsoleFactory(no_color=plain, force_terminal=False if plain else None)
        console = cf.create()
        factory_plain = cf.is_plain() or plain

    policy = policy or motion_from_env(plain=factory_plain)
    ascii_safe = ascii_safe or factory_plain

    scene = LiveScene(console, plain=factory_plain)
    last_completed: list[str] = []
    revealed = 0
    ready = False
    timed_out = False
    artificial_spent_ms = 0.0
    saw_ready_at: Optional[float] = None

    initial = reduce_enable_state(completed=[], revealed_through=1)
    try:
        scene.start(render_enable_frame(initial, console_width=console.width, ascii_safe=ascii_safe))
    except Exception:
        pass

    # Ensure at least the first stage shows as running while IPC is not up yet
    revealed = 1
    scene.update(
        render_enable_frame(
            reduce_enable_state(completed=[], revealed_through=1),
            console_width=console.width,
            ascii_safe=ascii_safe,
        )
    )

    start = time.monotonic()
    try:
        while time.monotonic() - start < timeout:
            try:
                completed_raw, current = poll()
            except Exception:
                completed_raw, current = None, None

            last_completed = _hold_last_completed(last_completed, completed_raw, current)
            target = next_reveal_target(last_completed, current)
            # Keep a live tip visible before the daemon answers
            if target == 0:
                target = 1

            if "ready" in last_completed and saw_ready_at is None:
                saw_ready_at = time.monotonic()

            # Ordered reveal toward target
            while revealed < target:
                catching_up = target - revealed
                remaining_budget_s = (
                    policy.clamp_artificial_budget(artificial_spent_ms)
                    if saw_ready_at is not None
                    else None
                )
                if saw_ready_at is not None and remaining_budget_s is not None and remaining_budget_s <= 0:
                    revealed = target
                    break

                if saw_ready_at is not None:
                    # Daemon already ready — paced ordered replay, clamped by budget
                    step_delay = policy.dwell_seconds() + policy.stagger_seconds()
                    step_delay = min(step_delay, remaining_budget_s / catching_up)
                elif catching_up > 1:
                    # Skipped ahead while polling — brief stagger between lines
                    step_delay = policy.stagger_seconds()
                else:
                    # Live follow of real progress — tiny pause so the frame paints
                    step_delay = min(0.08, policy.stagger_seconds()) if not factory_plain else 0.0

                revealed += 1
                state = reduce_enable_state(
                    completed=last_completed,
                    current=current,
                    revealed_through=revealed,
                )
                frame = render_enable_frame(
                    state,
                    console_width=console.width,
                    ascii_safe=ascii_safe,
                )
                scene.update(frame)

                if step_delay > 0:
                    sleep_fn(step_delay)
                    if saw_ready_at is not None:
                        artificial_spent_ms += step_delay * 1000.0

            # Refresh current tip even when target unchanged (running spinner feel)
            if not ("ready" in last_completed and revealed >= target):
                state = reduce_enable_state(
                    completed=last_completed,
                    current=current,
                    revealed_through=max(revealed, 1),
                )
                scene.update(
                    render_enable_frame(
                        state,
                        console_width=console.width,
                        ascii_safe=ascii_safe,
                    )
                )

            if "ready" in last_completed:
                if revealed >= target:
                    ready = True
                    break
            sleep_fn(0.0 if factory_plain else poll_interval)

        if not ready:
            timed_out = True
    except Exception:
        timed_out = not ready

    # Never invent success: only keys in last_completed are DONE.
    final_state = reduce_enable_state(
        completed=last_completed,
        timed_out=timed_out,
        revealed_through=len(CANONICAL_STAGES) if (timed_out or ready) else max(revealed, 1),
    )

    try:
        scene.settle(
            render_enable_frame(
                final_state,
                console_width=console.width,
                ascii_safe=ascii_safe,
                settled=True,
            )
        )
    except Exception:
        try:
            console.print("[red]Startup finished with UI fallback.[/]")
        except Exception:
            pass

    return ready and not timed_out


def demo_enable_animation(*, slow: bool = True) -> bool:
    """Watch the enable morph without a real daemon (for manual testing).

    Run::
        python -c "from shellmate.ui.scenes.enable import demo_enable_animation; demo_enable_animation()"

    Or slow real enable::
        $env:SM_UI_SLOW=1; sm disable; sm enable
    """
    import os

    keys = [k for k, _ in CANONICAL_STAGES]
    state = {"i": 0, "t0": time.monotonic()}

    def poll():
        # Reveal one new stage every ~0.4s
        elapsed = time.monotonic() - state["t0"]
        n = min(len(keys), 1 + int(elapsed / 0.4))
        state["i"] = n
        completed = keys[:n]
        return completed, completed[-1]

    if slow:
        os.environ.setdefault("SM_UI_SLOW", "1")

    return run_enable_scene(
        poll=poll,
        timeout=20.0,
        poll_interval=0.05,
    )


if __name__ == "__main__":
    demo_enable_animation()
