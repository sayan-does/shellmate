"""Timing rules for sequential stage reveals (hybrid dwell + artificial cap)."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass


def motion_from_env(*, plain: bool = False) -> "MotionPolicy":
    """Build policy; SM_UI_SLOW=1 roughly doubles dwell for demo visibility."""
    slow = os.environ.get("SM_UI_SLOW", "").strip().lower() in ("1", "true", "yes")
    if slow:
        return MotionPolicy(
            min_dwell_ms=350,
            stagger_ms=120,
            max_artificial_ms_after_ready=2800,
            plain=plain,
        )
    return MotionPolicy(
        min_dwell_ms=180,
        stagger_ms=70,
        max_artificial_ms_after_ready=1600,
        plain=plain,
    )


@dataclass
class MotionPolicy:
    """Hybrid timing: short min dwell/stagger, hard cap on artificial wait after ready."""

    min_dwell_ms: int = 180
    stagger_ms: int = 70
    max_artificial_ms_after_ready: int = 1600
    plain: bool = False

    def dwell_seconds(self) -> float:
        if self.plain:
            return 0.0
        return max(0, self.min_dwell_ms) / 1000.0

    def stagger_seconds(self) -> float:
        if self.plain:
            return 0.0
        return max(0, self.stagger_ms) / 1000.0

    def sleep(self, seconds: float) -> None:
        if self.plain or seconds <= 0:
            return
        time.sleep(seconds)

    def clamp_artificial_budget(self, already_spent_ms: float) -> float:
        """Seconds still allowed for artificial waits after ready was observed."""
        if self.plain:
            return 0.0
        remaining = self.max_artificial_ms_after_ready - already_spent_ms
        return max(0.0, remaining) / 1000.0

    def play_reveal_delays(self, n_stages: int) -> list[float]:
        """Per-stage delays for ordered reveal when jumping ahead (e.g. already ready)."""
        if self.plain or n_stages <= 0:
            return [0.0] * max(0, n_stages)
        per = self.dwell_seconds() + self.stagger_seconds()
        raw_total = per * n_stages
        budget = self.max_artificial_ms_after_ready / 1000.0
        if raw_total <= budget or raw_total <= 0:
            return [per] * n_stages
        scaled = budget / n_stages
        return [scaled] * n_stages
