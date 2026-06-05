"""
End-to-End User Flow Test for ShellMate v2.0

This test simulates a typical user workflow:
1. Check status
2. Analyze a command with -a flag
3. View configuration
"""

import pytest
import subprocess
import json
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def run_cli(*args, timeout=30):
    """Helper to run CLI commands"""
    return subprocess.run(
        [sys.executable, "-m", "cli.main", *args],
        capture_output=True,
        text=True,
        timeout=timeout
    )


class TestUserFlow:
    """Test complete user workflow scenarios"""

    @classmethod
    def setup_class(cls):
        """Enable daemon before tests"""
        run_cli("enable", timeout=30)
        import time
        time.sleep(2)  # Wait for daemon to fully start
        # Warm up the model by making a simple request
        run_cli("-a", "echo hello", timeout=60)

    @classmethod
    def teardown_class(cls):
        """Disable daemon after tests"""
        run_cli("disable", timeout=10)

    def test_cli_available(self):
        """Test that the CLI is accessible"""
        result = run_cli("--help", timeout=10)
        assert result.returncode == 0
        assert "ShellMate" in result.stdout
        assert "Intelligent Command Safety Layer" in result.stdout

    def test_status_command(self):
        """Test status command runs without error"""
        result = run_cli("status", timeout=10)
        assert result.returncode == 0
        assert "Daemon:" in result.stdout
        assert "Providers" in result.stdout

    def test_config_command(self):
        """Test config command displays configuration"""
        result = run_cli("config", timeout=10)
        assert result.returncode == 0
        assert "ShellMate Configuration" in result.stdout
        assert "Credentials" in result.stdout
        assert "Settings" in result.stdout

    def test_analyze_safe_command(self):
        """Test analyzing a safe command with -a flag"""
        result = run_cli("-a", "echo hello", timeout=30)
        assert result.returncode == 0
        assert "SAFE" in result.stdout or "LOW" in result.stdout

    def test_analyze_dangerous_command(self):
        """Test analyzing a dangerous command with -a flag"""
        result = run_cli("-a", "rm -rf /", timeout=30)
        assert result.returncode == 0
        assert "CRITICAL" in result.stdout or "HIGH" in result.stdout

    def test_analyze_with_quotes(self):
        """Test analyzing command with quotes"""
        result = run_cli("-a", "git", "commit", "-m", "\"test message\"", timeout=30)
        assert result.returncode == 0

    def test_analyze_with_pipe(self):
        """Test analyzing command with pipe"""
        result = run_cli("-a", "curl", "example.com", "|", "bash", timeout=30)
        assert result.returncode == 0
        assert "HIGH" in result.stdout or "CRITICAL" in result.stdout

    def test_invalid_command_error(self):
        """Test invalid command shows helpful error"""
        result = run_cli("invalid", timeout=10)
        assert result.returncode == 2  # USAGE_ERROR
        assert "Unknown command" in result.stdout
        assert "Suggestion" in result.stdout

    def test_missing_analyze_command_error(self):
        """Test -a without command shows error"""
        result = run_cli("-a", timeout=10)
        assert result.returncode == 2  # USAGE_ERROR
        assert "Missing command after -a" in result.stdout

    def test_version_flag(self):
        """Test --version flag"""
        result = run_cli("--version", timeout=10)
        assert result.returncode == 0
        assert "2.0.0" in result.stdout


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])