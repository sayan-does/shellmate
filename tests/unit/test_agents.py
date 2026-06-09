import os
import sys
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from agents.base import (
    Agent, AgentRequest, AgentResponse, AgentStatus,
    AgentManager, get_agent_manager,
)
from agents.watcher import WatcherAgent, get_watcher_agent


class TestAgentFramework:
    def test_agent_request_dataclass(self):
        req = AgentRequest(request_id="test-1", command="echo hello")
        assert req.request_id == "test-1"
        assert req.command == "echo hello"
        assert req.data == {}
        assert req.timeout == 5.0

        req2 = AgentRequest(request_id="test-2", command="ls", data={"path": "/"}, timeout=10.0)
        assert req2.data == {"path": "/"}
        assert req2.timeout == 10.0

    def test_agent_response_dataclass(self):
        resp = AgentResponse(
            request_id="test-1",
            agent_name="watcher",
            status="ok",
            data={"key": "value"},
        )
        assert resp.request_id == "test-1"
        assert resp.agent_name == "watcher"
        assert resp.status == "ok"
        assert resp.data == {"key": "value"}
        assert resp.error is None
        assert resp.latency_ms == 0.0

    def test_agent_status_enum(self):
        assert AgentStatus.STARTING.value == "starting"
        assert AgentStatus.READY.value == "ready"
        assert AgentStatus.ERROR.value == "error"
        assert AgentStatus.STOPPED.value == "stopped"

    def test_agent_manager_register_and_get(self):
        mgr = AgentManager()
        agent = WatcherAgent()
        mgr.register(agent)
        assert mgr.get("watcher") is agent
        assert mgr.get("nonexistent") is None

    def test_agent_manager_get_status_empty(self):
        mgr = AgentManager()
        assert mgr.get_status() == {}

    @pytest.mark.asyncio
    async def test_agent_manager_send_request_to_nonexistent(self):
        mgr = AgentManager()
        result = await mgr.send_request("nonexistent", "test")
        assert result.status == "error"
        assert "not found" in result.error

    def test_get_agent_manager(self):
        mgr = get_agent_manager()
        assert mgr is not None
        assert isinstance(mgr, AgentManager)


class TestWatcherAgent:
    @pytest.mark.asyncio
    async def test_agent_initial_status(self):
        agent = WatcherAgent()
        assert agent.status == AgentStatus.STARTING
        assert agent.name == "watcher"

    @pytest.mark.asyncio
    async def test_initialize_and_shutdown(self):
        agent = WatcherAgent()
        await agent.start()
        assert agent.status == AgentStatus.READY
        await agent.stop()
        assert agent.status == AgentStatus.STOPPED

    @pytest.mark.asyncio
    async def test_process_returns_cached_context(self):
        agent = WatcherAgent()
        await agent.initialize()

        req = AgentRequest(request_id="test-1", command="get_context")
        response = await agent.process(req)

        assert response.status == "ok"
        assert response.agent_name == "watcher"
        assert response.request_id == "test-1"
        assert "os" in response.data
        assert "shell" in response.data
        assert "git" in response.data
        assert response.latency_ms == 0.0

    @pytest.mark.asyncio
    async def test_detect_os(self):
        agent = WatcherAgent()
        os_info = agent._detect_os()
        assert "system" in os_info
        assert "release" in os_info

    @pytest.mark.asyncio
    async def test_detect_interactive(self):
        agent = WatcherAgent()
        result = agent._detect_interactive()
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_redact_context_redacts_git_url(self):
        agent = WatcherAgent()
        context = {
            "git": {
                "available": True,
                "is_repo": True,
                "remote_url": "https://token@github.com/user/repo.git",
            },
            "shell": "/bin/bash",
        }
        result = agent._redact_context(context)
        assert result["git"]["remote_url"] != "https://token@github.com/user/repo.git"
        assert "token" not in result["git"]["remote_url"]

    @pytest.mark.asyncio
    async def test_redact_context_no_git(self):
        agent = WatcherAgent()
        context = {"shell": "/bin/bash", "git": {"available": False}}
        result = agent._redact_context(context)
        assert result["shell"] == "/bin/bash"


class TestAgentManagerConcurrent:
    @pytest.mark.asyncio
    async def test_start_and_stop_all(self):
        mgr = AgentManager()
        watcher = WatcherAgent()
        mgr.register(watcher)

        await mgr.start_all()
        assert watcher.status == AgentStatus.READY

        await mgr.stop_all()
        assert watcher.status == AgentStatus.STOPPED

    @pytest.mark.asyncio
    async def test_send_concurrent(self):
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
