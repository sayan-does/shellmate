import sys
import os
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(autouse=True)
def _isolate_credentials():
    """Prevent on-disk credentials from leaking into tests (REL-06).

    Provider tests pop env vars to verify fallback behaviour, but
    ``providers/router.py:_inject_env()`` calls ``load_env()`` which reads
    the user's real ``.env`` file.  This fixture:
      1. patches ``load_env`` to return an empty dict, and
      2. resets the cached provider singletons so stale instances with
         real keys are discarded between tests.
    """
    import providers.router as router_mod
    router_mod._groq_provider = None
    router_mod._openrouter_provider = None
    # router.py does ``from config.credentials import load_env`` at module
    # level, so we must patch the local reference.
    with patch("providers.router.load_env", return_value={}):
        yield


# ---------------------------------------------------------------------------
# Enrichment test fixtures (Phase 6 — shared across AGR-18..32)
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_supervisor_route(mocker):
    """Patches ``orchestration.analysis_graph.route_command``.

    Yields a factory ``(run_watcher, run_librarian) -> None`` that
    configures the mock.  Call it in your test to set the desired
    flags.
    """
    import orchestration.analysis_graph as ag
    m = mocker.patch.object(ag, "route_command", new_callable=AsyncMock)

    def _set(run_watcher=True, run_librarian=False):
        m.return_value = {"run_watcher": run_watcher, "run_librarian": run_librarian}
    yield _set


@pytest.fixture
def mock_command_guide(mocker):
    """Patches ``orchestration.analysis_graph.generate_command_guide``.

    Yields a factory that sets the return value to a standard guide dict
    or to a caller-provided dict.
    """
    import orchestration.analysis_graph as ag
    m = mocker.patch.object(ag, "generate_command_guide", new_callable=AsyncMock)

    DEFAULT_GUIDE = {
        "when_to_use": "Apply a specific commit on the current branch.",
        "parameters": ["<commit>: SHA to cherry-pick"],
        "example_command": "git cherry-pick abc1234",
    }

    def _set(guide=None):
        m.return_value = guide or DEFAULT_GUIDE
    yield _set


def minimal_analysis_state(**overrides) -> dict:
    """Build a minimal ``AnalysisState`` with all required keys.

    Example::

        state = minimal_analysis_state(command="git status")

    The returned dict is a plain ``dict`` that satisfies the
    ``AnalysisState`` TypedDict shape.
    """
    state = {
        "command": "echo hello",
        "sanitized": None,
        "parsed": None,
        "rule_match": None,
        "cached": None,
        "needs_context": False,
        "watcher_context": None,
        "librarian_context": None,
        "merged_context": None,
        "risk_analysis": None,
        "remediation": None,
        "output": None,
        "errors": [],
        "stages": {},
        "agent_latency": {"watcher": 0, "librarian": 0},
        "early_exit": None,
        "supervisor_decision": None,
        "supervisor_fallback": False,
        "supervisor_warning": None,
        "command_guide": None,
    }
    state.update(overrides)
    return state


@pytest.fixture
def sample_watcher_context():
    """Standard watcher context dict for enrichment prompt tests."""
    return {
        "os": {"system": "Windows"},
        "shell": "powershell",
        "current_directory": "D:\\projects\\shellmate",
        "git": {"branch": "main", "staged": 0, "unstaged": 1},
    }
