import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from cli.parser import parse_argv, ParsedCommand, Action, ExitCode


class TestCLIParser:
    def test_empty_args(self):
        result = parse_argv([])
        assert result.action == Action.HELP
        assert result.exit_code == ExitCode.USAGE_ERROR
        assert "No command provided" in result.error

    def test_help_flag(self):
        result = parse_argv(["-h"])
        assert result.action == Action.HELP
        assert result.exit_code == ExitCode.SUCCESS

    def test_help_long_flag(self):
        result = parse_argv(["--help"])
        assert result.action == Action.HELP

    def test_version_flag(self):
        result = parse_argv(["-v"])
        assert result.action == Action.VERSION

    def test_version_long_flag(self):
        result = parse_argv(["--version"])
        assert result.action == Action.VERSION

    def test_analyze_simple(self):
        result = parse_argv(["-a", "echo", "hello"])
        assert result.action == Action.ANALYZE
        assert result.raw_command == "echo hello"
        assert result.tokens == ["echo", "hello"]

    def test_analyze_with_flags(self):
        result = parse_argv(["-a", "git", "push", "origin", "main"])
        assert result.action == Action.ANALYZE
        assert result.raw_command == "git push origin main"

    def test_analyze_with_quotes(self):
        result = parse_argv(["-a", "git", "commit", "-m", "\"test message\""])
        assert result.action == Action.ANALYZE
        assert "test message" in result.raw_command

    def test_analyze_with_pipe(self):
        result = parse_argv(["-a", "curl", "example.com", "|", "bash"])
        assert result.action == Action.ANALYZE
        assert "|" in result.raw_command

    def test_analyze_with_redirect(self):
        result = parse_argv(["-a", "ls", ">", "output.txt"])
        assert result.action == Action.ANALYZE
        assert ">" in result.raw_command

    def test_analyze_missing_command(self):
        result = parse_argv(["-a"])
        assert result.action == Action.ANALYZE
        assert result.exit_code == ExitCode.USAGE_ERROR
        assert "Missing command after -a" in result.error

    def test_enable_command(self):
        result = parse_argv(["enable"])
        assert result.action == Action.ENABLE
        assert result.exit_code == ExitCode.SUCCESS

    def test_disable_command(self):
        result = parse_argv(["disable"])
        assert result.action == Action.DISABLE

    def test_status_command(self):
        result = parse_argv(["status"])
        assert result.action == Action.STATUS

    def test_config_command(self):
        result = parse_argv(["config"])
        assert result.action == Action.CONFIG

    def test_unknown_command(self):
        result = parse_argv(["unknown"])
        assert result.action == Action.HELP
        assert result.exit_code == ExitCode.USAGE_ERROR
        assert "Unknown command: unknown" in result.error

    def test_old_analyze_usage(self):
        result = parse_argv(["analyze", "echo hello"])
        assert result.action == Action.HELP
        assert result.exit_code == ExitCode.USAGE_ERROR

    def test_shell_special_tokens(self):
        result = parse_argv(["-a", "rm", "-rf", "/tmp/test;", "&&", "echo", "done"])
        assert result.action == Action.ANALYZE
        assert ";" in result.raw_command
        assert "&&" in result.raw_command