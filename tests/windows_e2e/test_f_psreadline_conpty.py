"""Series F - PSReadLine UX, fully automated via ConPTY (best-effort).

Spawns the *installed* adapter in a real pwsh pseudo-console and asserts on the
rendered screen. Opt-in (`@conpty`) because pseudo-console timing is flaky; the
Pester + predictor floor (Series G) is the deterministic baseline.

Skips automatically unless pwsh 7.2+, pywinpty, and pyte are all available.
"""

from __future__ import annotations

import pytest

from tests.windows_e2e.conftest import conpty_available, pwsh_path
from tests.windows_e2e.helpers import conpty_harness

pytestmark = [
    pytest.mark.windows,
    pytest.mark.pwsh,
    pytest.mark.conpty,
    pytest.mark.slow,
    # Collection-time guard: skip before the session wheel build when ConPTY toolchain absent.
    pytest.mark.skipif(
        not conpty_available(),
        reason="ConPTY toolchain unavailable (needs pwsh 7.2+ + pywinpty + pyte)",
    ),
]

# pwsh_env and adapter_path fixtures live in conftest.py (shared with Series G).


@pytest.fixture
def console(adapter_path, pwsh_env):
    con = conpty_harness.PwshConsole(adapter_path, env=pwsh_env, pwsh=pwsh_path())
    try:
        yield con
    finally:
        con.close()


def test_dangerous_command_shows_blocking_banner(console):
    """Typing a catastrophic command + Enter renders the BLOCKING annotation."""
    assert console.type_enter_expect("git push --force origin main", "BLOCKING", timeout=8.0), console.screen_text()


def test_first_enter_is_suppressed_for_dangerous(console):
    """Double-tap gate: first Enter must not submit the command."""
    got = console.type_enter_expect("git push --force origin main", "BLOCKING", timeout=8.0)
    assert got, console.screen_text()
    # The typed buffer is still visible on the prompt line (not accepted/cleared).
    assert "git push --force" in console.screen_text(), console.screen_text()


def test_safe_command_has_no_blocking_banner(console):
    console.type("Get-ChildItem")
    console.send_enter()
    # Give the adapter a moment; a safe command must not raise a block banner.
    console.wait_for("PS", timeout=3.0)
    assert "BLOCKING" not in console.screen_text(), console.screen_text()


def test_no_terminal_corruption_after_several_commands(console):
    for cmd in ("Get-ChildItem", "git status", "echo hi"):
        console.type(cmd)
        console.send_enter()
        console.wait_for("PS", timeout=4.0)
    # pyte resolves all cursor save/restore; no raw escape bytes should remain.
    assert not console.has_stray_escape(), console.screen_text()
