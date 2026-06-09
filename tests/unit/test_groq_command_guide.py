import asyncio
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from providers.groq_command_guide import (
    generate_command_guide,
    CommandGuideError,
    _parse_guide_json,
    alternatives_from_guide,
)


class TestParseGuideJson:
    def test_plain_json(self):
        result = _parse_guide_json(
            '{"when_to_use": "test", "parameters": ["-v: verbose"], "example_command": "cmd -v"}'
        )
        assert result["when_to_use"] == "test"
        assert result["parameters"] == ["-v: verbose"]
        assert result["example_command"] == "cmd -v"

    def test_fenced_json(self):
        raw = '```json\n{"when_to_use": "check status", "parameters": [], "example_command": "git status"}\n```'
        result = _parse_guide_json(raw)
        assert result["when_to_use"] == "check status"

    def test_missing_fields_default(self):
        result = _parse_guide_json('{}')
        assert result["intent_guess"] == ""
        assert result["when_to_use"] == ""
        assert result["parameters"] == []
        assert result["suggested_command"] == ""
        assert result["example_command"] == ""


class TestAlternativesFromGuide:
    def test_builds_intent_parameters_and_command(self):
        guide = {
            "intent_guess": "Maybe you're trying to run pytest on tests/test_how.py",
            "parameters": ["test: path to test file", "-v: verbose"],
            "suggested_command": "python -m pytest tests/test_how.py -v",
        }
        alts = alternatives_from_guide(guide)
        assert alts[0].startswith("Maybe you're trying")
        assert "test: path" in alts[1]
        assert alts[-1] == "Try: python -m pytest tests/test_how.py -v"

    def test_empty_guide(self):
        assert alternatives_from_guide({}) == []
        assert alternatives_from_guide(None) == []


@pytest.mark.asyncio
async def test_generate_command_guide_success(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(
        content='{"when_to_use": "Check repo status.", "parameters": ["-s: short"], "example_command": "git status -s"}'
    ))]

    with patch("providers.groq_command_guide.AsyncGroq") as MockGroq:
        instance = MockGroq.return_value
        instance.chat.completions.create = AsyncMock(return_value=mock_response)
        instance.aclose = AsyncMock()
        result = await generate_command_guide("git status")
        assert result["when_to_use"] == "Check repo status."
        assert result["example_command"] == "git status -s"


@pytest.mark.asyncio
async def test_generate_command_guide_no_key():
    import os
    old = os.environ.pop("GROQ_API_KEY", None)
    try:
        with patch("config.credentials.load_env", return_value={}):
            with pytest.raises(CommandGuideError):
                await generate_command_guide("echo hi")
    finally:
        if old:
            os.environ["GROQ_API_KEY"] = old


@pytest.mark.asyncio
async def test_guide_timeout_returns_error(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    with patch("providers.groq_command_guide.AsyncGroq") as MockGroq:
        instance = MockGroq.return_value
        async def _never(*args, **kwargs):
            await asyncio.sleep(10)
            return None
        instance.chat.completions.create = _never
        instance.aclose = AsyncMock()
        with pytest.raises(CommandGuideError, match="timed out"):
            await generate_command_guide("git status", timeout_ms=1)


@pytest.mark.asyncio
async def test_guide_invalid_json_returns_error(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="not json"))]
    with patch("providers.groq_command_guide.AsyncGroq") as MockGroq:
        instance = MockGroq.return_value
        instance.chat.completions.create = AsyncMock(return_value=mock_response)
        instance.aclose = AsyncMock()
        with pytest.raises(CommandGuideError, match="Invalid JSON"):
            await generate_command_guide("git status")


@pytest.mark.asyncio
async def test_guide_includes_context_in_prompt(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    context_str = "\nSystem Context:\n  Directory: D:\\projects\\shellmate\n  Git: branch=main"
    captured_prompt = None

    with patch("providers.groq_command_guide.AsyncGroq") as MockGroq:
        instance = MockGroq.return_value
        instance.chat.completions.create = AsyncMock()
        instance.aclose = AsyncMock()

        async def _capture(*args, **kwargs):
            nonlocal captured_prompt
            captured_prompt = kwargs.get("messages", [{}])[0].get("content", "")
            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=MagicMock(
                content='{"when_to_use": "test", "parameters": [], "example_command": "git cherry-pick abc123"}'
            ))]
            return mock_response
        instance.chat.completions.create.side_effect = _capture

        await generate_command_guide("git status", context=context_str)
        assert captured_prompt is not None
        assert "D:\\projects\\shellmate" in captured_prompt or "shellmate" in captured_prompt
        assert "branch=main" in captured_prompt
        assert "current directory" in captured_prompt.lower() or "git branch" in captured_prompt.lower()
