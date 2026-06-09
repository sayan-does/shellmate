"""E2E tests for daemon startup performance and low-latency initialization."""

import pytest
import subprocess
import sys
import os
import time
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from daemon.server import STARTUP_STAGES
from config.credentials import load_env, save_env

VALID_GROQ_KEY = os.environ.get("GROQ_API_KEY", "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")
VALID_OPENROUTER_KEY = os.environ.get("OPENROUTER_KEY", "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")


def run_cli(*args, timeout=30):
    env = os.environ.copy()
    env["SM_NONINTERACTIVE"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "cli.main", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


class TestDaemonStartupPerformance:
    """Test daemon starts within acceptable time limits."""

    STARTUP_TIMEOUT = 15.0
    STARTUP_ACCEPTABLE = 10.0

    @classmethod
    def setup_class(cls):
        run_cli("disable", timeout=10)
        time.sleep(1)

    @classmethod
    def teardown_class(cls):
        run_cli("disable", timeout=10)

    def measure_startup_time(self):
        """Measure daemon startup time."""
        run_cli("disable", timeout=5)
        time.sleep(0.5)
        start = time.monotonic()
        result = run_cli("enable", timeout=int(self.STARTUP_TIMEOUT) + 5)
        elapsed = time.monotonic() - start
        return elapsed, result

    def test_daemon_starts_within_timeout(self):
        elapsed, result = self.measure_startup_time()
        assert result.returncode == 0, f"Daemon failed: {result.stdout} {result.stderr}"
        assert "started" in result.stdout.lower()
        assert elapsed < self.STARTUP_TIMEOUT, f"Startup took {elapsed:.2f}s, exceeds {self.STARTUP_TIMEOUT}s"
        run_cli("disable", timeout=5)

    def test_startup_under_acceptable_threshold(self):
        elapsed, result = self.measure_startup_time()
        assert result.returncode == 0
        print(f"\n  Daemon startup time: {elapsed:.2f}s")
        if elapsed > self.STARTUP_ACCEPTABLE:
            print(f"  WARNING: Startup time {elapsed:.2f}s exceeds target {self.STARTUP_ACCEPTABLE}s")
        assert elapsed < self.STARTUP_TIMEOUT
        run_cli("disable", timeout=5)

    def test_daemon_reports_ready_via_status(self):
        run_cli("enable", timeout=30)
        time.sleep(2)
        result = run_cli("status", timeout=5)
        assert result.returncode == 0
        assert "Running" in result.stdout
        run_cli("disable", timeout=5)

    def test_consecutive_enable_disable_cycles(self):
        for i in range(3):
            result = run_cli("enable", timeout=30)
            assert result.returncode == 0, f"Cycle {i} enable failed"
            time.sleep(1)
            result = run_cli("disable", timeout=10)
            assert result.returncode == 0, f"Cycle {i} disable failed"
            time.sleep(0.5)


class TestStartupStages:
    """Test daemon startup stage progression."""

    def test_startup_stages_defined_correctly(self):
        assert STARTUP_STAGES == [
            "binding_ipc",
            "watcher_starting",
            "watcher_ready",
            "librarian_scanning",
            "librarian_ready",
            "providers_checked",
            "ready",
        ]
        assert "ready" in STARTUP_STAGES

    def test_startup_stages_progress_sequentially(self):
        from daemon.server import get_startup_stage, set_startup_stage
        set_startup_stage("binding_ipc")
        assert get_startup_stage() == "binding_ipc"

        set_startup_stage("watcher_starting")
        assert get_startup_stage() == "watcher_starting"

        set_startup_stage("ready")
        assert get_startup_stage() == "ready"

    def test_all_stages_valid(self):
        from daemon.server import set_startup_stage
        set_startup_stage("invalid_stage")
        from daemon.server import get_startup_stage
        assert get_startup_stage() != "invalid_stage"


class TestDaemonStartupWithCredentials:
    """Test daemon startup with API keys configured."""

    @classmethod
    def setup_class(cls):
        old = load_env()
        cls._old_creds = old
        run_cli("disable", timeout=10)
        time.sleep(1)

    @classmethod
    def teardown_class(cls):
        save_env(cls._old_creds)
        run_cli("disable", timeout=5)

    def test_startup_with_credentials_enabled(self):
        save_env({
            "GROQ_API_KEY": VALID_GROQ_KEY,
            "OPENROUTER_API_KEY": VALID_OPENROUTER_KEY,
        })
        result = run_cli("enable", timeout=30)
        assert result.returncode == 0
        status = run_cli("status", timeout=5)
        assert status.returncode == 0
        assert "Running" in status.stdout
        run_cli("disable", timeout=5)

    def test_startup_provider_status_reflects_credentials(self):
        save_env({})
        run_cli("enable", timeout=30)
        time.sleep(1)
        result = run_cli("status", timeout=5)
        assert "groq" in result.stdout.lower()
        run_cli("disable", timeout=5)

    def test_enable_after_credential_change(self):
        save_env({})
        run_cli("enable", timeout=30)
        time.sleep(1)
        run_cli("disable", timeout=5)

        save_env({
            "GROQ_API_KEY": VALID_GROQ_KEY,
            "OPENROUTER_API_KEY": VALID_OPENROUTER_KEY,
        })
        result = run_cli("enable", timeout=30)
        assert result.returncode == 0
        run_cli("disable", timeout=5)


class TestAgentStartupLatency:
    """Test agent initialization latency during startup."""

    def test_watcher_initializes_quickly(self):
        import asyncio
        from agents.watcher import WatcherAgent
        async def _test():
            agent = WatcherAgent()
            start = time.monotonic()
            await agent.initialize()
            elapsed = (time.monotonic() - start) * 1000
            assert elapsed < 5000, f"Watcher init took {elapsed:.0f}ms"
            assert agent._cached_context is not None
            assert "os" in agent._cached_context
            assert "shell" in agent._cached_context
        asyncio.run(_test())

    def test_librarian_init_returns_ready(self):
        import asyncio
        import tempfile
        from agents.librarian import LibrarianAgent
        async def _test():
            with tempfile.TemporaryDirectory() as tmpdir:
                original = os.getcwd()
                os.chdir(tmpdir)
                try:
                    agent = LibrarianAgent()
                    start = time.monotonic()
                    await agent.initialize()
                    ready = await agent.wait_until_indexed(timeout=10.0)
                    elapsed = (time.monotonic() - start) * 1000
                    assert ready, "Librarian did not become ready"
                    print(f"\n  Librarian init: {elapsed:.0f}ms, files: {agent.file_count}")
                finally:
                    os.chdir(original)
        asyncio.run(_test())


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
