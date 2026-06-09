import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from orchestration.state import AnalysisState
from orchestration.analysis_graph import (
    AnalysisGraph,
    sanitize_node,
    parse_node,
    rules_node,
    cache_node,
    early_exit_router,
    supervisor_node,
    supervisor_router,
    format_node,
    command_guide_node,
    _needs_context,
)
from unittest.mock import AsyncMock, patch

from tests.conftest import minimal_analysis_state


class TestAnalysisState:
    def test_state_structure(self):
        state: AnalysisState = {
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
        assert state["command"] == "echo hello"
        assert state["errors"] == []
        assert state["supervisor_fallback"] is False
        assert state["supervisor_decision"] is None
        assert state["supervisor_warning"] is None
        assert state["command_guide"] is None


class TestGraphNodes:
    def test_sanitize_node(self):
        state: AnalysisState = {
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
        result = sanitize_node(state)
        assert "sanitized" in result
        assert result["sanitized"] is not None
        assert "syntax" in result["sanitized"]

    def test_parse_node(self):
        state: AnalysisState = {
            "command": "echo hello",
            "sanitized": {"normalized": "echo hello", "syntax": {"valid": True}},
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
            "stages": {"sanitizer": 1.0},
            "agent_latency": {"watcher": 0, "librarian": 0},
            "early_exit": None,
            "supervisor_decision": None,
            "supervisor_fallback": False,
            "supervisor_warning": None,
            "command_guide": None,
        }
        result = parse_node(state)
        assert "parsed" in result
        assert "stages" in result
        assert "parser" in result["stages"]

    def test_rules_node(self):
        state: AnalysisState = {
            "command": "echo hello",
            "sanitized": {"normalized": "echo hello", "syntax": {"valid": True}},
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
            "stages": {"sanitizer": 1.0},
            "agent_latency": {"watcher": 0, "librarian": 0},
            "early_exit": None,
            "supervisor_decision": None,
            "supervisor_fallback": False,
            "supervisor_warning": None,
            "command_guide": None,
        }
        result = rules_node(state)
        assert "rule_match" in result
        assert "stages" in result

    def test_cache_node(self):
        state: AnalysisState = {
            "command": "echo hello",
            "sanitized": {"normalized": "echo hello", "syntax": {"valid": True}},
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
            "stages": {"sanitizer": 1.0},
            "agent_latency": {"watcher": 0, "librarian": 0},
            "early_exit": None,
            "supervisor_decision": None,
            "supervisor_fallback": False,
            "supervisor_warning": None,
            "command_guide": None,
        }
        result = cache_node(state)
        assert "cached" in result
        assert "stages" in result

    def test_early_exit_router_sanitizer_correction(self):
        state: AnalysisState = {
            "command": "echo hello",
            "sanitized": {"correction": "echo hello", "syntax": {"valid": True}},
            "rule_match": None,
            "cached": None,
        }
        assert early_exit_router(state) == "early_exit_sanitizer"

    def test_early_exit_router_syntax_error(self):
        state: AnalysisState = {
            "command": "echo 'hello",
            "sanitized": {"syntax": {"valid": False, "errors": ["unclosed quote"]}},
            "rule_match": None,
            "cached": None,
        }
        assert early_exit_router(state) == "early_exit_sanitizer"

    def test_early_exit_router_rule_match(self):
        state: AnalysisState = {
            "command": "rm -rf /",
            "sanitized": {"normalized": "rm -rf /", "syntax": {"valid": True}},
            "rule_match": {"matched": True, "confidence": 0.95},
            "cached": None,
        }
        assert early_exit_router(state) == "early_exit_rule"

    def test_early_exit_router_cache(self):
        state: AnalysisState = {
            "command": "echo hello",
            "sanitized": {"normalized": "echo hello", "syntax": {"valid": True}},
            "rule_match": None,
            "cached": {"risk": "LOW"},
        }
        assert early_exit_router(state) == "early_exit_cache"

    def test_early_exit_router_needs_context(self):
        state: AnalysisState = {
            "command": "echo hello",
            "sanitized": {"normalized": "echo hello", "syntax": {"valid": True}},
            "rule_match": {"matched": False},
            "cached": None,
        }
        assert early_exit_router(state) == "needs_context"

    @pytest.mark.asyncio
    async def test_supervisor_node_no_key_heuristic(self):
        state: AnalysisState = {
            "command": "rm file.txt",
            **{k: None for k in ["sanitized", "parsed", "rule_match", "cached",
                                 "watcher_context", "librarian_context", "merged_context",
                                 "risk_analysis", "remediation", "output"]},
            "errors": [],
            "stages": {},
            "agent_latency": {"watcher": 0, "librarian": 0},
            "early_exit": None,
            "needs_context": False,
            "supervisor_decision": None,
            "supervisor_fallback": False,
            "supervisor_warning": None,
            "command_guide": None,
        }
        result = await supervisor_node(state)
        assert result["needs_context"] is True
        assert result["supervisor_decision"]["run_watcher"] is True
        assert result["supervisor_decision"]["run_librarian"] is True

    @pytest.mark.asyncio
    async def test_supervisor_node_with_groq_key(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test")
        state: AnalysisState = {
            "command": "git status",
            **{k: None for k in ["sanitized", "parsed", "rule_match", "cached",
                                 "watcher_context", "librarian_context", "merged_context",
                                 "risk_analysis", "remediation", "output"]},
            "errors": [],
            "stages": {},
            "agent_latency": {"watcher": 0, "librarian": 0},
            "early_exit": None,
            "needs_context": False,
            "supervisor_decision": None,
            "supervisor_fallback": False,
            "supervisor_warning": None,
            "command_guide": None,
        }
        with patch("orchestration.analysis_graph.route_command", new_callable=AsyncMock) as mock_route:
            mock_route.return_value = {"run_watcher": True, "run_librarian": False}
            result = await supervisor_node(state)
            assert result["supervisor_decision"]["run_watcher"] is True
            assert result["supervisor_decision"]["run_librarian"] is False
            assert result["needs_context"] is True

    @pytest.mark.asyncio
    async def test_supervisor_node_groq_neither(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test")
        state: AnalysisState = {
            "command": "echo hi",
            **{k: None for k in ["sanitized", "parsed", "rule_match", "cached",
                                 "watcher_context", "librarian_context", "merged_context",
                                 "risk_analysis", "remediation", "output"]},
            "errors": [],
            "stages": {},
            "agent_latency": {"watcher": 0, "librarian": 0},
            "early_exit": None,
            "needs_context": False,
            "supervisor_decision": None,
            "supervisor_fallback": False,
            "supervisor_warning": None,
            "command_guide": None,
        }
        with patch("orchestration.analysis_graph.route_command", new_callable=AsyncMock) as mock_route:
            mock_route.return_value = {"run_watcher": False, "run_librarian": False}
            result = await supervisor_node(state)
            assert result["needs_context"] is False
            assert result["supervisor_decision"]["run_watcher"] is False
            assert result["supervisor_decision"]["run_librarian"] is False

    @pytest.mark.asyncio
    async def test_supervisor_node_fallback_on_error(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test")
        state: AnalysisState = {
            "command": "docker ps",
            **{k: None for k in ["sanitized", "parsed", "rule_match", "cached",
                                 "watcher_context", "librarian_context", "merged_context",
                                 "risk_analysis", "remediation", "output"]},
            "errors": [],
            "stages": {},
            "agent_latency": {"watcher": 0, "librarian": 0},
            "early_exit": None,
            "needs_context": False,
            "supervisor_decision": None,
            "supervisor_fallback": False,
            "supervisor_warning": None,
            "command_guide": None,
        }
        with patch("orchestration.analysis_graph.route_command", new_callable=AsyncMock) as mock_route:
            from providers.groq_supervisor import SupervisorError
            mock_route.side_effect = SupervisorError("timeout")
            result = await supervisor_node(state)
            assert result["supervisor_fallback"] is True
            assert result["needs_context"] is False
            assert "supervisor unavailable" in result["supervisor_warning"]

    @pytest.mark.asyncio
    async def test_supervisor_node_records_stage(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test")
        state: AnalysisState = {
            "command": "git status",
            **{k: None for k in ["sanitized", "parsed", "rule_match", "cached",
                                 "watcher_context", "librarian_context", "merged_context",
                                 "risk_analysis", "remediation", "output"]},
            "errors": [],
            "stages": {},
            "agent_latency": {"watcher": 0, "librarian": 0},
            "early_exit": None,
            "needs_context": False,
            "supervisor_decision": None,
            "supervisor_fallback": False,
            "supervisor_warning": None,
            "command_guide": None,
        }
        with patch("orchestration.analysis_graph.route_command", new_callable=AsyncMock) as mock_route:
            mock_route.return_value = {"run_watcher": True, "run_librarian": False}
            result = await supervisor_node(state)
            assert "supervisor" in result.get("stages", {})

    def test_supervisor_router_context(self):
        state = {"needs_context": True}
        assert supervisor_router(state) == "context_worker"

    def test_supervisor_router_skip(self):
        state = {"needs_context": False}
        assert supervisor_router(state) == "skip_context"

    def test_supervisor_router_fallback(self):
        state = {"supervisor_fallback": True, "needs_context": True}
        assert supervisor_router(state) == "skip_context"

    def test_supervisor_router_fallback_no_context(self):
        state = {"supervisor_fallback": True, "needs_context": False}
        assert supervisor_router(state) == "skip_context"


class TestAnalysisWorkflow:
    """AGR-20: Full graph ainvoke tests for every major branch."""

    @pytest.mark.asyncio
    async def test_workflow_early_exit_cache(self):
        graph = AnalysisGraph()
        with patch("orchestration.analysis_graph.cache_lookup") as mock_cache:
            mock_cache.return_value = {"risk": "LOW", "confidence": 0.9}
            result = await graph.ainvoke("echo hello")
        assert result.get("early_exit") == "cache"
        assert result.get("command_guide") is None

    @pytest.mark.asyncio
    async def test_workflow_early_exit_rule(self):
        graph = AnalysisGraph()
        result = await graph.ainvoke("rm -rf /")
        assert result.get("early_exit") == "rule_engine"
        assert result.get("command_guide") is None

    @pytest.mark.asyncio
    async def test_workflow_supervisor_fallback(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test")
        graph = AnalysisGraph()
        with (
            patch("orchestration.analysis_graph.route_command", new_callable=AsyncMock) as mock_route,
            patch("orchestration.analysis_graph.analyze_risk", new_callable=AsyncMock) as mock_risk,
            patch("orchestration.analysis_graph.generate_remediation", new_callable=AsyncMock) as mock_rem,
        ):
            from providers.groq_supervisor import SupervisorError
            mock_route.side_effect = SupervisorError("timeout")
            mock_risk.return_value = {"risk": "SAFE", "confidence": 0.9, "provider": "fallback"}
            mock_rem.return_value = {"explanation": "safe", "alternatives": []}
            result = await graph.ainvoke("git status")
        assert result.get("supervisor_warning") is not None
        assert "supervisor unavailable" in result["supervisor_warning"]
        assert result.get("risk") is not None

    @pytest.mark.asyncio
    async def test_workflow_full_path_keyed(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test")
        graph = AnalysisGraph()
        with (
            patch("orchestration.analysis_graph.route_command", new_callable=AsyncMock) as mock_route,
            patch("orchestration.analysis_graph.analyze_risk", new_callable=AsyncMock) as mock_risk,
            patch("orchestration.analysis_graph.generate_remediation", new_callable=AsyncMock) as mock_rem,
            patch("orchestration.analysis_graph.generate_command_guide", new_callable=AsyncMock) as mock_guide,
        ):
            mock_route.return_value = {"run_watcher": True, "run_librarian": True}
            mock_risk.return_value = {"risk": "LOW", "confidence": 0.7, "provider": "groq"}
            mock_rem.return_value = {"explanation": "safe", "alternatives": ["use echo"]}
            mock_guide.return_value = {
                "when_to_use": "Check repository status.",
                "parameters": ["-s: short"],
                "example_command": "git status -s",
            }
            result = await graph.ainvoke("git status")
        assert result.get("command_guide") is not None
        assert result["command_guide"]["when_to_use"] == "Check repository status."
        assert result.get("risk") is not None

    @pytest.mark.asyncio
    async def test_workflow_skip_context_both_false(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test")
        graph = AnalysisGraph()
        with (
            patch("orchestration.analysis_graph.route_command", new_callable=AsyncMock) as mock_route,
            patch("orchestration.analysis_graph.analyze_risk", new_callable=AsyncMock) as mock_risk,
            patch("orchestration.analysis_graph.generate_remediation", new_callable=AsyncMock) as mock_rem,
            patch("orchestration.analysis_graph.generate_command_guide", new_callable=AsyncMock) as mock_guide,
        ):
            mock_route.return_value = {"run_watcher": False, "run_librarian": False}
            mock_risk.return_value = {"risk": "LOW", "confidence": 0.8, "provider": "groq"}
            mock_rem.return_value = {"explanation": "safe", "alternatives": []}
            mock_guide.return_value = {"when_to_use": "test", "parameters": [], "example_command": "echo hi"}
            result = await graph.ainvoke("echo xyz_unique_test_skip_context")
        assert result.get("command_guide") is not None
        assert "context_used" in result

    @pytest.mark.asyncio
    async def test_workflow_watcher_only_context(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test")
        graph = AnalysisGraph()
        from orchestration.analysis_graph import _query_watcher, _query_librarian, _query_repomix
        with (
            patch("orchestration.analysis_graph.route_command", new_callable=AsyncMock) as mock_route,
            patch("orchestration.analysis_graph.analyze_risk", new_callable=AsyncMock) as mock_risk,
            patch("orchestration.analysis_graph.generate_remediation", new_callable=AsyncMock) as mock_rem,
            patch.object(graph, "_compiled") as mock_compiled,
        ):
            mock_route.return_value = {"run_watcher": True, "run_librarian": False}
            mock_risk.return_value = {"risk": "LOW", "confidence": 0.7, "provider": "groq"}
            mock_rem.return_value = {"explanation": "safe", "alternatives": []}
            result = await graph.ainvoke("git status")
        assert result.get("risk") is not None


class TestGraphMemoryAndState:
    """AGR-21: LangGraph MemorySaver compiles; state fields survive node chain."""

    def test_graph_compiles_with_checkpointer(self):
        graph = AnalysisGraph()
        compiled = graph.build()
        assert compiled is not None

    def test_initial_state_has_all_keys(self):
        graph = AnalysisGraph()
        graph.build()
        expected_keys = {
            "command", "sanitized", "parsed", "rule_match", "cached",
            "needs_context", "watcher_context", "librarian_context", "merged_context",
            "risk_analysis", "remediation", "output", "errors", "stages",
            "agent_latency", "early_exit",
            "supervisor_decision", "supervisor_fallback", "supervisor_warning", "command_guide",
        }
        initial = {
            "command": "test",
            "sanitized": None, "parsed": None, "rule_match": None, "cached": None,
            "needs_context": False,
            "watcher_context": None, "librarian_context": None, "merged_context": None,
            "risk_analysis": None, "remediation": None, "output": None,
            "errors": [], "stages": {}, "agent_latency": {"watcher": 0, "librarian": 0},
            "early_exit": None,
            "supervisor_decision": None, "supervisor_fallback": False,
            "supervisor_warning": None, "command_guide": None,
        }
        assert set(initial.keys()) == expected_keys

    def test_state_supervisor_fields_preserved(self):
        result = supervisor_router({"supervisor_fallback": True, "needs_context": True})
        assert result == "skip_context"
        result = supervisor_router({"needs_context": True})
        assert result == "context_worker"

    def test_format_node_replaces_generic_alternatives_with_guide(self):
        from orchestration.analysis_graph import format_node
        state = {
            "command": "python -m pytest test how",
            "sanitized": {"normalized": "python -m pytest test how", "syntax": {"valid": True}},
            "rule_match": None,
            "cached": None,
            "risk_analysis": {"risk": "LOW", "confidence": 0.8, "reason": "running tests"},
            "remediation": {
                "explanation": "safe",
                "alternatives": ["Review the command carefully before executing."],
            },
            "merged_context": None,
            "stages": {},
            "command_guide": {
                "intent_guess": "Maybe you're trying to run pytest on a test module",
                "parameters": ["test: test path"],
                "suggested_command": "python -m pytest tests/",
            },
        }
        result = format_node(state)
        alts = result["output"]["alternatives"]
        assert any("Maybe you're trying" in a for a in alts)
        assert any("Try: python -m pytest" in a for a in alts)

    def test_state_command_guide_in_format_output(self):
        state = minimal_analysis_state(
            command="git status",
            sanitized={"normalized": "git status", "syntax": {"valid": True}},
            risk_analysis={"risk": "SAFE", "confidence": 0.9, "provider": "fallback"},
            remediation={"explanation": "safe", "alternatives": []},
            stages={"sanitizer": 1.0},
            command_guide={"when_to_use": "test", "parameters": [], "example_command": "git status"},
        )
        result = format_node(state)
        output = result.get("output", {})
        assert output.get("command_guide") is not None
        assert output["command_guide"]["when_to_use"] == "test"


class TestAnalysisGraph:
    def test_analyze_safe_command(self):
        import asyncio
        graph = AnalysisGraph()
        result = asyncio.run(graph.analyze_command("echo hello"))
        assert "risk" in result
        assert "message" in result
        assert "confidence" in result
        assert result["risk"] in ("SAFE", "LOW", "MEDIUM", "HIGH", "CRITICAL")

    def test_analyze_rm_rf(self):
        import asyncio
        graph = AnalysisGraph()
        result = asyncio.run(graph.analyze_command("rm -rf /"))
        assert "risk" in result
        assert "message" in result

    def test_gather_context(self):
        import asyncio
        graph = AnalysisGraph()
        result = asyncio.run(graph.gather_context("echo hello"))
        assert "watcher" in result
        assert "librarian" in result
        assert "agent_latency_ms" in result

    def test_ainvoke(self):
        import asyncio
        graph = AnalysisGraph()
        result = asyncio.run(graph.ainvoke("echo hello"))
        assert "risk" in result

    def test_analyze_output_structure(self):
        import asyncio
        graph = AnalysisGraph()
        result = asyncio.run(graph.analyze_command("echo hello"))
        assert isinstance(result.get("risk"), str)
        assert isinstance(result.get("confidence"), (int, float))
        assert isinstance(result.get("alternatives"), list)
        assert "cached" in result


class TestSelectiveWorkerFanOut:
    def _make_state(self, **overrides):
        from orchestration.state import AnalysisState
        base = AnalysisState(
            command="echo hello",
            sanitized=None, parsed=None, rule_match=None, cached=None,
            needs_context=True,
            watcher_context=None, librarian_context=None, merged_context=None,
            risk_analysis=None, remediation=None, output=None,
            errors=[], stages={},
            agent_latency={"watcher": 0, "librarian": 0},
            early_exit=None,
            supervisor_decision={"run_watcher": True, "run_librarian": False, "command": "echo hello"},
            supervisor_fallback=False, supervisor_warning=None, command_guide=None,
        )
        base.update(overrides)
        return base

    @pytest.mark.asyncio
    async def test_watcher_only_called(self, mocker):
        from orchestration.analysis_graph import context_worker_node
        mock_watcher = mocker.patch("orchestration.analysis_graph._query_watcher", new_callable=AsyncMock)
        mock_librarian = mocker.patch("orchestration.analysis_graph._query_librarian", new_callable=AsyncMock)
        mock_repomix = mocker.patch("orchestration.analysis_graph._query_repomix", new_callable=AsyncMock)
        mock_watcher.return_value = {"os": "linux", "_latency_ms": 1.0}

        state = self._make_state()
        result = await context_worker_node(state)
        mock_watcher.assert_called_once()
        mock_librarian.assert_not_called()
        mock_repomix.assert_not_called()
        assert result["watcher_context"].get("os") == "linux"

    @pytest.mark.asyncio
    async def test_librarian_runs_repomix(self, mocker):
        from orchestration.analysis_graph import context_worker_node
        mock_watcher = mocker.patch("orchestration.analysis_graph._query_watcher", new_callable=AsyncMock)
        mock_librarian = mocker.patch("orchestration.analysis_graph._query_librarian", new_callable=AsyncMock)
        mock_repomix = mocker.patch("orchestration.analysis_graph._query_repomix", new_callable=AsyncMock)
        mock_librarian.return_value = {"matches": [{"file": "test.py"}], "_latency_ms": 1.0}
        mock_repomix.return_value = {"matches": [{"file": "lib.py"}]}

        state = self._make_state(supervisor_decision={"run_watcher": False, "run_librarian": True, "command": "echo hello"})
        result = await context_worker_node(state)
        mock_watcher.assert_not_called()
        mock_librarian.assert_called_once()
        mock_repomix.assert_called_once()
        assert len(result["librarian_context"]["matches"]) == 2

    @pytest.mark.asyncio
    async def test_neither_skips_workers(self, mocker):
        from orchestration.analysis_graph import context_worker_node
        mock_watcher = mocker.patch("orchestration.analysis_graph._query_watcher", new_callable=AsyncMock)
        mock_librarian = mocker.patch("orchestration.analysis_graph._query_librarian", new_callable=AsyncMock)
        mock_repomix = mocker.patch("orchestration.analysis_graph._query_repomix", new_callable=AsyncMock)

        state = self._make_state(supervisor_decision={"run_watcher": False, "run_librarian": False, "command": "echo hello"})
        result = await context_worker_node(state)
        mock_watcher.assert_not_called()
        mock_librarian.assert_not_called()
        mock_repomix.assert_not_called()
        assert result["merged_context"]["partial"] is False

    @pytest.mark.asyncio
    async def test_both_called_when_no_decision(self, mocker):
        from orchestration.analysis_graph import context_worker_node
        mock_watcher = mocker.patch("orchestration.analysis_graph._query_watcher", new_callable=AsyncMock)
        mock_librarian = mocker.patch("orchestration.analysis_graph._query_librarian", new_callable=AsyncMock)
        mock_repomix = mocker.patch("orchestration.analysis_graph._query_repomix", new_callable=AsyncMock)
        mock_watcher.return_value = {"os": "linux", "_latency_ms": 1.0}
        mock_librarian.return_value = {"matches": [], "_latency_ms": 1.0}
        mock_repomix.return_value = {"matches": []}

        state = self._make_state(supervisor_decision=None, needs_context=True)
        result = await context_worker_node(state)
        mock_watcher.assert_called_once()
        mock_librarian.assert_called_once()
        mock_repomix.assert_called_once()


class TestLLMSupervisorNode:
    """AGR-19: Supervisor routing matrix — every combination of flags tested."""

    @pytest.mark.asyncio
    async def test_supervisor_groq_watcher_only(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test")
        state = minimal_analysis_state(command="git status")
        with patch("orchestration.analysis_graph.route_command", new_callable=AsyncMock) as mock_route:
            mock_route.return_value = {"run_watcher": True, "run_librarian": False}
            result = await supervisor_node(state)
        assert result["needs_context"] is True
        assert result["supervisor_decision"]["run_watcher"] is True
        assert result["supervisor_decision"]["run_librarian"] is False

    @pytest.mark.asyncio
    async def test_supervisor_groq_librarian_only(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test")
        state = minimal_analysis_state(command="git status")
        with patch("orchestration.analysis_graph.route_command", new_callable=AsyncMock) as mock_route:
            mock_route.return_value = {"run_watcher": False, "run_librarian": True}
            result = await supervisor_node(state)
        assert result["needs_context"] is True
        assert result["supervisor_decision"]["run_watcher"] is False
        assert result["supervisor_decision"]["run_librarian"] is True

    @pytest.mark.asyncio
    async def test_supervisor_groq_neither(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test")
        state = minimal_analysis_state(command="echo hi")
        with patch("orchestration.analysis_graph.route_command", new_callable=AsyncMock) as mock_route:
            mock_route.return_value = {"run_watcher": False, "run_librarian": False}
            result = await supervisor_node(state)
        assert result["needs_context"] is False
        assert result["supervisor_decision"]["run_watcher"] is False
        assert result["supervisor_decision"]["run_librarian"] is False

    @pytest.mark.asyncio
    async def test_supervisor_groq_both(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test")
        state = minimal_analysis_state(command="docker ps")
        with patch("orchestration.analysis_graph.route_command", new_callable=AsyncMock) as mock_route:
            mock_route.return_value = {"run_watcher": True, "run_librarian": True}
            result = await supervisor_node(state)
        assert result["needs_context"] is True
        assert result["supervisor_decision"]["run_watcher"] is True
        assert result["supervisor_decision"]["run_librarian"] is True

    @pytest.mark.asyncio
    async def test_supervisor_no_key_uses_heuristic(self, monkeypatch):
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        state = minimal_analysis_state(command="git status")
        result = await supervisor_node(state)
        assert result["needs_context"] is True
        assert result["supervisor_decision"]["run_watcher"] is True
        assert result["supervisor_decision"]["run_librarian"] is True

    @pytest.mark.asyncio
    async def test_supervisor_no_key_echo_skips(self, monkeypatch):
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        state = minimal_analysis_state(command="echo hi")
        result = await supervisor_node(state)
        assert result["needs_context"] is False
        assert result["supervisor_decision"]["run_watcher"] is False
        assert result["supervisor_decision"]["run_librarian"] is False

    @pytest.mark.asyncio
    async def test_supervisor_records_stage_latency(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test")
        state = minimal_analysis_state(command="git status")
        with patch("orchestration.analysis_graph.route_command", new_callable=AsyncMock) as mock_route:
            mock_route.return_value = {"run_watcher": True, "run_librarian": False}
            result = await supervisor_node(state)
        assert "supervisor" in result.get("stages", {})


class TestNeedsContext:
    """PIP-01: _needs_context() heuristics cover git, docker, package managers."""

    @pytest.fixture
    def needs_context(self):
        from orchestration.analysis_graph import _needs_context
        return _needs_context

    def test_git_commands_need_context(self, needs_context):
        assert needs_context("git status")
        assert needs_context("git push origin main")
        assert needs_context("git commit -m 'fix'")

    def test_docker_commands_need_context(self, needs_context):
        assert needs_context("docker ps")
        assert needs_context("docker-compose up")
        assert needs_context("docker build -t myapp .")

    def test_package_manager_commands_need_context(self, needs_context):
        assert needs_context("pip install requests")
        assert needs_context("npm install")
        assert needs_context("yarn add lodash")
        assert needs_context("pnpm update")

    def test_safe_commands_do_not_need_context(self, needs_context):
        assert not needs_context("echo hello")
        assert not needs_context("ls -la")
        assert not needs_context("date")

    def test_file_ops_need_context(self, needs_context):
        assert needs_context("rm file.txt")
        assert needs_context("mv src dest")
        assert needs_context("cp a b")

    def test_path_refs_need_context(self, needs_context):
        assert needs_context("./script.sh")
        assert needs_context("../build.sh")
        assert needs_context("/usr/local/bin/test")

    def test_empty_command_returns_false(self, needs_context):
        assert not needs_context("")


class TestProviderContextWiring:
    """REL-01/02: Verify context is threaded from graph to providers."""

    @pytest.mark.asyncio
    async def test_risk_analyzer_passes_context(self, mocker):
        from orchestration.analysis_graph import risk_analyzer_node
        from orchestration.state import AnalysisState
        mock_result = {"risk": "LOW", "confidence": 0.5, "provider": "fallback"}
        mock_analyze = mocker.patch("orchestration.analysis_graph.analyze_risk",
                                    return_value=mock_result)
        state: AnalysisState = {
            "command": "rm file.txt",
            "sanitized": None, "parsed": None, "rule_match": None,
            "cached": None, "needs_context": True,
            "watcher_context": {"os": "linux"},
            "librarian_context": {"matches": [{"file": "test.py", "snippet": "print"}]},
            "merged_context": {"watcher": {"os": "linux"},
                               "librarian": {"matches": [{"file": "test.py", "snippet": "print"}]},
                               "partial": False},
            "risk_analysis": None, "remediation": None, "output": None,
            "errors": [], "stages": {},
            "agent_latency": {"watcher": 0, "librarian": 0},
            "early_exit": None,
            "supervisor_decision": None,
            "supervisor_fallback": False,
            "supervisor_warning": None,
            "command_guide": None,
        }
        result = await risk_analyzer_node(state)
        mock_analyze.assert_called_once()
        _args, kwargs = mock_analyze.call_args
        assert "context" in kwargs
        assert kwargs["context"]["watcher"]["os"] == "linux"
        assert len(kwargs["context"]["librarian"]["matches"]) == 1

    @pytest.mark.asyncio
    async def test_remediation_passes_context(self, mocker):
        from orchestration.analysis_graph import remediation_node
        from orchestration.state import AnalysisState
        mock_result = {"explanation": "safe", "alternatives": []}
        mock_remediate = mocker.patch("orchestration.analysis_graph.generate_remediation",
                                      return_value=mock_result)
        state: AnalysisState = {
            "command": "rm file.txt",
            "sanitized": None, "parsed": None, "rule_match": None,
            "cached": None, "needs_context": True,
            "watcher_context": {"os": "linux"},
            "librarian_context": {"matches": []},
            "merged_context": {"watcher": {"os": "linux"},
                               "librarian": {"matches": []},
                               "partial": False},
            "risk_analysis": {"risk": "HIGH", "confidence": 0.9, "provider": "groq"},
            "remediation": None, "output": None,
            "errors": [], "stages": {},
            "agent_latency": {"watcher": 0, "librarian": 0},
            "early_exit": None,
            "supervisor_decision": None,
            "supervisor_fallback": False,
            "supervisor_warning": None,
            "command_guide": None,
        }
        result = await remediation_node(state)
        mock_remediate.assert_called_once()
        _args, kwargs = mock_remediate.call_args
        assert "context" in kwargs
        assert kwargs["context"]["watcher"]["os"] == "linux"

    def test_groq_provider_formats_context(self):
        from providers.groq_provider import _format_context
        context = {
            "watcher": {"os": "linux", "shell": "bash",
                        "current_directory": "/home/user/project",
                        "git_context": {"branch": "main", "staged": 2, "unstaged": 1}},
            "librarian": {"matches": [{"file": "src/main.py",
                                       "content": "import os"}]},
        }
        formatted = _format_context(context)
        assert "System Context:" in formatted
        assert "OS: linux" in formatted
        assert "Shell: bash" in formatted
        assert "branch=main" in formatted
        assert "src/main.py" in formatted

    def test_groq_provider_formats_context_empty(self):
        from providers.groq_provider import _format_context
        assert _format_context(None) == ""
        assert _format_context({}) == ""

    def test_openrouter_provider_formats_context(self):
        from providers.openrouter_provider import _format_context
        context = {
            "watcher": {"os": "darwin", "tech_stack": ["python", "react"]},
            "librarian": {"matches": []},
        }
        formatted = _format_context(context)
        assert "System Context:" in formatted
        assert "OS: darwin" in formatted
        assert "Tech stack: python, react" in formatted

    def test_openrouter_provider_formats_context_empty(self):
        from providers.openrouter_provider import _format_context
        assert _format_context(None) == ""
        assert _format_context({}) == ""


class TestFormatNode:
    def test_format_node_sanitizer_exit(self):
        state: AnalysisState = {
            "command": "echo hello",
            "sanitized": {"correction": "echo hello", "syntax": {"valid": True},
                          "trailing_char": {"message": "fixed typo"}},
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
            "stages": {"sanitizer": 1.0},
            "agent_latency": {"watcher": 0, "librarian": 0},
            "early_exit": "sanitizer",
            "supervisor_decision": None,
            "supervisor_fallback": False,
            "supervisor_warning": None,
            "command_guide": None,
        }
        result = format_node(state)
        output = result.get("output", {})
        assert output.get("early_exit") == "sanitizer"
        assert output.get("risk") in ("SAFE", "LOW", "MEDIUM", "HIGH", "CRITICAL")

    def test_format_node_rule_exit(self):
        state: AnalysisState = {
            "command": "rm -rf /",
            "sanitized": {"normalized": "rm -rf /", "syntax": {"valid": True}},
            "parsed": None,
            "rule_match": {"matched": True, "rule_id": "R001", "severity": "HIGH",
                           "message": "Dangerous", "description": "rm -rf / is dangerous",
                           "category": "destructive", "confidence": 0.95, "risk": "HIGH"},
            "cached": None,
            "needs_context": False,
            "watcher_context": None,
            "librarian_context": None,
            "merged_context": None,
            "risk_analysis": None,
            "remediation": None,
            "output": None,
            "errors": [],
            "stages": {"sanitizer": 1.0, "parser": 0.5, "rule_engine": 0.3},
            "agent_latency": {"watcher": 0, "librarian": 0},
            "early_exit": "rule",
            "supervisor_decision": None,
            "supervisor_fallback": False,
            "supervisor_warning": None,
            "command_guide": None,
        }
        result = format_node(state)
        output = result.get("output", {})
        assert output.get("early_exit") == "rule_engine"
        assert output.get("rule_id") == "R001"

    def test_format_node_cache_exit(self):
        state: AnalysisState = {
            "command": "echo hello",
            "sanitized": {"normalized": "echo hello", "syntax": {"valid": True}},
            "parsed": None,
            "rule_match": None,
            "cached": {"risk": "LOW", "confidence": 0.8, "explanation": "cached result",
                       "alternatives": []},
            "needs_context": False,
            "watcher_context": None,
            "librarian_context": None,
            "merged_context": None,
            "risk_analysis": None,
            "remediation": None,
            "output": None,
            "errors": [],
            "stages": {"sanitizer": 1.0, "parser": 0.5, "rule_engine": 0.3, "cache": 0.1},
            "agent_latency": {"watcher": 0, "librarian": 0},
            "early_exit": "cache",
            "supervisor_decision": None,
            "supervisor_fallback": False,
            "supervisor_warning": None,
            "command_guide": None,
        }
        result = format_node(state)
        output = result.get("output", {})
        assert output.get("cached") is True
        assert output.get("early_exit") == "cache"

    def test_format_node_supervisor_fallback(self):
        state: AnalysisState = {
            "command": "git status",
            "sanitized": {"normalized": "git status", "syntax": {"valid": True}},
            "parsed": None,
            "rule_match": None,
            "cached": None,
            "needs_context": False,
            "watcher_context": None,
            "librarian_context": None,
            "merged_context": None,
            "risk_analysis": {"risk": "SAFE", "confidence": 0.9, "provider": "fallback"},
            "remediation": {"explanation": "safe", "alternatives": []},
            "output": None,
            "errors": ["Supervisor timed out after 500ms"],
            "stages": {"sanitizer": 1.0, "supervisor": 500.0},
            "agent_latency": {"watcher": 0, "librarian": 0},
            "early_exit": None,
            "supervisor_decision": {"run_watcher": False, "run_librarian": False},
            "supervisor_fallback": True,
            "supervisor_warning": "Context skipped: supervisor unavailable",
            "command_guide": None,
        }
        result = format_node(state)
        output = result.get("output", {})
        assert output.get("supervisor_fallback") is True
        assert "supervisor unavailable" in output.get("supervisor_warning", "")


class TestCommandGuideNode:
    @pytest.mark.asyncio
    async def test_guide_node_returns_guide_on_success(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test")
        state: AnalysisState = {
            "command": "git status",
            "sanitized": {"normalized": "git status", "syntax": {"valid": True}},
            "parsed": None, "rule_match": None, "cached": None,
            "needs_context": False,
            "watcher_context": None, "librarian_context": None,
            "merged_context": None,
            "risk_analysis": None, "remediation": None, "output": None,
            "errors": [], "stages": {},
            "agent_latency": {"watcher": 0, "librarian": 0},
            "early_exit": None,
            "supervisor_decision": None,
            "supervisor_fallback": False, "supervisor_warning": None, "command_guide": None,
        }
        mock_guide = {
            "when_to_use": "Check repository status.",
            "parameters": ["-s: short format"],
            "example_command": "git status -s",
        }
        with patch("orchestration.analysis_graph.generate_command_guide", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = mock_guide
            result = await command_guide_node(state)
            assert result["command_guide"] == mock_guide
            assert "command_guide" in result.get("stages", {})

    @pytest.mark.asyncio
    async def test_guide_node_skips_on_early_exit(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test")
        state: AnalysisState = {
            "command": "echo hello",
            "sanitized": {"correction": "echo hello", "syntax": {"valid": True}},
            "parsed": None, "rule_match": None, "cached": None,
            "needs_context": False,
            "watcher_context": None, "librarian_context": None,
            "merged_context": None,
            "risk_analysis": None, "remediation": None, "output": None,
            "errors": [], "stages": {},
            "agent_latency": {"watcher": 0, "librarian": 0},
            "early_exit": None,
            "supervisor_decision": None,
            "supervisor_fallback": False, "supervisor_warning": None, "command_guide": None,
        }
        with patch("orchestration.analysis_graph.generate_command_guide", new_callable=AsyncMock) as mock_gen:
            result = await command_guide_node(state)
            assert result == {}
            mock_gen.assert_not_called()

    @pytest.mark.asyncio
    async def test_guide_node_skips_without_key(self):
        import os
        old = os.environ.pop("GROQ_API_KEY", None)
        try:
            state: AnalysisState = {
                "command": "git status",
                "sanitized": {"normalized": "git status", "syntax": {"valid": True}},
                "parsed": None, "rule_match": None, "cached": None,
                "needs_context": False,
                "watcher_context": None, "librarian_context": None,
                "merged_context": None,
                "risk_analysis": None, "remediation": None, "output": None,
                "errors": [], "stages": {},
                "agent_latency": {"watcher": 0, "librarian": 0},
                "early_exit": None,
                "supervisor_decision": None,
                "supervisor_fallback": False, "supervisor_warning": None, "command_guide": None,
            }
            with patch("orchestration.analysis_graph.generate_command_guide", new_callable=AsyncMock) as mock_gen:
                result = await command_guide_node(state)
                assert result == {}
                mock_gen.assert_not_called()
        finally:
            if old:
                os.environ["GROQ_API_KEY"] = old

    def test_format_node_includes_command_guide_from_state(self):
        state: AnalysisState = {
            "command": "git status",
            "sanitized": {"normalized": "git status", "syntax": {"valid": True}},
            "parsed": None, "rule_match": None, "cached": None,
            "needs_context": False,
            "watcher_context": None, "librarian_context": None,
            "merged_context": None,
            "risk_analysis": {"risk": "SAFE", "confidence": 0.9, "provider": "fallback"},
            "remediation": {"explanation": "safe", "alternatives": []},
            "output": None,
            "errors": [], "stages": {"sanitizer": 1.0},
            "agent_latency": {"watcher": 0, "librarian": 0},
            "early_exit": None,
            "supervisor_decision": None,
            "supervisor_fallback": False, "supervisor_warning": None,
            "command_guide": {
                "when_to_use": "Check repository status.",
                "parameters": ["-s: short format"],
                "example_command": "git status -s",
            },
        }
        result = format_node(state)
        output = result.get("output", {})
        assert output.get("command_guide") is not None
        assert output["command_guide"]["when_to_use"] == "Check repository status."
        assert output["command_guide"]["example_command"] == "git status -s"

    @pytest.mark.asyncio
    async def test_guide_node_returns_empty_on_error(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test")
        state: AnalysisState = {
            "command": "git status",
            "sanitized": {"normalized": "git status", "syntax": {"valid": True}},
            "parsed": None, "rule_match": None, "cached": None,
            "needs_context": False,
            "watcher_context": None, "librarian_context": None,
            "merged_context": None,
            "risk_analysis": None, "remediation": None, "output": None,
            "errors": [], "stages": {},
            "agent_latency": {"watcher": 0, "librarian": 0},
            "early_exit": None,
            "supervisor_decision": None,
            "supervisor_fallback": False, "supervisor_warning": None, "command_guide": None,
        }
        with patch("orchestration.analysis_graph.generate_command_guide", new_callable=AsyncMock) as mock_gen:
            from providers.groq_command_guide import CommandGuideError
            mock_gen.side_effect = CommandGuideError("timeout")
            result = await command_guide_node(state)
            assert result == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
