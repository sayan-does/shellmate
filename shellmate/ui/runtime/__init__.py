"""Shared Rich presentation runtime for ShellMate CLI scenes."""

from shellmate.ui.runtime.console_factory import ConsoleFactory, is_plain_mode
from shellmate.ui.runtime.live_scene import LiveScene
from shellmate.ui.runtime.motion_policy import MotionPolicy, motion_from_env
from shellmate.ui.runtime import tokens

__all__ = [
    "ConsoleFactory",
    "is_plain_mode",
    "LiveScene",
    "MotionPolicy",
    "motion_from_env",
    "tokens",
]
