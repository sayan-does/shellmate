"""Series D - pipeline tier, offline / rule-based (no AI keys).

With the daemon running but no API key configured, the Tier-2 /analyze-partial
path must degrade gracefully to deterministic output rather than crashing, and
the completion + daemon endpoints must answer. This is the Windows adapter's
"no key" baseline.
"""

from __future__ import annotations

import pytest

from tests.e2e.helpers.daemon_utils import query_daemon_status
from tests.windows_e2e.helpers.ipc import analyze_partial, complete, daemon_command

pytestmark = [pytest.mark.windows, pytest.mark.slow]


def test_analyze_partial_degrades_without_keys(installed_daemon):
    installed_daemon.enable()
    result = analyze_partial(installed_daemon.installed, "git status", env=installed_daemon.env)
    assert isinstance(result, dict)
    # Either a well-formed analysis payload or a clean error dict - never a crash.
    assert any(k in result for k in ("annotation", "severity", "risk", "status", "consequence_preview")), result


def test_catastrophic_still_flagged_offline(installed_daemon):
    """The instant tier inside /analyze-partial needs no key."""
    installed_daemon.enable()
    result = analyze_partial(installed_daemon.installed, "rm -rf /", env=installed_daemon.env)
    assert result.get("instant") is True or result.get("severity") in ("CRITICAL", "HIGH", "blocking"), result
    cp = result.get("consequence_preview") or {}
    assert cp.get("what_happens"), result


def test_completion_returns_git_push(installed_daemon):
    installed_daemon.enable()
    result = complete(installed_daemon.installed, "git pu", env=installed_daemon.env)
    comps = result.get("completions") or []
    assert any("push" in c for c in comps), result


def test_status_endpoint_answers(installed_daemon):
    installed_daemon.enable()
    data = query_daemon_status()
    assert data is not None
    assert data.get("startup_stage") == "ready"


def test_instant_check_endpoint_answers(installed_daemon):
    installed_daemon.enable()
    resp = daemon_command({"command": "/instant-check", "request_id": "win-e2e", "partial": "rm -rf /"})
    assert resp is not None and resp.get("status") == "ok", resp
    assert resp.get("matched") is True, resp
