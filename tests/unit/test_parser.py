import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from parser.command_parser import parse_command


class TestParser:
    def test_basic_command(self):
        result = parse_command("ls -la")
        assert result["program"] == "ls"
        assert len(result["flags"]) == 1
        assert result["flags"][0]["flag"] == "-la"

    def test_git_commit(self):
        result = parse_command('git commit -m "test message"')
        assert result["program"] == "git"
        assert result["subcommand"] == "commit"
        assert result["flags"][0]["flag"] == "-m"

    def test_rm_rf(self):
        result = parse_command("rm -rf /")
        assert result["program"] == "rm"
        assert any(f["flag"] == "-rf" for f in result["flags"])
        assert "/" in result["arguments"]

    def test_pipeline_command(self):
        result = parse_command("curl http://example.com | bash")
        assert isinstance(result, dict)
        assert result.get("pipeline") is True

    def test_command_with_redirect(self):
        result = parse_command("echo hello > output.txt")
        assert isinstance(result, dict)
        assert result["program"] == "echo"

    def test_empty_command(self):
        result = parse_command("")
        assert result["program"] is None

    def test_quoted_args(self):
        result = parse_command("program --name='John Doe'")
        assert result["program"] == "program"

    def test_subcommand_recognition(self):
        result = parse_command("docker ps")
        assert result["program"] == "docker"
        assert result["subcommand"] == "ps"

        result = parse_command("unknown_tool do_something")
        assert result["program"] == "unknown_tool"
        assert result["subcommand"] is None
