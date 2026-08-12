"""Completion source adapters for autocomplete mode (Phase 4).

Works offline / without bash (Windows) via static subcommand maps,
then bash compgen, then carapace.
"""

from __future__ import annotations

import shlex
import subprocess
from typing import List

# Shared with ipc/ps_client offline path — keep in sync for ghost-text / Tab.
_SUBCOMMANDS = {
    "git": [
        "status", "push", "pull", "commit", "checkout", "branch", "log", "diff",
        "add", "merge", "rebase", "reset", "fetch", "clone", "stash", "remote",
    ],
    "docker": ["ps", "images", "run", "build", "exec", "stop", "rm", "compose", "logs"],
    "kubectl": ["get", "apply", "delete", "describe", "logs", "exec", "port-forward"],
    "npm": ["install", "run", "test", "build", "start", "ci"],
}

_FLAG_MAP = {
    "git": ["--force", "--all", "--verbose", "--help", "--amend", "--no-verify"],
    "docker": ["--help", "--version", "--verbose", "--rm", "-it"],
    "kubectl": ["--namespace", "--context", "--kubeconfig", "--help"],
}


def get_completions(partial_command: str) -> List[str]:
    """
    Get completions for a partial command.

    Order: static map (always available) → bash compgen → carapace.
    Returns full-line suggestions when completing a subcommand (e.g. "git push")
    so ble.sh ghost text can strip the typed prefix.
    """
    candidates = get_completions_static(partial_command)
    if candidates:
        return candidates

    candidates = get_completions_bash(partial_command)
    if candidates:
        return candidates

    return get_completions_carapace(partial_command)


def get_completions_static(partial_command: str) -> List[str]:
    """Offline completions from known program maps (Windows-safe)."""
    partial = (partial_command or "").strip()
    if not partial:
        return []

    try:
        tokens = shlex.split(partial_command)
    except ValueError:
        tokens = partial_command.split()

    if not tokens:
        return []

    program = tokens[0]
    ends_with_space = partial_command.endswith(" ")
    current = "" if ends_with_space else tokens[-1]

    # Flag completion
    if current.startswith("-"):
        flags = get_flag_completions(program, current)
        return flags[:10]

    # Program name completion (single token)
    if len(tokens) == 1 and not ends_with_space:
        return [p for p in _SUBCOMMANDS if p.startswith(program)][:10]

    # Subcommand completion: "git pu" → ["git push", "git pull"]
    if program in _SUBCOMMANDS:
        if len(tokens) == 1 and ends_with_space:
            prefix = ""
        elif len(tokens) == 2 and not ends_with_space:
            prefix = tokens[1]
        else:
            return []

        matches = [s for s in _SUBCOMMANDS[program] if s.startswith(prefix)]
        # Full-line form for adapters; also expose bare subcommands for callers
        # that expect pivot-style ["push", "pull"].
        full = [f"{program} {m}" for m in matches]
        return (full or matches)[:10]

    return []


def get_completions_bash(partial_command: str) -> List[str]:
    """Get bash completions using compgen (Linux/WSL/Git Bash)."""
    try:
        tokens = shlex.split(partial_command)
        if not tokens:
            return []

        program = tokens[0]
        current = tokens[-1] if len(tokens) > 1 else program

        # Escape for safe shell interpolation
        safe_current = current.replace("'", "'\\''")
        result = subprocess.run(
            ["bash", "-c", f"compgen -c -- '{safe_current}'"],
            capture_output=True,
            text=True,
            timeout=0.1,
        )

        if result.returncode == 0 and result.stdout.strip():
            candidates = [c for c in result.stdout.strip().split("\n") if c]
            # Prefer candidates that extend the typed token
            filtered = [c for c in candidates if c.startswith(current)][:10]
            return filtered

        return []
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        return []


def get_flag_completions(program: str, partial_flag: str) -> List[str]:
    """Get flag completions for known programs."""
    flags = _FLAG_MAP.get(program, [])
    return [f for f in flags if f.startswith(partial_flag)]


def get_completions_carapace(partial_command: str) -> List[str]:
    """Fallback to carapace if bash-completion unavailable."""
    try:
        result = subprocess.run(
            ["carapace", "_carapace", "bash", partial_command],
            capture_output=True,
            text=True,
            timeout=0.2,
        )

        if result.returncode == 0 and result.stdout.strip():
            return [c for c in result.stdout.strip().split("\n") if c][:10]
        return []
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        return []
