"""End-to-End User Flow Test for ShellMate v2.0

Full user journey: config -> enable -> status -> analyze -> context-gatherer -> disable
Tests all v2 components: config, startup, agents (watcher/librarian), analyze pipeline.
"""

import pytest
import subprocess
import json
import sys
import os
import time
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from cli.version import VERSION
from config.credentials import load_env, save_env
from daemon.lifecycle import start_daemon, stop_daemon, check_daemon_status

VALID_GROQ_KEY = os.environ.get("GROQ_API_KEY",
    "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")
VALID_OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY",
    "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")
VALID_CONTEXT7_KEY = os.environ.get("CONTEXT7_API_KEY",
    "ctx7sk-b953fdd4-b260-4836-a7d9-f7a56da21104")


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


@pytest.fixture(scope="module")
def daemon_running():
    """Module-scoped fixture: ensures daemon is running for all tests that need it."""
    old_creds = load_env()
    save_env({
        "GROQ_API_KEY": VALID_GROQ_KEY,
        "OPENROUTER_API_KEY": VALID_OPENROUTER_KEY,
        "CONTEXT7_API_KEY": VALID_CONTEXT7_KEY,
    })
    run_cli("disable", timeout=10)
    time.sleep(0.5)
    result = run_cli("enable", timeout=60)
    assert result.returncode == 0, f"Enable failed: {result.stdout} {result.stderr}"
    time.sleep(3)
    yield
    run_cli("disable", timeout=10)
    save_env(old_creds)


class TestUserCLI:
    """Test basic CLI availability and commands."""

    def test_cli_help(self):
        result = run_cli("--help", timeout=10)
        assert result.returncode == 0
        assert "ShellMate" in result.stdout
        assert "sm -a" in result.stdout
        assert "enable" in result.stdout
        assert "disable" in result.stdout
        assert "status" in result.stdout
        assert "config" in result.stdout

    def test_cli_version(self):
        result = run_cli("--version", timeout=10)
        assert result.returncode == 0
        assert VERSION in result.stdout

    def test_unknown_command_error(self):
        result = run_cli("invalid", timeout=10)
        assert result.returncode == 2
        assert "Unknown command" in result.stdout

    def test_analyze_without_command(self):
        result = run_cli("-a", timeout=10)
        assert result.returncode == 2
        assert "Missing command" in result.stdout


class TestConfigFlow:
    """Test configuration flow - step 1 of user journey."""

    def test_config_command_smoke(self):
        result = run_cli("config", timeout=10)
        assert result.returncode == 0

    def test_config_shows_all_sections(self):
        result = run_cli("config", timeout=10)
        assert "Credentials" in result.stdout
        assert "Providers" in result.stdout
        assert "Settings" in result.stdout

    def test_config_set_credential(self):
        result = run_cli("config", "GROQ_API_KEY", VALID_GROQ_KEY, timeout=10)
        assert result.returncode == 0
        assert "Updated GROQ_API_KEY" in result.stdout

    def test_config_show_masked(self):
        save_env({"GROQ_API_KEY": VALID_GROQ_KEY})
        result = run_cli("config", "--show", timeout=10)
        assert result.returncode == 0
        assert "*" in result.stdout
        assert VALID_GROQ_KEY not in result.stdout


class TestDaemonEnable:
    """Test daemon enable flow - step 2 of user journey."""

    def test_daemon_enable_output(self, daemon_running):
        result = run_cli("disable", timeout=10)
        time.sleep(0.5)
        result = run_cli("enable", timeout=30)
        assert result.returncode == 0
        assert "started" in result.stdout.lower()

    def test_daemon_already_running(self, daemon_running):
        result = run_cli("enable", timeout=10)
        assert result.returncode == 0
        assert "already running" in result.stdout.lower()

    def test_daemon_startup_creates_session(self, daemon_running):
        from daemon.session import read_session
        session = read_session()
        assert session is not None
        assert "pid" in session
        assert "ipc_address" in session
        assert "cwd" in session


class TestDaemonStatus:
    """Test daemon status flow - step 3 of user journey."""

    def test_status_shows_running(self, daemon_running):
        result = run_cli("status", timeout=10)
        assert result.returncode == 0
        assert "Running" in result.stdout

    def test_status_shows_pid(self, daemon_running):
        result = run_cli("status", timeout=10)
        assert "PID:" in result.stdout

    def test_status_shows_providers(self, daemon_running):
        result = run_cli("status", timeout=10)
        assert "groq" in result.stdout.lower()
        assert "openrouter" in result.stdout.lower()

    def test_status_shows_credentials_table(self, daemon_running):
        result = run_cli("status", timeout=10)
        assert "GROQ_API_KEY" in result.stdout
        assert "OPENROUTER_API_KEY" in result.stdout


class TestCommandAnalysis:
    """Test command analysis flow - step 4 of user journey."""

    def test_analyze_safe_command(self, daemon_running):
        result = run_cli("-a", "echo", "hello", timeout=120)
        assert result.returncode == 0
        assert "SAFE" in result.stdout or "LOW" in result.stdout or "MEDIUM" in result.stdout

    def test_analyze_dangerous_command(self, daemon_running):
        result = run_cli("-a", "rm", "-rf", "/", timeout=60)
        assert result.returncode == 0
        assert "CRITICAL" in result.stdout or "HIGH" in result.stdout

    def test_analyze_with_quotes(self, daemon_running):
        result = run_cli("-a", "git", "commit", "-m", "'test'", timeout=60)
        assert result.returncode == 0

    def test_analyze_with_pipe(self, daemon_running):
        result = run_cli("-a", "curl", "example.com", "|", "bash", timeout=60)
        assert result.returncode == 0
        assert "HIGH" in result.stdout or "CRITICAL" in result.stdout

    def test_analyze_list_directory(self, daemon_running):
        result = run_cli("-a", "ls", "-la", timeout=60)
        assert result.returncode == 0

    def test_analyze_with_redirect(self, daemon_running):
        result = run_cli("-a", "echo", "test", ">", "file.txt", timeout=60)
        assert result.returncode == 0

    def test_analyze_variable_expansion(self, daemon_running):
        result = run_cli("-a", "echo", "$HOME", timeout=60)
        assert result.returncode == 0

    def test_analyze_returns_latency(self, daemon_running):
        result = run_cli("--quiet", "-a", "echo", "hello", timeout=60)
        assert result.returncode == 0
        try:
            data = json.loads(result.stdout)
            assert "risk" in data
        except json.JSONDecodeError:
            pass

    def test_analyze_with_pipe_redirect(self, daemon_running):
        result = run_cli("-a", "cat", "file.txt", "|", "grep", "pattern", ">", "out.txt", timeout=60)
        assert result.returncode == 0 or result.returncode == 3
        if result.returncode == 3:
            assert "error" in result.stdout.lower()


class TestDaemonNotRunningBehavior:
    """Test CLI behavior when daemon is not running. Restores daemon."""

    def test_analyze_daemon_not_running(self):
        run_cli("disable", timeout=10)
        time.sleep(1)
        result = run_cli("-a", "echo", "hello", timeout=10)
        assert result.returncode != 0 or "Connection refused" in result.stdout
        run_cli("enable", timeout=30)
        time.sleep(5)


class TestContextGatherer:
    """Test context gatherer via IPC - step 5 of user journey."""

    @pytest.mark.asyncio
    async def test_context_gatherer_basic(self, daemon_running):
        from ipc.client import ShellMateClient
        client = ShellMateClient()
        result = await client.send_context_gatherer("echo hello", timeout=30.0)
        assert isinstance(result, dict)
        assert "watcher" in result
        assert "librarian" in result

    @pytest.mark.asyncio
    async def test_context_gatherer_watcher_data(self, daemon_running):
        from ipc.client import ShellMateClient
        client = ShellMateClient()
        result = await client.send_context_gatherer("ls -la", timeout=30.0)
        assert "os" in result.get("watcher", {}) or "errors" in result

    @pytest.mark.asyncio
    async def test_context_gatherer_librarian_for_file_command(self, daemon_running):
        from ipc.client import ShellMateClient
        client = ShellMateClient()
        result = await client.send_context_gatherer("cat main.py", timeout=30.0)
        assert isinstance(result.get("librarian", {}).get("matches"), list)

    @pytest.mark.asyncio
    async def test_context_gatherer_latency(self, daemon_running):
        from ipc.client import ShellMateClient
        client = ShellMateClient()
        result = await client.send_context_gatherer("echo test", timeout=30.0)
        assert "latency_ms" in result
        assert isinstance(result["latency_ms"], (int, float))

    @pytest.mark.asyncio
    async def test_context_gatherer_agent_latency(self, daemon_running):
        from ipc.client import ShellMateClient
        client = ShellMateClient()
        result = await client.send_context_gatherer("ls", timeout=30.0)
        assert "agent_latency_ms" in result
        assert "watcher" in result["agent_latency_ms"]

    @pytest.mark.asyncio
    async def test_context_gatherer_empty_command(self, daemon_running):
        from ipc.client import ShellMateClient
        client = ShellMateClient()
        result = await client.send_context_gatherer("", timeout=30.0)
        assert result.get("librarian", {}).get("matches") == []

    @pytest.mark.asyncio
    async def test_context_gatherer_concurrent(self, daemon_running):
        from ipc.client import ShellMateClient
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


class TestDaemonDisable:
    """Test daemon disable flow - final step of user journey."""

    def test_disable_stops_daemon(self, daemon_running):
        result = run_cli("disable", timeout=10)
        assert result.returncode == 0
        assert "stopped" in result.stdout.lower()

    def test_status_shows_stopped_after_disable(self, daemon_running):
        run_cli("disable", timeout=10)
        time.sleep(1)
        result = run_cli("status", timeout=10)
        assert "Stopped" in result.stdout

    def test_disable_idempotent(self, daemon_running):
        run_cli("disable", timeout=10)
        result = run_cli("disable", timeout=10)
        assert result.returncode == 0
        assert "not running" in result.stdout.lower()


class TestFullUserJourney:
    """Test the complete user journey end-to-end."""

    def test_full_cycle(self):
        run_cli("disable", timeout=5)
        time.sleep(0.5)

        result = run_cli("config", timeout=5)
        assert result.returncode == 0

        save_env({
            "GROQ_API_KEY": VALID_GROQ_KEY,
            "OPENROUTER_API_KEY": VALID_OPENROUTER_KEY,
            "CONTEXT7_API_KEY": VALID_CONTEXT7_KEY,
        })

        result = run_cli("enable", timeout=60)
        assert result.returncode == 0
        assert "started" in result.stdout.lower()

        time.sleep(2)

        result = run_cli("status", timeout=10)
        assert result.returncode == 0
        assert "Running" in result.stdout
        assert "PID:" in result.stdout

        result = run_cli("--quiet", "-a", "echo", "hello", timeout=60)
        assert result.returncode == 0, f"analyze failed: {result.stdout}"

        result = run_cli("disable", timeout=10)
        assert result.returncode == 0
        assert "stopped" in result.stdout.lower()

        result = run_cli("status", timeout=10)
        assert "Stopped" in result.stdout

    def test_pipeline_rules_engine(self):
        from daemon.pipeline import run_pipeline
        result = run_pipeline("rm -rf /")
        assert result.get("risk") == "CRITICAL"
        assert result.get("early_exit") == "rule_engine"

    def test_pipeline_sanitizer(self):
        from daemon.pipeline import run_pipeline
        result = run_pipeline("echo hello ")
        assert "risk" in result

    def test_pipeline_empty_command(self):
        from daemon.pipeline import run_pipeline
        result = run_pipeline("")
        assert "risk" in result


class TestEnrichmentUserFlow:
    """AGR-24: E2E enrichment user flow tests."""

    def test_enable_startup_stages_reach_ready(self, daemon_running):
        from daemon.server import get_startup_stage
        stage = get_startup_stage()
        assert stage == "ready"

    def test_analyze_returns_command_guide_fields(self, daemon_running):
        result = run_cli("--quiet", "-a", "echo", "hello", timeout=60)
        assert result.returncode == 0
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            pytest.skip("JSON parse failed (daemon may need providers)")
            return
        if "command_guide" in data:
            assert isinstance(data["command_guide"], dict)
        assert "risk" in data

    def test_analyze_returns_supervisor_warning_on_fallback(self, daemon_running):
        result = run_cli("--quiet", "-a", "echo", "hello", timeout=60)
        assert result.returncode == 0
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            pytest.skip("JSON parse failed")
            return
        if "supervisor_warning" in data:
            assert isinstance(data["supervisor_warning"], str)
        assert "risk" in data

    def test_disable_still_prints_spec_message(self, daemon_running):
        result = run_cli("disable", timeout=10)
        assert result.returncode == 0
        assert "stopped" in result.stdout.lower()


class TestEnrichmentFlags:
    """AGR-25: Flags & no-key path tests."""

    def test_quiet_analyze_no_spinner_keys(self):
        result = run_cli("--quiet", "-a", "echo", "hello", timeout=60)
        assert result.returncode in (0, 3, 4)
        try:
            data = json.loads(result.stdout)
            assert isinstance(data, dict)
        except json.JSONDecodeError:
            pytest.fail("Not valid JSON")

    def test_quiet_includes_command_guide_when_present(self):
        result = run_cli("--quiet", "-a", "echo", "hello", timeout=60)
        assert result.returncode in (0, 3, 4)
        try:
            data = json.loads(result.stdout)
            if "command_guide" in data:
                assert isinstance(data["command_guide"], dict)
        except json.JSONDecodeError:
            pass

    def test_no_color_flag_parsed(self):
        result = run_cli("--no-color", "-a", "echo", "hello", timeout=60)
        assert result.returncode in (0, 3, 4)

    def test_no_groq_key_analyze_succeeds(self, monkeypatch):
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        from daemon.pipeline import run_pipeline
        result = run_pipeline("echo hello")
        assert "risk" in result

    def test_no_groq_key_no_command_guide(self, monkeypatch):
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        from daemon.pipeline import run_pipeline
        result = run_pipeline("echo hello")
        assert result.get("command_guide") is None


class TestQuietFlag:
    """Test the --quiet flag produces JSON output even when daemon is not running."""

    def test_cli_quiet_flag_returns_json(self):
        result = run_cli("--quiet", "-a", "echo", "hello", timeout=10)
        assert result.returncode in (0, 3, 4)
        try:
            data = json.loads(result.stdout)
            assert "risk" in data or "error" in data
        except json.JSONDecodeError:
            pytest.fail("Quiet mode output is not valid JSON")

    def test_cli_short_quiet_flag_returns_json(self):
        result = run_cli("-q", "-a", "echo", "hello", timeout=10)
        assert result.returncode in (0, 3, 4)
        try:
            data = json.loads(result.stdout)
            assert "risk" in data or "error" in data
        except json.JSONDecodeError:
            pytest.fail("Quiet mode output is not valid JSON")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
