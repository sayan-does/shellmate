import asyncio
import json
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ipc.client import ShellMateClient


@pytest.fixture(scope="module")
def daemon_running():
    """Enable daemon before tests, disable after."""
    import subprocess
    import time
    
    # Disable any existing daemon
    subprocess.run([sys.executable, "-m", "cli.main", "disable"], 
                   capture_output=True, timeout=10)
    time.sleep(1)
    
    # Enable daemon
    result = subprocess.run([sys.executable, "-m", "cli.main", "enable"], 
                           capture_output=True, timeout=30)
    assert result.returncode == 0
    
    time.sleep(2)  # Wait for daemon to fully start
    
    yield
    
    # Disable daemon after tests
    subprocess.run([sys.executable, "-m", "cli.main", "disable"], 
                   capture_output=True, timeout=10)


class TestIPCClient:
    def setup_method(self):
        self.client = ShellMateClient()

    @pytest.mark.asyncio
    async def test_send_command_success(self, daemon_running):
        result = await self.client.send_command("echo hello", timeout=30.0)
        assert "status" in result
        assert result["status"] in ["ok", "error"]

    @pytest.mark.asyncio
    async def test_send_status(self, daemon_running):
        result = await self.client.send_command("/status", timeout=30.0)
        assert "status" in result

    @pytest.mark.asyncio
    async def test_send_context_gatherer(self, daemon_running):
        result = await self.client.send_context_gatherer("echo hello")
        assert "status" in result


class TestAnalyzeIPCEnrichment:
    """AGR-26: IPC analyze response schema includes enrichment fields."""

    @pytest.mark.asyncio
    async def test_analyze_response_schema_has_risk(self, daemon_running):
        client = ShellMateClient()
        result = await client.send_command("echo hello")
        if result["status"] == "ok" and "data" in result:
            data = result["data"] if isinstance(result["data"], dict) else {}
            assert "risk" in data or "error" in data

    @pytest.mark.asyncio
    async def test_analyze_response_backward_compatible(self, daemon_running):
        client = ShellMateClient()
        result = await client.send_command("echo hello")
        if result["status"] == "ok" and "data" in result:
            data = result["data"] if isinstance(result["data"], dict) else {}
            for key in ("risk", "message"):
                assert key in data or "error" in data

    @pytest.mark.asyncio
    async def test_context_gatherer_unchanged(self, daemon_running):
        client = ShellMateClient()
        result = await client.send_context_gatherer("echo hello")
        assert "watcher" in result or "error" in result
        assert "librarian" in result or "error" in result


class TestIPCServer:
    @pytest.mark.asyncio
    async def test_analyze_handler(self, daemon_running):
        client = ShellMateClient()
        result = await client.send_command("echo hello")
        assert "status" in result
        assert "request_id" in result

    @pytest.mark.asyncio
    async def test_status_handler(self, daemon_running):
        client = ShellMateClient()
        result = await client.send_command("/status")
        assert "status" in result
        if result["status"] == "ok":
            assert "data" in result

    @pytest.mark.asyncio
    async def test_health_handler(self, daemon_running):
        client = ShellMateClient()
        result = await client.send_command("health")
        assert result["status"] == "ok"
        assert result["healthy"] is True

    @pytest.mark.asyncio
    async def test_context_gatherer_handler(self, daemon_running):
        client = ShellMateClient()
        result = await client.send_context_gatherer("echo hello")
        assert "status" in result

    @pytest.mark.asyncio
    async def test_malformed_json(self, daemon_running):
        from config.defaults import get_default_config
        
        config = get_default_config()
        host = config["daemon"]["host"]
        port = config["daemon"]["port"]
        
        reader, writer = await asyncio.open_connection(host, port)
        writer.write(b"not valid json")
        await writer.drain()
        
        data = await reader.read(65536)
        writer.close()
        await writer.wait_closed()
        
        result = json.loads(data.decode("utf-8"))
        assert result["status"] == "error"
        assert "Invalid JSON" in result["error"]

    @pytest.mark.asyncio
    async def test_oversized_request(self, daemon_running):
        from config.defaults import get_default_config
        
        config = get_default_config()
        host = config["daemon"]["host"]
        port = config["daemon"]["port"]
        
        reader, writer = await asyncio.open_connection(host, port)
        large_message = json.dumps({
            "command": "x" * (1024 * 1024 + 100),
            "request_id": "test"
        })
        writer.write(large_message.encode("utf-8"))
        await writer.drain()
        
        data = await reader.read(65536)
        writer.close()
        await writer.wait_closed()
        
        if data:
            result = json.loads(data.decode("utf-8"))
            assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_request_id_in_response(self, daemon_running):
        client = ShellMateClient()
        result = await client.send_command("echo hello")
        assert "request_id" in result
        assert isinstance(result["request_id"], str)
        assert len(result["request_id"]) > 0

    @pytest.mark.asyncio
    async def test_structured_error_response(self, daemon_running):
        client = ShellMateClient()
        result = await client.send_command("")
        if result["status"] == "error":
            assert "error" in result
            assert "request_id" in result

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, daemon_running):
        client = ShellMateClient()
        tasks = [client.send_command(f"echo test{i}") for i in range(5)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for r in results:
            if isinstance(r, Exception):
                continue
            assert "status" in r
            assert "request_id" in r


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])