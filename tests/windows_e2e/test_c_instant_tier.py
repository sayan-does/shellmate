"""Series C - instant tier (local catastrophic matcher, no daemon).

This is the Tier-1 Enter-key path in powershell_adapter.ps1: a synchronous,
API-free match that must stay well under the keystroke budget. Exercised through
the installed wheel's Python to prove packaging.
"""

from __future__ import annotations

import time

import pytest

from tests.windows_e2e.helpers.ipc import instant_check

pytestmark = pytest.mark.windows

# Commands the shipped rules/catastrophic.yaml actually flags (instant tier).
DANGEROUS = [
    "rm -rf /",
    "git push --force origin main",
    "dd if=/dev/zero of=/dev/sda",
    "chmod -R 777 /",
]
SAFE = ["Get-ChildItem", "git status", "ls -la"]


@pytest.mark.parametrize("cmd", DANGEROUS)
def test_dangerous_commands_match(installed_env, isolated_env, cmd):
    result = instant_check(installed_env, cmd, env=isolated_env)
    assert result.get("matched") is True, result


@pytest.mark.parametrize("cmd", SAFE)
def test_safe_commands_do_not_match(installed_env, isolated_env, cmd):
    result = instant_check(installed_env, cmd, env=isolated_env)
    assert result.get("matched") is False, result


def test_matched_payload_has_message_and_severity(installed_env, isolated_env):
    result = instant_check(installed_env, "rm -rf /", env=isolated_env)
    assert result.get("matched") is True
    assert result.get("message"), result
    assert result.get("severity"), result


@pytest.mark.slow
def test_instant_check_keystroke_budget_p99_under_10ms():
    """In-process timing of the local matcher (same code the adapter calls).

    Runs in the test interpreter (dev tree) because this is a pure-CPU budget
    check; packaging is proven separately above.
    """
    from shellmate.ipc.ps_client import PSReadLineSyncClient

    client = PSReadLineSyncClient()
    commands = ["rm -rf /", "git status", "format C:", "Get-ChildItem"]
    for _ in range(5):
        client.instant_check_sync("ls")  # warmup

    samples = []
    for i in range(100):
        start = time.perf_counter()
        client.instant_check_sync(commands[i % len(commands)])
        samples.append((time.perf_counter() - start) * 1000)

    samples.sort()
    p99 = samples[min(99, len(samples) - 1)]
    assert p99 < 10.0, f"instant keystroke P99 {p99:.2f}ms exceeds 10ms budget"
