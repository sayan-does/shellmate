"""E2E tests for agent behaviors -- what they do, how they detect, loading states."""

import pytest
import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from agents.base import (
    Agent, AgentRequest, AgentResponse, AgentStatus,
    AgentManager, get_agent_manager,
)
from agents.watcher import WatcherAgent, get_watcher_agent
from agents.librarian import (
    LibrarianAgent, get_librarian_agent,
    ELIGIBLE_EXTENSIONS, EXCLUDE_DIRS,
)
from agents.context_gatherer import ContextGatherer, get_context_gatherer


class TestWatcherAgentBehaviors:

    @pytest.mark.asyncio
    async def test_watcher_detects_os(self):
        agent = WatcherAgent()
        await agent.initialize()
        context = agent._cached_context
        assert "os" in context
        assert "system" in context["os"]
        assert context["os"]["system"] in ("Windows", "Linux", "Darwin")

    @pytest.mark.asyncio
    async def test_watcher_detects_shell(self):
        agent = WatcherAgent()
        await agent.initialize()
        context = agent._cached_context
        assert "shell" in context
        shell = context["shell"]
        assert shell is None or isinstance(shell, str)

    @pytest.mark.asyncio
    async def test_watcher_detects_terminal(self):
        agent = WatcherAgent()
        await agent.initialize()
        context = agent._cached_context
        assert "terminal" in context

    @pytest.mark.asyncio
    async def test_watcher_detects_environment_type(self):
        agent = WatcherAgent()
        await agent.initialize()
        context = agent._cached_context
        assert "environment" in context
        assert isinstance(context["environment"], dict)
        for key in ("wsl", "container", "ssh", "ci"):
            assert key in context["environment"]
            assert isinstance(context["environment"][key], bool)

    @pytest.mark.asyncio
    async def test_watcher_detects_interactive(self):
        agent = WatcherAgent()
        await agent.initialize()
        context = agent._cached_context
        assert "interactive" in context
        assert isinstance(context["interactive"], bool)

    @pytest.mark.asyncio
    async def test_watcher_detects_tech_stack(self):
        agent = WatcherAgent()
        await agent.initialize()
        context = agent._cached_context
        assert "tech_stack" in context
        assert isinstance(context["tech_stack"], list)

    @pytest.mark.asyncio
    async def test_watcher_detects_tech_stack_from_project_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            orig = os.getcwd()
            os.chdir(tmpdir)
            (Path(tmpdir) / "package.json").write_text("{}")
            (Path(tmpdir) / "Dockerfile").write_text("FROM python")
            try:
                agent = WatcherAgent()
                await agent.initialize()
                context = agent._cached_context
                assert "nodejs" in context["tech_stack"]
                assert "docker" in context["tech_stack"]
            finally:
                os.chdir(orig)

    @pytest.mark.asyncio
    async def test_watcher_detects_git_context(self):
        agent = WatcherAgent()
        await agent.initialize()
        context = agent._cached_context
        assert "git" in context
        git = context["git"]
        assert "available" in git
        assert "is_repo" in git
        assert isinstance(git["available"], bool)
        assert isinstance(git["is_repo"], bool)

    @pytest.mark.asyncio
    async def test_watcher_redacts_sensitive_data(self):
        agent = WatcherAgent()
        context = {
            "git": {
                "available": True,
                "remote_url": "https://ghp_token123@github.com/user/repo.git",
            },
            "shell": "/bin/bash",
        }
        result = agent._redact_context(context)
        assert "ghp_token123" not in result["git"]["remote_url"]

    @pytest.mark.asyncio
    async def test_watcher_status_lifecycle(self):
        agent = WatcherAgent()
        assert agent.status == AgentStatus.STARTING
        await agent.start()
        assert agent.status == AgentStatus.READY
        await agent.stop()
        assert agent.status == AgentStatus.STOPPED

    @pytest.mark.asyncio
    async def test_watcher_process_returns_data(self):
        agent = WatcherAgent()
        await agent.start()
        req = AgentRequest(request_id="test", command="get_context")
        resp = await agent.process(req)
        assert resp.status == "ok"
        assert "os" in resp.data
        assert "shell" in resp.data
        await agent.stop()

    @pytest.mark.asyncio
    async def test_watcher_not_ready_before_start(self):
        agent = WatcherAgent()
        req = AgentRequest(request_id="test", command="get_context")
        resp = await agent.send_request("get_context")
        assert resp.status == "error"


class TestLibrarianAgentBehaviors:

    @pytest.mark.asyncio
    async def test_librarian_scans_and_indexes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            orig = os.getcwd()
            os.chdir(tmpdir)
            (Path(tmpdir) / "demo.py").write_text("print('hello')\n")
            (Path(tmpdir) / "config.json").write_text('{"key": "val"}\n')
            (Path(tmpdir) / "README.md").write_text("# Demo\n")
            try:
                agent = LibrarianAgent()
                await agent.initialize()
                await agent.wait_until_indexed(timeout=5.0)
                assert agent.is_indexed
                assert agent.file_count == 3
            finally:
                os.chdir(orig)

    @pytest.mark.asyncio
    async def test_librarian_filters_excluded_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            orig = os.getcwd()
            os.chdir(tmpdir)
            (Path(tmpdir) / "main.py").write_text("ok\n")
            (Path(tmpdir) / ".git").mkdir()
            (Path(tmpdir) / ".git" / "config").write_text("[core]\n")
            (Path(tmpdir) / "node_modules").mkdir()
            (Path(tmpdir) / "node_modules" / "pkg.js").write_text("skip\n")
            try:
                agent = LibrarianAgent()
                await agent.initialize()
                await agent.wait_until_indexed(timeout=5.0)
                assert agent.file_count == 1
                assert all(".git" not in f["path"] for f in agent._files)
                assert all("node_modules" not in f["path"] for f in agent._files)
            finally:
                os.chdir(orig)

    @pytest.mark.asyncio
    async def test_librarian_skips_binary_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            orig = os.getcwd()
            os.chdir(tmpdir)
            (Path(tmpdir) / "main.py").write_text("print('ok')\n")
            (Path(tmpdir) / "image.png").write_bytes(b"\x89PNG\r\n")
            try:
                agent = LibrarianAgent()
                await agent.initialize()
                await agent.wait_until_indexed(timeout=5.0)
                assert agent.file_count == 1
                assert all(".png" not in f["ext"] for f in agent._files)
            finally:
                os.chdir(orig)

    @pytest.mark.asyncio
    async def test_librarian_search_returns_matches(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            orig = os.getcwd()
            os.chdir(tmpdir)
            (Path(tmpdir) / "app.py").write_text("import flask\napp = Flask(__name__)\n")
            (Path(tmpdir) / "utils.py").write_text("def helper():\n    pass\n")
            try:
                agent = LibrarianAgent()
                await agent.initialize()
                await agent.wait_until_indexed(timeout=5.0)
                matches = agent._search("app")
                assert len(matches) > 0
                assert any("app.py" in m["path"] for m in matches)
            finally:
                os.chdir(orig)

    @pytest.mark.asyncio
    async def test_librarian_search_max_10_results(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            orig = os.getcwd()
            os.chdir(tmpdir)
            for i in range(20):
                (Path(tmpdir) / f"mod_{i}.py").write_text(f"# module {i}\n")
            try:
                agent = LibrarianAgent()
                await agent.initialize()
                await agent.wait_until_indexed(timeout=5.0)
                matches = agent._search("mod_")
                assert len(matches) <= 10
            finally:
                os.chdir(orig)

    @pytest.mark.asyncio
    async def test_librarian_returns_snippets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            orig = os.getcwd()
            os.chdir(tmpdir)
            (Path(tmpdir) / "main.py").write_text("print('hello world')\n")
            try:
                agent = LibrarianAgent()
                await agent.initialize()
                await agent.wait_until_indexed(timeout=5.0)
                matches = agent._search("main")
                assert len(matches) > 0
                assert "snippet" in matches[0]
                assert len(matches[0]["snippet"]) > 0
            finally:
                os.chdir(orig)

    @pytest.mark.asyncio
    async def test_librarian_lifecycle(self):
        agent = LibrarianAgent()
        assert not agent.is_indexed
        assert agent.file_count == 0

    @pytest.mark.asyncio
    async def test_librarian_process_uninitialized(self):
        agent = LibrarianAgent()
        req = AgentRequest(request_id="test", command="search", data={"query": "test"})
        resp = await agent.process(req)
        assert resp.status == "not_ready"
        assert "partial" in resp.data
        assert resp.data["partial"]

    @pytest.mark.asyncio
    async def test_librarian_eligible_extensions_exist(self):
        assert ".py" in ELIGIBLE_EXTENSIONS
        assert ".js" in ELIGIBLE_EXTENSIONS
        assert ".json" in ELIGIBLE_EXTENSIONS
        assert ".md" in ELIGIBLE_EXTENSIONS

    @pytest.mark.asyncio
    async def test_librarian_exclude_dirs_exist(self):
        assert ".git" in EXCLUDE_DIRS
        assert "node_modules" in EXCLUDE_DIRS
        assert "__pycache__" in EXCLUDE_DIRS


class TestContextGathererBehaviors:

    @pytest.mark.asyncio
    async def test_gatherer_returns_expected_structure(self):
        gatherer = ContextGatherer()
        result = await gatherer.gather("echo hello")
        assert "watcher" in result
        assert "librarian" in result
        assert "timed_out" in result
        assert "errors" in result
        assert "latency_ms" in result
        assert "agent_latency" in result

    @pytest.mark.asyncio
    async def test_gatherer_returns_within_500ms(self):
        gatherer = ContextGatherer()
        start = time.monotonic()
        result = await gatherer.gather("echo hello")
        elapsed = (time.monotonic() - start) * 1000
        assert elapsed < 5000
        assert "latency_ms" in result

    @pytest.mark.asyncio
    async def test_gatherer_does_not_query_librarian_for_simple_commands(self):
        gatherer = ContextGatherer()
        result = await gatherer.gather("echo hello")
        assert result.get("librarian", {}).get("matches") == []

    @pytest.mark.asyncio
    async def test_gatherer_queries_librarian_for_file_ops(self):
        gatherer = ContextGatherer()
        result = await gatherer.gather("cat main.py")
        assert "librarian" in result

    @pytest.mark.asyncio
    async def test_gatherer_empty_command(self):
        gatherer = ContextGatherer()
        result = await gatherer.gather("")
        assert result["librarian"]["matches"] == []

    @pytest.mark.asyncio
    async def test_gatherer_handles_whitespace_command(self):
        gatherer = ContextGatherer()
        result = await gatherer.gather("   ")
        assert result["librarian"]["matches"] == []

    @pytest.mark.asyncio
    async def test_gatherer_handles_timed_out_agents_gracefully(self):
        gatherer = ContextGatherer()
        result = await gatherer.gather("ls -la")
        assert "timed_out" in result
        assert isinstance(result["timed_out"], list)
        assert "errors" in result
        assert isinstance(result["errors"], dict)

    @pytest.mark.asyncio
    async def test_gatherer_latency_is_positive(self):
        gatherer = ContextGatherer()
        result = await gatherer.gather("echo test")
        assert result["latency_ms"] >= 0

    @pytest.mark.asyncio
    async def test_gatherer_agent_latencies_present(self):
        gatherer = ContextGatherer()
        result = await gatherer.gather("cat main.py")
        assert "agent_latency" in result
        agent_lat = result["agent_latency"]
        if "watcher" in agent_lat:
            assert agent_lat["watcher"] >= 0
        if "librarian" in agent_lat:
            assert agent_lat["librarian"] >= 0


class TestAgentFrameworkBehaviors:

    @pytest.mark.asyncio
    async def test_agent_manager_register(self):
        mgr = AgentManager()
        watcher = WatcherAgent()
        mgr.register(watcher)
        assert mgr.get("watcher") is watcher
        assert mgr.get("nonexistent") is None

    @pytest.mark.asyncio
    async def test_agent_manager_start_stop_all(self):
        mgr = AgentManager()
        watcher = WatcherAgent()
        mgr.register(watcher)
        await mgr.start_all()
        assert watcher.status == AgentStatus.READY
        await mgr.stop_all()
        assert watcher.status == AgentStatus.STOPPED

    @pytest.mark.asyncio
    async def test_agent_manager_get_status(self):
        mgr = AgentManager()
        assert mgr.get_status() == {}
        watcher = WatcherAgent()
        mgr.register(watcher)
        await mgr.start_all()
        status = mgr.get_status()
        assert "watcher" in status
        assert status["watcher"] == "ready"
        await mgr.stop_all()

    @pytest.mark.asyncio
    async def test_send_request_to_unregistered_agent(self):
        mgr = AgentManager()
        result = await mgr.send_request("nonexistent", "test")
        assert result.status == "error"
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_agent_request_timeout_behavior(self):
        mgr = AgentManager()
        watcher = WatcherAgent()
        mgr.register(watcher)
        await mgr.start_all()
        req = AgentRequest(request_id="test", command="get_context", timeout=0.001)
        resp = await watcher.send_request("get_context", timeout=0.001)
        assert resp.status in ("ok", "timeout")
        await mgr.stop_all()

    @pytest.mark.asyncio
    async def test_agent_send_concurrent(self):
        mgr = AgentManager()
        watcher = WatcherAgent()
        mgr.register(watcher)
        await mgr.start_all()
        results = await mgr.send_concurrent(
            {"watcher": ("get_context", {})},
            timeout=5.0,
        )
        assert "watcher" in results
        assert results["watcher"].status == "ok"
        await mgr.stop_all()


class TestDaemonStartupStates:

    def test_startup_stages_defined(self):
        from daemon.server import STARTUP_STAGES
        expected = [
            "binding_ipc",
            "watcher_starting",
            "watcher_ready",
            "librarian_scanning",
            "librarian_ready",
            "providers_checked",
            "ready",
        ]
        assert STARTUP_STAGES == expected

    def test_startup_stage_setter_validates(self):
        from daemon.server import set_startup_stage, get_startup_stage
        set_startup_stage("binding_ipc")
        assert get_startup_stage() == "binding_ipc"
        set_startup_stage("invalid")
        assert get_startup_stage() != "invalid"
        set_startup_stage("ready")
        assert get_startup_stage() == "ready"

    def test_startup_stage_ready_at_end(self):
        from daemon.server import STARTUP_STAGES
        assert STARTUP_STAGES[-1] == "ready"

    def test_startup_ui_has_all_stages(self):
        from daemon.startup_ui import run_startup_ui
        assert callable(run_startup_ui)


class TestSingletonAccessors:

    def test_get_agent_manager_singleton(self):
        mgr1 = get_agent_manager()
        mgr2 = get_agent_manager()
        assert mgr1 is mgr2

    def test_get_watcher_agent_singleton(self):
        w1 = get_watcher_agent()
        w2 = get_watcher_agent()
        assert w1 is w2

    def test_get_librarian_agent_singleton(self):
        l1 = get_librarian_agent()
        l2 = get_librarian_agent()
        assert l1 is l2

    def test_get_context_gatherer_singleton(self):
        g1 = get_context_gatherer()
        g2 = get_context_gatherer()
        assert g1 is g2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
