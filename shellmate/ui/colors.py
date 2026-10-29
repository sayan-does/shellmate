"""Semantic terminal colors for suggestions and cautions.

Single source of truth for ShellMate's inline color scheme so every surface
agrees on what red / yellow / green mean:

    caution     -> red     (dangerous: HIGH / CRITICAL / blocking)
    warning     -> yellow  (proceed with care: MEDIUM)
    suggestion  -> green    (a safer alternative / "Safe alt")
    safe        -> green    (SAFE / LOW — nothing to worry about)
    info        -> cyan     (neutral information)
    dim         -> grey     (de-emphasized)

The shell adapters (``powershell_adapter.ps1`` / ``ble_adapter.sh``) mirror these
SGR codes directly since they render ANSI themselves; keep them in sync with
``ROLE_SGR`` below. Python-side rendering should use this module.

Honors the https://no-color.org convention: if the ``NO_COLOR`` environment
variable is set (to anything), colorizing becomes a no-op.
"""

from __future__ import annotations

import os
from typing import Optional

ESC = "\033"
RESET = f"{ESC}[0m"

# Role -> SGR (Select Graphic Rendition) code. Bright variants read well on both
# dark and light terminals. Mirror these in the shell adapters.
ROLE_SGR = {
    "caution": 91,     # bright red
    "warning": 93,     # bright yellow
    "suggestion": 92,  # bright green
    "safe": 92,        # bright green
    "info": 96,        # bright cyan
    "dim": 90,         # grey
}

# Role -> rich style name, for Console/Text rendering in the CLI scenes.
ROLE_RICH = {
    "caution": "bold red",
    "warning": "yellow",
    "suggestion": "green",
    "safe": "green",
    "info": "cyan",
    "dim": "bright_black",
}

# Risk/severity label -> semantic role.
SEVERITY_ROLE = {
    "CRITICAL": "caution",
    "HIGH": "caution",
    "blocking": "caution",
    "MEDIUM": "warning",
    "warning": "warning",
    "LOW": "safe",
    "SAFE": "safe",
    "info": "info",
}


def color_enabled(no_color: Optional[bool] = None) -> bool:
    """Whether color should be emitted.

    Explicit ``no_color`` wins; otherwise honor the ``NO_COLOR`` env var.
    """
    if no_color is not None:
        return not no_color
    return os.environ.get("NO_COLOR") is None


def role_for_severity(severity: Optional[str]) -> str:
    """Map a risk/severity label to a semantic role (defaults to ``warning``)."""
    return SEVERITY_ROLE.get(severity or "", "warning")


def colorize(text: str, role: str, *, no_color: Optional[bool] = None) -> str:
    """Wrap ``text`` in the ANSI color for ``role``.

    Returns ``text`` unchanged when color is disabled, the text is empty, or the
    role is unknown — so it is always safe to call.
    """
    if not text or not color_enabled(no_color):
        return text
    sgr = ROLE_SGR.get(role)
    if sgr is None:
        return text
    return f"{ESC}[{sgr}m{text}{RESET}"


def caution(text: str, *, no_color: Optional[bool] = None) -> str:
    """Red — a dangerous command or consequence."""
    return colorize(text, "caution", no_color=no_color)


def warning(text: str, *, no_color: Optional[bool] = None) -> str:
    """Yellow — proceed with care."""
    return colorize(text, "warning", no_color=no_color)


def suggestion(text: str, *, no_color: Optional[bool] = None) -> str:
    """Green — a safer alternative to offer."""
    return colorize(text, "suggestion", no_color=no_color)


def by_severity(text: str, severity: Optional[str], *, no_color: Optional[bool] = None) -> str:
    """Colorize ``text`` using the role implied by a risk/severity label."""
    return colorize(text, role_for_severity(severity), no_color=no_color)
