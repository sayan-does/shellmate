"""Canonical startup stages and pure reducer for enable-scene UI state."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Optional


# Canonical display order (UI labels). Daemon keys must match.
# The daemon reports ready as soon as IPC is bound and catastrophic rules are
# loaded; agents and the provider check warm up in the background AFTER ready
# (surfaced via /status `agents`, not as startup stages), so they are not rows
# here. Keeping stale agent/provider rows made the enable screen show stages
# that never complete under a "Ready" banner.
CANONICAL_STAGES: list[tuple[str, str]] = [
    ("binding_ipc", "Binding IPC"),
    ("rules_loaded", "Safety rules loaded"),
    ("ready", "Ready"),
]

STAGE_KEYS = [k for k, _ in CANONICAL_STAGES]
STAGE_LABELS = {k: label for k, label in CANONICAL_STAGES}


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    INCOMPLETE = "incomplete"  # timeout — never paint false success


@dataclass
class StageView:
    key: str
    label: str
    status: StageStatus


@dataclass
class EnableViewState:
    stages: list[StageView] = field(default_factory=list)
    ready: bool = False
    timed_out: bool = False
    revealed_count: int = 0


def expand_from_current(current: Optional[str]) -> list[str]:
    """Legacy single-pointer protocol: current stage implies all prior milestones reached."""
    if not current or current not in STAGE_LABELS:
        return []
    idx = STAGE_KEYS.index(current)
    return list(STAGE_KEYS[: idx + 1])


def normalize_completed(completed: Iterable[str] | None, current: Optional[str] = None) -> list[str]:
    """Merge completed list + current into canonical-ordered unique keys.

    If ``completed`` is empty/None but ``current`` is set, expand legacy pointer.
    """
    raw_list = list(completed) if completed is not None else []
    if not raw_list and current:
        raw_list = expand_from_current(current)
    seen: set[str] = set()
    raw: list[str] = []
    for key in raw_list + ([current] if current else []):
        if key in STAGE_LABELS and key not in seen:
            seen.add(key)
            raw.append(key)
    raw.sort(key=lambda k: STAGE_KEYS.index(k))
    return raw


def next_reveal_target(completed: Iterable[str] | None, current: Optional[str] = None) -> int:
    """Exclusive index into CANONICAL_STAGES the UI should reveal up to."""
    ordered = normalize_completed(completed, current)
    if not ordered:
        return 0
    return STAGE_KEYS.index(ordered[-1]) + 1


def reduce_enable_state(
    *,
    completed: Iterable[str] | None = None,
    current: Optional[str] = None,
    timed_out: bool = False,
    revealed_through: Optional[int] = None,
) -> EnableViewState:
    """Pure reducer: daemon facts → UI stage list. Never invents success.

    ``revealed_through`` caps how many canonical rows are visible (ordered animation).
    If None, reveal through the latest known completed/current stage (or all on timeout).
    """
    completed_ordered = normalize_completed(completed, current)
    completed_set = set(completed_ordered)
    ready = "ready" in completed_set and not timed_out

    if revealed_through is None:
        if timed_out:
            reveal_idx = len(CANONICAL_STAGES)
        else:
            reveal_idx = next_reveal_target(completed, current)
            if reveal_idx == 0 and current:
                reveal_idx = 1
    else:
        reveal_idx = max(0, min(int(revealed_through), len(CANONICAL_STAGES)))

    stages: list[StageView] = []
    for i, (key, label) in enumerate(CANONICAL_STAGES):
        if i >= reveal_idx:
            break

        if key in completed_set:
            status = StageStatus.DONE
        elif timed_out:
            status = StageStatus.INCOMPLETE
        elif i == reveal_idx - 1:
            status = StageStatus.RUNNING
        else:
            status = StageStatus.PENDING

        stages.append(StageView(key=key, label=label, status=status))

    return EnableViewState(
        stages=stages,
        ready=ready,
        timed_out=timed_out,
        revealed_count=reveal_idx,
    )
