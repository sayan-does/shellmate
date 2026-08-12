"""Synchronous IPC client for PowerShell adapter."""

from __future__ import annotations

import argparse
import asyncio
import json
import shlex
import sys
from pathlib import Path

# Ensure project root on path when invoked as a script
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from shellmate.ipc.client import ShellMateClient

# Common subcommand / flag completions for offline / fast path (no daemon required)
_SUBCOMMANDS = {
    "git": [
        "status", "push", "pull", "commit", "checkout", "branch", "log", "diff",
        "add", "merge", "rebase", "reset", "fetch", "clone", "stash", "remote",
    ],
    "docker": ["ps", "images", "run", "build", "exec", "stop", "rm", "compose", "logs"],
    "kubectl": ["get", "apply", "delete", "describe", "logs", "exec", "port-forward"],
    "npm": ["install", "run", "test", "build", "start", "ci"],
}

_FLAGS = {
    "git": ["--force", "--all", "--verbose", "--help", "--amend", "--no-verify"],
    "docker": ["--help", "--version", "--verbose", "--rm", "-it"],
    "kubectl": ["--namespace", "--context", "--kubeconfig", "--help"],
}


def _derive_completions(partial: str, program: str, result: dict) -> list:
    """Derive completions from analysis output for partial commands."""
    completions: list[str] = []
    risk = result.get("risk", "")
    if risk in ("HIGH", "CRITICAL"):
        rem = result.get("remediation") or {}
        if isinstance(rem, dict):
            alts = rem.get("alternatives") or []
            completions.extend([a for a in alts if isinstance(a, str)][:3])
    guide = result.get("command_guide") or {}
    if isinstance(guide, dict):
        completions.extend(
            [s for s in (guide.get("suggestions") or []) if isinstance(s, str)][:2]
        )
    elif isinstance(guide, list):
        completions.extend([s for s in guide if isinstance(s, str)][:5])
    return completions[:5]


def _local_completions(partial: str) -> list[str]:
    """Fast local completions for ghost-text / Tab (works without daemon)."""
    partial = (partial or "").strip()
    if not partial:
        return []

    try:
        tokens = shlex.split(partial)
    except ValueError:
        tokens = partial.split()

    if not tokens:
        return []

    program = tokens[0].lower()
    # Trailing space => user finished a token; suggest next word from empty prefix
    ends_with_space = partial.endswith(" ")

    if len(tokens) == 1 and not ends_with_space:
        # Completing the program name itself — leave to shell builtins
        return []

    # Flag completion
    current = "" if ends_with_space else tokens[-1]
    if current.startswith("-"):
        flags = _FLAGS.get(program, [])
        return [f for f in flags if f.startswith(current)][:5]

    # Subcommand completion (e.g. "git pu" -> "git push")
    if program in _SUBCOMMANDS:
        if len(tokens) == 1 and ends_with_space:
            prefix = ""
            base = program + " "
        elif len(tokens) == 2 and not ends_with_space:
            prefix = tokens[1]
            base = program + " "
        else:
            # Deeper args: try importing bash flag helper / return empty
            prefix = current
            base = " ".join(tokens[:-1]) + " " if tokens else ""
            try:
                from shellmate.completion.bash_adapter import get_flag_completions
                flags = get_flag_completions(program, prefix if prefix.startswith("-") else "-")
                if prefix.startswith("-"):
                    return flags[:5]
            except Exception:
                pass
            if len(tokens) >= 2 and not ends_with_space and tokens[1] in _SUBCOMMANDS.get(program, []):
                return []
            # Still allow subcommand match when second token is partial
            if len(tokens) == 2:
                matches = [s for s in _SUBCOMMANDS[program] if s.startswith(prefix)]
                return [f"{program} {m}" for m in matches][:5]
            return []

        matches = [s for s in _SUBCOMMANDS[program] if s.startswith(prefix)]
        return [f"{base}{m}".rstrip() if base.endswith(" ") else f"{program} {m}" for m in matches][:5]

    return []


class PSReadLineSyncClient:
    """Blocking wrapper around async Python client for PowerShell."""

    def send_command_partial_sync(self, command: str, timeout: float = 5.0) -> dict:
        """Blocking call to /analyze-partial endpoint."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            client = ShellMateClient()
            result = loop.run_until_complete(
                asyncio.wait_for(client.send_command_partial(command), timeout=timeout)
            )
            return result
        except Exception as e:
            return {"status": "error", "error": str(e)}
        finally:
            loop.close()

    def instant_check_sync(self, command: str) -> dict:
        """Local catastrophic match (no daemon required)."""
        from shellmate.rules.catastrophic_matcher import match_catastrophic
        return match_catastrophic(command)

    def complete_sync(self, command: str, timeout: float = 0.2) -> dict:
        """Return completion suggestions for ghost text / Tab.

        Prefers local completions (fast). Merges daemon-derived suggestions when available.
        """
        local = _local_completions(command)
        daemon_completions: list[str] = []
        try:
            result = self.send_command_partial_sync(command, timeout=timeout)
            guide = result.get("command_guide") or result.get("annotation", "")
            if isinstance(guide, list):
                daemon_completions = [g for g in guide if isinstance(g, str)][:5]
            elif result.get("status") == "ok" or result.get("annotation") or result.get("risk"):
                program = ""
                parsed = result.get("parsed") or {}
                if isinstance(parsed, dict):
                    program = parsed.get("program") or ""
                if not program:
                    try:
                        program = shlex.split(command)[0] if command.strip() else ""
                    except ValueError:
                        program = command.split()[0] if command.split() else ""
                daemon_completions = _derive_completions(command, program, result)
        except Exception:
            pass

        # Dedupe preserving order; local first for latency/stability
        seen = set()
        merged: list[str] = []
        for item in local + daemon_completions:
            if item and item not in seen:
                seen.add(item)
                merged.append(item)
        return {"completions": merged[:5]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ShellMate PowerShell IPC client")
    parser.add_argument("command", nargs="?", default="")
    parser.add_argument("--complete", action="store_true", help="Return completions instead of analysis")
    parser.add_argument("--instant", action="store_true", help="Local catastrophic check only")
    args = parser.parse_args()

    client = PSReadLineSyncClient()
    if args.instant:
        result = client.instant_check_sync(args.command)
    elif args.complete:
        result = client.complete_sync(args.command)
    else:
        result = client.send_command_partial_sync(args.command)
    print(json.dumps(result))
