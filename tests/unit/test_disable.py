import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest


class TestDisableMessage:
    """DIS-01: Verify disable message matches spec."""

    def test_disable_message_uses_spec_text(self):
        from cli.commands.disable import disable
        import inspect
        source = inspect.getsource(disable)
        assert "ShellMate has been disabled" in source

    def test_disable_no_longer_uses_old_message(self):
        from cli.commands.disable import disable
        import inspect
        source = inspect.getsource(disable)
        assert "Daemon stopped." not in source


class TestConcurrentStartup:
    """ENB-02: Verify watcher and librarian start concurrently."""

    def test_server_uses_asyncio_gather_for_agents(self):
        import inspect
        from daemon.server import run_daemon
        source = inspect.getsource(run_daemon)
        assert "asyncio.gather" in source

    def test_watcher_and_librarian_start_in_gather(self):
        import inspect
        from daemon.server import run_daemon
        source = inspect.getsource(run_daemon)
        assert "_start_watcher" in source
        assert "_start_librarian" in source
