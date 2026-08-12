import sys
import re
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from enum import Enum


class ExitCode(Enum):
    SUCCESS = 0
    USAGE_ERROR = 2
    TEMP_ERROR = 3
    INTERNAL_ERROR = 4


class Action(Enum):
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
    verbose: bool = False  # NEW Phase 5 - Task 5.1
    
    # NEW v3 fields
    queries: List[str] = field(default_factory=list)
    directives: List[str] = field(default_factory=list)
    overrides: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if self.tokens is None:
            self.tokens = []


_SUBCOMMANDS = frozenset({
    "enable", "disable", "status", "config",
    "install", "uninstall",
    "-h", "--help", "-v", "--version",
})


def _extract_bracket_syntax(command: str) -> tuple:
    """Extract [?...], [!...], [@...] from command string.
    
    Returns:
        tuple: (cleaned_command, queries, directives, overrides)
    """
    # Extract queries [?...]
    queries = re.findall(r'\[\?([^\]]+)\]', command)
    
    # Extract directives [!...]
    directives = re.findall(r'\[!([^\]]+)\]', command)
    
    # Extract overrides [@...]
    overrides_raw = re.findall(r'\[@([^\]]+)\]', command)
    overrides = {}
    for override in overrides_raw:
        if '=' in override:
            key, value = override.split('=', 1)
            overrides[key.strip()] = value.strip()
    
    # Remove all brackets from command
    cleaned = re.sub(r'\[[\?!@][^\]]+\]', '', command).strip()
    
    return cleaned, queries, directives, overrides


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
        verbose = False  # NEW Phase 5 - Task 5.1
        remaining = list(args)

        while remaining and remaining[0] not in _SUBCOMMANDS:
            flag = remaining.pop(0)
            if flag in ("--quiet", "-q"):
                quiet = True
            elif flag == "--no-color":
                no_color = True
            elif flag == "--dry-run":
                dry_run = True
            elif flag == "--verbose":
                verbose = True
            else:
                remaining.insert(0, flag)
                break

        return remaining, quiet, no_color, dry_run, verbose

    def parse(self) -> ParsedCommand:
        # Bare `sm` (and flag-only argv) → usage help (Done When: sm shows command list)
        if not self.argv:
            return ParsedCommand(action=Action.HELP)

        args, quiet, no_color, dry_run, verbose = self._consume_global_flags(self.argv)
        self._dry_run = dry_run

        if not args:
            return ParsedCommand(
                action=Action.HELP,
                no_color=no_color,
                dry_run=self._dry_run,
                verbose=verbose,
            )

        first_arg = args[0]

        if first_arg in ("-h", "--help"):
            return ParsedCommand(action=Action.HELP, no_color=no_color, dry_run=self._dry_run, verbose=verbose)

        if first_arg in ("-v", "--version"):
            return ParsedCommand(action=Action.VERSION, no_color=no_color, dry_run=self._dry_run, verbose=verbose)

        if first_arg in ("enable", "disable", "status", "config", "install", "uninstall"):
            parsed = self._parse_simple_command(first_arg, args[1:])
            parsed.no_color = no_color
            parsed.dry_run = self._dry_run
            parsed.verbose = verbose
            return parsed

        if first_arg.endswith(".py") or "test_" in first_arg or "/test" in first_arg or "\\test" in first_arg or "tests/" in first_arg:
            return ParsedCommand(
                action=Action.HELP,
                error="No command provided",
                suggestion="Run 'sm --help' for usage",
                exit_code=ExitCode.USAGE_ERROR,
                no_color=no_color,
                dry_run=self._dry_run,
                verbose=verbose,
            )

        return ParsedCommand(
            action=Action.HELP,
            error=f"Unknown command: {first_arg}",
            suggestion="Run 'sm --help' for usage.",
            exit_code=ExitCode.USAGE_ERROR,
            no_color=no_color,
            dry_run=self._dry_run,
            verbose=verbose,
        )

    def _parse_simple_command(self, cmd: str, rest: Optional[List[str]] = None) -> ParsedCommand:
        action_map = {
            "enable": Action.ENABLE,
            "disable": Action.DISABLE,
            "status": Action.STATUS,
            "config": Action.CONFIG,
            "install": Action.INSTALL,
            "uninstall": Action.UNINSTALL,
        }
        parsed = ParsedCommand(action=action_map[cmd])
        # Stash remaining flags for commands that accept them
        if rest:
            parsed.tokens = list(rest)
        return parsed


def parse_argv(argv: List[str] = None) -> ParsedCommand:
    parser = ShellMateCommandParser(argv)
    return parser.parse()
