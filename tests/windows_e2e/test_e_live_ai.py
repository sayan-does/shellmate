"""Series E - live AI tier (requires a real key).

Runs only when a provider key is present in the environment (see conftest
`live_keys`). Exercises the agentic /analyze-partial path and the full graph:
consequence preview, AI risk classification, remediation, and latency sanity.

Set keys before running, e.g.:
    $env:GROQ_API_KEY       = "<groq key>"
    $env:OPENROUTER_API_KEY = "<openrouter key>"   # optional, enables remediation
"""

from __future__ import annotations

import os
import time

import pytest

from tests.windows_e2e.conftest import LIVE_KEY_NAMES
from tests.windows_e2e.helpers.ipc import analyze_partial

pytestmark = [
    pytest.mark.windows,
    pytest.mark.requires_api,
    pytest.mark.slow,
    # Collection-time guard: skip before the session wheel build when no key is set.
    pytest.mark.skipif(
        not any(os.environ.get(k) for k in LIVE_KEY_NAMES),
        reason="No AI key set; export GROQ_API_KEY (or OPENROUTER/XAI) for the live tier",
    ),
]

# Genuinely risky but NOT in catastrophic.yaml -> these go through the AI pipeline
# (step 3 risk_analyzer), rather than short-circuiting to the instant tier.
RISKY = [
    "kubectl delete deployment api --namespace prod",
    "rm -rf ./build/cache",
    "git clean -fdx",
]


def test_consequence_preview_is_populated(live_daemon, live_env):
    live_daemon.enable()
    result = analyze_partial(live_daemon.installed, RISKY[0], env=live_env)
    cp = result.get("consequence_preview") or {}
    assert cp.get("what_happens"), result
    assert "scope" in cp, result
    assert "reversible" in cp, result
    assert cp.get("severity"), result
    # When a reachable model is configured (GROQ_MODEL), the AI must actually run
    # - not silently fall back. Guards against a 404 model masquerading as success.
    if os.environ.get("GROQ_MODEL"):
        assert "AI analysis unavailable" not in cp["what_happens"], (
            f"AI fell back instead of analyzing (check model access): {result}"
        )
        assert result.get("pipeline") == "full_agentic", result


@pytest.mark.parametrize("cmd", RISKY)
def test_risk_classification_present(live_daemon, live_env, cmd):
    live_daemon.enable()
    result = analyze_partial(live_daemon.installed, cmd, env=live_env)
    sev = result.get("severity") or (result.get("consequence_preview") or {}).get("severity")
    assert sev in ("SAFE", "LOW", "MEDIUM", "HIGH", "CRITICAL", "blocking"), result
    # Fresh isolated cache -> first lookup should not be a cache hit.
    assert result.get("pipeline") != "cache", result


def test_full_graph_analysis_returns_structure(live_daemon):
    """The raw-command path drives the full LangGraph pipeline end-to-end."""
    live_daemon.enable()
    result = live_daemon.analyze("git push --force origin main")
    assert isinstance(result, dict)
    assert result.get("status") == "ok", result
    assert any(k in result for k in ("risk", "consequence_preview", "remediation", "annotation")), result


@pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY required for remediation suggestions",
)
def test_remediation_suggestions_present(live_daemon):
    live_daemon.enable()
    result = live_daemon.analyze("git push --force origin main")
    rem = result.get("remediation")
    assert rem, f"no remediation in result: {result}"
    if isinstance(rem, dict):
        assert rem.get("alternatives") or rem.get("suggestion") or rem.get("explanation"), rem


def test_ai_latency_sanity(live_daemon, live_env):
    """Record pipeline latency; sanity ceiling only (provider-dependent)."""
    live_daemon.enable()
    start = time.perf_counter()
    analyze_partial(live_daemon.installed, "find / -name '*.log' -delete", env=live_env)
    elapsed_ms = (time.perf_counter() - start) * 1000
    # Generous ceiling - the configured ai_analysis_ms budget is 5s; subprocess
    # + cold model adds overhead. Flag only egregious hangs.
    assert elapsed_ms < 30_000, f"AI analyze took {elapsed_ms:.0f}ms (>30s)"
