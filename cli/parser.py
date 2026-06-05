import sys
from dataclasses import dataclass
from typing import Optional, List
from enum import Enum


class ExitCode(Enum):
    SUCCESS = 0
    USAGE_ERROR = 2
    TEMP_ERROR = 3
    INTERNAL_ERROR = 4


class Action(Enum):
    ANALYZE = "analyze"
    ENABLE = "enable"
    DISABLE = "disable"
    STATUS = "status"
    CONFIG = "config"
    HELP = "help"
    VERSION = "version"


@dataclass
class ParsedCommand:
    action: Action
    raw_command: Optional[str] = None
    tokens: List[str] = None
    error: Optional[str] = None
    suggestion: Optional[str] = None
    exit_code: ExitCode = ExitCode.SUCCESS

    def __post_init__(self):
        if self.tokens is None:
            self.tokens = []


class ShellMateCommandParser:
    def __init__(self, argv: List[str] = None):
        self.argv = argv or sys.argv[1:]

    def parse(self) -> ParsedCommand:
        if not self.argv:
            return ParsedCommand(
                action=Action.HELP,
                error="No command provided",
                suggestion="Run 'sm --help' for usage",
                exit_code=ExitCode.USAGE_ERROR,
            )

        first_arg = self.argv[0]

        if first_arg in ("-h", "--help"):
            return ParsedCommand(action=Action.HELP)

        if first_arg in ("-v", "--version"):
            return ParsedCommand(action=Action.VERSION)

        if first_arg == "-a":
            return self._parse_analyze()

        if first_arg in ("enable", "disable", "status", "config"):
            return self._parse_simple_command(first_arg)

        if first_arg.endswith(".py") or "test_" in first_arg or "/test" in first_arg or "\\test" in first_arg or "tests/" in first_arg:
            return ParsedCommand(
                action=Action.HELP,
                error="No command provided",
                suggestion="Run 'sm --help' for usage",
                exit_code=ExitCode.USAGE_ERROR,
            )

        return ParsedCommand(
            action=Action.HELP,
            error=f"Unknown command: {first_arg}",
            suggestion="Run 'sm --help' for usage. Use 'sm -a <command>' to analyze.",
            exit_code=ExitCode.USAGE_ERROR,
        )

    def _parse_analyze(self) -> ParsedCommand:
        if len(self.argv) < 2:
            return ParsedCommand(
                action=Action.ANALYZE,
                error="Missing command after -a",
                suggestion="Usage: sm -a <command>",
                exit_code=ExitCode.USAGE_ERROR,
            )

        raw_command = " ".join(self.argv[1:])
        return ParsedCommand(
            action=Action.ANALYZE,
            raw_command=raw_command,
            tokens=self.argv[1:],
        )

    def _parse_simple_command(self, cmd: str) -> ParsedCommand:
        action_map = {
            "enable": Action.ENABLE,
            "disable": Action.DISABLE,
            "status": Action.STATUS,
            "config": Action.CONFIG,
        }
        return ParsedCommand(action=action_map[cmd])


def parse_argv(argv: List[str] = None) -> ParsedCommand:
    parser = ShellMateCommandParser(argv)
    return parser.parse()