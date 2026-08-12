"""Console construction with plain-mode detection and real terminal width."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from rich.console import Console


def is_plain_mode(
    *,
    no_color: bool = False,
    force_terminal: bool | None = None,
    environ: dict | None = None,
    stdout=None,
) -> bool:
    """True when animation/color should be disabled.

    Triggers: --no-color, NO_COLOR, CI, or non-TTY stdout.
    """
    env = environ if environ is not None else os.environ
    if no_color:
        return True
    if env.get("NO_COLOR", ""):
        return True
    if env.get("CI", ""):
        return True
    stream = stdout if stdout is not None else sys.stdout
    if force_terminal is False:
        return True
    if force_terminal is True:
        return False
    try:
        return not stream.isatty()
    except Exception:
        return True


@dataclass
class ConsoleFactory:
    no_color: bool = False
    force_terminal: bool | None = None
    width: int | None = None

    def is_plain(self) -> bool:
        return is_plain_mode(no_color=self.no_color, force_terminal=self.force_terminal)

    def create(self) -> Console:
        plain = self.is_plain()
        kwargs: dict = {
            "no_color": plain or self.no_color,
            "highlight": False,
        }
        if self.force_terminal is not None:
            kwargs["force_terminal"] = self.force_terminal
        console = Console(**kwargs)
        # Soft-wrap; never pin 110/120. Optional override via size when provided.
        if self.width is not None:
            try:
                console.width = self.width
            except Exception:
                pass
        return console
