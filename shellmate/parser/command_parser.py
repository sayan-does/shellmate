import shlex
import re

PIPE_PATTERN = re.compile(r"(\||&&|;|\|\|)")
REDIRECT_PATTERN = re.compile(r"(?:^|[^<>])([<>]{1,2}|>&|<>|>>|<<)")

SUPPORTED_SUBCOMMANDS = {
    "git": ["add", "commit", "push", "pull", "clone", "checkout", "branch", "merge", "rebase", "log", "status", "diff", "fetch", "remote", "stash", "tag", "init", "config", "reset"],
    "npm": ["install", "run", "test", "build", "start", "publish", "update", "audit", "init", "link", "uninstall"],
    "docker": ["run", "exec", "build", "push", "pull", "ps", "images", "stop", "start", "restart", "rm", "logs", "compose"],
    "kubectl": ["get", "apply", "delete", "describe", "logs", "exec", "create", "port-forward", "rollout"],
    "pip": ["install", "uninstall", "list", "show", "freeze", "check"],
    "brew": ["install", "uninstall", "update", "upgrade", "list", "search", "info", "services"],
    "cargo": ["build", "run", "test", "check", "clippy", "add", "remove", "publish", "update"],
    "go": ["run", "build", "test", "mod", "get", "install", "fmt", "vet"],
    "uv": ["run", "add", "remove", "sync", "lock", "tool", "pip", "python"],
    "pnpm": ["install", "add", "remove", "run", "test", "build", "start"],
    "bun": ["run", "install", "add", "remove", "test", "build", "start"],
    "deno": ["run", "test", "compile", "fmt", "lint", "cache", "bundle"],
    "systemctl": ["start", "stop", "restart", "status", "enable", "disable", "daemon-reload"],
    "service": ["start", "stop", "restart", "status"],
    "apt": ["install", "remove", "update", "upgrade", "autoremove", "search"],
    "yum": ["install", "remove", "update", "search", "list"],
    "pacman": ["-S", "-R", "-Rns", "-U", "-Sy", "-Syu", "-Ss", "-Qs"],
    "mkfs": [],  # mkfs has no subcommands, but needs to be recognized
    "mkfs.ext4": [],  # Common mkfs variant
}


def parse_command(command_string):
    stripped = command_string.strip()
    if not stripped:
        return {"program": None, "subcommand": None, "flags": [], "arguments": []}

    segments = PIPE_PATTERN.split(stripped)
    commands = []
    current = ""
    for segment in segments:
        if segment in ("|", "&&", ";", "||"):
            commands.append(("pipe" if segment == "|" else "operator", segment))
        else:
            if current:
                commands.append(("command", _parse_single(current.strip())))
                current = ""
            current = segment.strip()

    if current:
        commands.append(("command", _parse_single(current.strip())))

    if len(commands) == 1 and commands[0][0] == "command":
        return commands[0][1]

    return {
        "pipeline": True,
        "segments": commands,
    }


def _parse_single(command):
    if not command or not command.strip():
        return {"program": None, "subcommand": None, "flags": [], "arguments": []}

    try:
        tokens = shlex.split(command)
    except ValueError as e:
        return {
            "program": None,
            "subcommand": None,
            "flags": [],
            "arguments": [command],
            "error": str(e),
        }

    if not tokens:
        return {"program": None, "subcommand": None, "flags": [], "arguments": []}

    program = tokens[0]
    flags = []
    arguments = []
    subcommand = None

    known_subcommands = SUPPORTED_SUBCOMMANDS.get(program, [])
    i = 1
    while i < len(tokens):
        token = tokens[i]
        if token.startswith("-"):
            if "=" in token:
                flag, _, value = token.partition("=")
                flags.append({"flag": flag, "value": value})
            else:
                flags.append({"flag": token, "value": None})
                if i + 1 < len(tokens) and not tokens[i + 1].startswith("-"):
                    if any(p in program for p in ("find", "grep", "sed", "awk")):
                        flags[-1] = {"flag": token, "value": tokens[i + 1]}
                        i += 1
        else:
            if subcommand is None and known_subcommands:
                if token in known_subcommands:
                    subcommand = token
                else:
                    arguments.append(token)
            else:
                arguments.append(token)
        i += 1

    return {
        "program": program,
        "subcommand": subcommand,
        "flags": flags,
        "arguments": arguments,
    }
