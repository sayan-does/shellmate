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
    INSTALL = "install"
    UNINSTALL = "uninstall"
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
    quiet: bool = False
    no_color: bool = False
    dry_run: bool = False

    def __post_init__(self):
        if self.tokens is None:
            self.tokens = []


_SUBCOMMANDS = frozenset({
    "-a", "analyze", "enable", "disable", "status", "config",
    "install", "uninstall", "-h", "--help", "-v", "--version",
})


class ShellMateCommandParser:
    def __init__(self, argv: List[str] = None):
        self.argv = argv or sys.argv[1:]

    def _consume_global_flags(self, args: List[str]):
        """Parse sm-level flags only before the subcommand.

        Flags that belong to the analyzed shell command (e.g. pytest -q) must
        not be stripped from argv.
        """
        quiet = False
        no_color = False
        dry_run = False
        remaining = list(args)

        while remaining and remaining[0] not in _SUBCOMMANDS:
            flag = remaining.pop(0)
            if flag in ("--quiet", "-q"):
                quiet = True
            elif flag == "--no-color":
                no_color = True
            elif flag == "--dry-run":
                dry_run = True
            else:
                remaining.insert(0, flag)
                break

        return remaining, quiet, no_color, dry_run

    def parse(self) -> ParsedCommand:
        if not self.argv:
            return ParsedCommand(
                action=Action.HELP,
                error="No command provided",
                suggestion="Run 'sm --help' for usage",
                exit_code=ExitCode.USAGE_ERROR,
            )

        args, quiet, no_color, dry_run = self._consume_global_flags(self.argv)
        self._dry_run = dry_run

        if not args:
            return ParsedCommand(
                action=Action.HELP,
                error="No command provided",
                suggestion="Run 'sm --help' for usage",
                exit_code=ExitCode.USAGE_ERROR,
                no_color=no_color,
                dry_run=self._dry_run,
            )

        first_arg = args[0]

        if first_arg in ("-h", "--help"):
            return ParsedCommand(action=Action.HELP, no_color=no_color, dry_run=self._dry_run)

        if first_arg in ("-v", "--version"):
            return ParsedCommand(action=Action.VERSION, no_color=no_color, dry_run=self._dry_run)

        if first_arg in ("-a", "analyze"):
            parsed = self._parse_analyze(args, quiet)
            parsed.no_color = no_color
            parsed.dry_run = self._dry_run
            return parsed

        if first_arg in ("enable", "disable", "status", "config", "install", "uninstall"):
            parsed = self._parse_simple_command(first_arg)
            parsed.no_color = no_color
            parsed.dry_run = self._dry_run
            return parsed

        if first_arg.endswith(".py") or "test_" in first_arg or "/test" in first_arg or "\\test" in first_arg or "tests/" in first_arg:
            return ParsedCommand(
                action=Action.HELP,
                error="No command provided",
                suggestion="Run 'sm --help' for usage",
                exit_code=ExitCode.USAGE_ERROR,
                no_color=no_color,
                dry_run=self._dry_run,
            )

        return ParsedCommand(
            action=Action.HELP,
            error=f"Unknown command: {first_arg}",
            suggestion="Run 'sm --help' for usage. Use 'sm -a <command>' to analyze.",
            exit_code=ExitCode.USAGE_ERROR,
            no_color=no_color,
            dry_run=self._dry_run,
        )

    def _parse_analyze(self, args: List[str] = None, quiet: bool = False) -> ParsedCommand:
        remaining = (args or self.argv)[1:]
        if not remaining:
            return ParsedCommand(
                action=Action.ANALYZE,
                error="Missing command to analyze",
                suggestion="Usage: sm -a <command>",
                exit_code=ExitCode.USAGE_ERROR,
                quiet=quiet,
            )

        raw_command = " ".join(remaining)
        return ParsedCommand(
            action=Action.ANALYZE,
            raw_command=raw_command,
            tokens=remaining,
            quiet=quiet,
        )

    def _parse_simple_command(self, cmd: str) -> ParsedCommand:
        action_map = {
            "enable": Action.ENABLE,
            "disable": Action.DISABLE,
            "status": Action.STATUS,
            "config": Action.CONFIG,
            "install": Action.INSTALL,
            "uninstall": Action.UNINSTALL,
        }
        return ParsedCommand(action=action_map[cmd])


def parse_argv(argv: List[str] = None) -> ParsedCommand:
    parser = ShellMateCommandParser(argv)
    return parser.parse()