import os
import sys
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from agents.context_gatherer import (
    ContextGatherer, get_context_gatherer,
    CONTEXT_TIMEOUT, CATEGORY_NEEDS_LIBRARIAN, FILE_REF_PATTERN,
)


class TestContextGatherer:
    def test_get_context_gatherer(self):
        gatherer = get_context_gatherer()
        assert gatherer is not None
        assert isinstance(gatherer, ContextGatherer)

    def test_needs_librarian_for_file_ops(self):
        gatherer = ContextGatherer()
        assert gatherer._needs_librarian("rm -rf ./build")
        assert gatherer._needs_librarian("cat /etc/passwd")
        assert gatherer._needs_librarian("nano main.py")
        assert gatherer._needs_librarian("cat ./config.json")

    def test_needs_librarian_false_for_non_file_ops(self):
        gatherer = ContextGatherer()
        assert not gatherer._needs_librarian("echo hello")
        assert not gatherer._needs_librarian("ls")
        assert not gatherer._needs_librarian("git status")

    def test_needs_librarian_for_path_references(self):
        gatherer = ContextGatherer()
        assert gatherer._needs_librarian("ls ./src")
        assert gatherer._needs_librarian("python ../script.py")
        assert gatherer._needs_librarian("cat .\\file.txt")

    def test_needs_librarian_no_tokens(self):
        gatherer = ContextGatherer()
        assert not gatherer._needs_librarian("")

    @pytest.mark.asyncio
    async def test_gather_empty_command(self):
        gatherer = ContextGatherer()
        result = await gatherer.gather("")
        assert result["watcher"] == {}
        assert result["librarian"]["matches"] == []
        assert result["partial"] is False
        assert isinstance(result["latency_ms"], float)

    @pytest.mark.asyncio
    async def test_gather_simple_command(self):
        gatherer = ContextGatherer()
        result = await gatherer.gather("echo hello")
        assert "watcher" in result
        assert "librarian" in result
        assert isinstance(result["latency_ms"], float)

    @pytest.mark.asyncio
    async def test_context_timeout_constant(self):
        assert CONTEXT_TIMEOUT == 0.5

    def test_category_needs_librarian(self):
        assert "rm" in CATEGORY_NEEDS_LIBRARIAN
        assert "mv" in CATEGORY_NEEDS_LIBRARIAN
        assert "nano" in CATEGORY_NEEDS_LIBRARIAN

    def test_file_ref_pattern(self):
        assert "./" in FILE_REF_PATTERN
        assert "../" in FILE_REF_PATTERN

    @pytest.mark.asyncio
    async def test_gather_with_file_reference(self):
        gatherer = ContextGatherer()
        result = await gatherer.gather("cat ./config.json")
        assert "librarian" in result
        assert isinstance(result["latency_ms"], float)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
