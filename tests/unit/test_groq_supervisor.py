import asyncio
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from providers.groq_supervisor import route_command, SupervisorError, _parse_supervisor_json


class TestParseSupervisorJson:
    def test_plain_json(self):
        assert _parse_supervisor_json('{"run_watcher": true, "run_librarian": false}') == {
            "run_watcher": True, "run_librarian": False,
        }

    def test_fenced_json(self):
        raw = '```json\n{"run_watcher": false, "run_librarian": true}\n```'
        assert _parse_supervisor_json(raw)["run_librarian"] is True


@pytest.mark.asyncio
async def test_route_command_success(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(
        content='{"run_watcher": true, "run_librarian": false}'
    ))]

    with patch("providers.groq_supervisor.AsyncGroq") as MockGroq:
        instance = MockGroq.return_value
        instance.chat.completions.create = AsyncMock(return_value=mock_response)
        instance.aclose = AsyncMock()
        result = await route_command("git status")
        assert result == {"run_watcher": True, "run_librarian": False}


@pytest.mark.asyncio
async def test_timeout_raises_supervisor_error(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    with patch("providers.groq_supervisor.AsyncGroq") as MockGroq:
        instance = MockGroq.return_value
        async def _never(*args, **kwargs):
            await asyncio.sleep(10)
            return None
        instance.chat.completions.create = _never
        instance.aclose = AsyncMock()
        with pytest.raises(SupervisorError, match="timed out"):
            await route_command("git status", timeout_ms=1)


@pytest.mark.asyncio
async def test_invalid_json_raises(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="not json"))]
    with patch("providers.groq_supervisor.AsyncGroq") as MockGroq:
        instance = MockGroq.return_value
        instance.chat.completions.create = AsyncMock(return_value=mock_response)
        instance.aclose = AsyncMock()
        with pytest.raises(SupervisorError, match="Invalid JSON"):
            await route_command("git status")


@pytest.mark.asyncio
async def test_route_command_no_key():
    import os
    old = os.environ.pop("GROQ_API_KEY", None)
    try:
        with pytest.raises(SupervisorError):
            await route_command("echo hi")
    finally:
        if old:
            os.environ["GROQ_API_KEY"] = old
