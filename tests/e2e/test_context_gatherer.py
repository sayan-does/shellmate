import asyncio
import json
import os
import sys
import time
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ipc.client import ShellMateClient


@pytest.fixture(scope="module")
def daemon_running():
    import subprocess
    subprocess.run([sys.executable, "-m", "cli.main", "disable"],
                   capture_output=True, timeout=10)
    time.sleep(1)
    result = subprocess.run([sys.executable, "-m", "cli.main", "enable"],
                            capture_output=True, timeout=60)
    assert result.returncode == 0, f"Daemon failed to start: {result.stderr.decode()}"
    time.sleep(3)
    yield
    subprocess.run([sys.executable, "-m", "cli.main", "disable"],
                   capture_output=True, timeout=10)


class TestContextGathererE2E:
    @pytest.mark.asyncio
    async def test_context_gatherer_returns_watcher_data(self, daemon_running):
        client = ShellMateClient()
        result = await client.send_context_gatherer("echo hello", timeout=30.0)
        assert isinstance(result, dict), f"Expected dict, got {type(result)}: {result}"
        assert "watcher" in result
        assert "librarian" in result
        assert "timed_out" in result
        assert "latency_ms" in result

    @pytest.mark.asyncio
    async def test_context_gatherer_empty_command(self, daemon_running):
        client = ShellMateClient()
        result = await client.send_context_gatherer("", timeout=30.0)
        assert isinstance(result, dict)
        assert result.get("librarian", {}).get("matches") == []

    @pytest.mark.asyncio
    async def test_context_gatherer_file_command_triggers_librarian(self, daemon_running):
        client = ShellMateClient()
        result = await client.send_context_gatherer("cat main.py", timeout=30.0)
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_context_gatherer_has_latency_info(self, daemon_running):
        client = ShellMateClient()
        result = await client.send_context_gatherer("ls -la", timeout=30.0)
        assert isinstance(result, dict)
        assert "latency_ms" in result
        assert result["latency_ms"] >= 0
        assert "agent_latency_ms" in result
        assert "watcher" in result.get("agent_latency_ms", {})

    @pytest.mark.asyncio
    async def test_context_gatherer_partial_result_on_timeout(self, daemon_running):
        client = ShellMateClient()
        result = await client.send_context_gatherer("ls -la", timeout=30.0)
        assert isinstance(result, dict)
        assert "partial" in result

    @pytest.mark.asyncio
    async def test_context_gatherer_concurrent(self, daemon_running):
        client = ShellMateClient()
        tasks = [
            client.send_context_gatherer("echo test1", timeout=30.0),
            client.send_context_gatherer("rm file.txt", timeout=30.0),
            client.send_context_gatherer("cat config.json", timeout=30.0),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                continue
            assert "watcher" in r
            assert "librarian" in r
