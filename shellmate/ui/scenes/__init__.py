"""CLI scene composers."""

from shellmate.ui.scenes.enable import render_enable_frame, run_enable_scene
from shellmate.ui.scenes.help import print_help, render_help
from shellmate.ui.scenes.status import render_status, build_status_renderable
from shellmate.ui.scenes.stages import (
    CANONICAL_STAGES,
    reduce_enable_state,
    normalize_completed,
    next_reveal_target,
)

__all__ = [
    "render_enable_frame",
    "run_enable_scene",
    "print_help",
    "render_help",
    "render_status",
    "build_status_renderable",
    "CANONICAL_STAGES",
    "reduce_enable_state",
    "normalize_completed",
    "next_reveal_target",
]
