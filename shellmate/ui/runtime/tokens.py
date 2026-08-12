"""Shared visual tokens — spacing, styles, icons with ASCII fallbacks."""

from __future__ import annotations

CONTENT_MAX_WIDTH = 96
NARROW_WIDTH = 80
MIN_WIDTH = 40

ACCENT = "cyan"
MUTED = "dim"
SUCCESS = "green"
WARNING = "yellow"
ERROR = "red"
TITLE = "bold"

# Unicode icons (interactive modern terminals)
ICONS_UNICODE = {
    "pending": "○",
    "running": "●",
    "done": "✓",
    "error": "✗",
    "skip": "−",
}

# ASCII-safe (Windows PS 5.1 / constrained / --no-color plain)
ICONS_ASCII = {
    "pending": "o",
    "running": "*",
    "done": "+",
    "error": "x",
    "skip": "-",
}


def icons(ascii_safe: bool = False) -> dict[str, str]:
    return ICONS_ASCII if ascii_safe else ICONS_UNICODE


def content_width(console_width: int) -> int:
    """Usable content width: track terminal, clamp to max, never invent fixed 110."""
    w = max(int(console_width or MIN_WIDTH), MIN_WIDTH)
    return min(w, CONTENT_MAX_WIDTH)


def show_logo(console_width: int) -> bool:
    """Bold logo only when there is room; narrow terminals get wordmark only."""
    return int(console_width or 0) >= NARROW_WIDTH
