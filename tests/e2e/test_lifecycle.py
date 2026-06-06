import pytest
import subprocess
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def run_cli(*args, timeout=30):
    return subprocess.run(
        [sys.executable, "-m", "cli.main", *args],
        capture_output=True,
        text=True,
        timeout=timeout
    )


class TestDaemonLifecycle:
    @classmethod
    def setup_class(cls):
        run_cli("disable", timeout=10)
        time.sleep(1)

    @classmethod
    def teardown_class(cls):
        run_cli("disable", timeout=10)

    def test_enable_daemon(self):
        result = run_cli("enable", timeout=30)
        assert result.returncode == 0
        assert "Daemon started" in result.stdout

        status = run_cli("status", timeout=10)
        assert status.returncode == 0
        assert "Running" in status.stdout

    def test_disable_daemon(self):
        run_cli("enable", timeout=30)
        time.sleep(1)

        result = run_cli("disable", timeout=10)
        assert result.returncode == 0
        assert "stopped" in result.stdout.lower()

        status = run_cli("status", timeout=10)
        assert status.returncode == 0
        assert "Stopped" in status.stdout

    def test_enable_idempotent(self):
        run_cli("enable", timeout=30)
        time.sleep(1)

        result = run_cli("enable", timeout=10)
        assert result.returncode == 0
        assert "already running" in result.stdout.lower()

        run_cli("disable", timeout=10)

    def test_status_shows_session_info(self):
        run_cli("enable", timeout=30)
        time.sleep(1)

        result = run_cli("status", timeout=10)
        assert result.returncode == 0
        assert "Running" in result.stdout
        assert "PID:" in result.stdout

        run_cli("disable", timeout=10)

    def test_stale_session_cleanup(self):
        from daemon.session import create_session, read_session, cleanup_stale_sessions

        create_session(999999, "/tmp", "127.0.0.1:9823")
        session = read_session()
        assert session is not None
        assert session["pid"] == 999999

        count = cleanup_stale_sessions()
        assert count == 1
        assert read_session() is None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])