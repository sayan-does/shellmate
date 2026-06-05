# ShellMate v2.0

Intelligent Command Safety Layer for Modern Terminals.

## Documentation

- **Requirements & Design**: [docs/shellmate-v2-requirements-design.md](docs/shellmate-v2-requirements-design.md)
- **Implementation Tasks**: [docs/v2-implementation-tasks.md](docs/v2-implementation-tasks.md)

## Installation

```bash
pip install shellmate
```

## Quick Start (v2 CLI)

```bash
# Enable the daemon for current directory
sm enable

# Analyze a command (no quotes needed)
sm -a rm -rf /

# Check daemon status
sm status

# Configure providers
sm config

# Disable daemon
sm disable
```

## Features (v2 MVP Scope)

- **Simple CLI**: `sm -a <command>` analyzes commands without quotes
- **Daemon-backed**: Single-user background daemon for command analysis
- **Context-aware**: Watcher (environment, tech stack, git) + Librarian (file index) agents
- **Rich terminal output**: Startup progress, status, errors, analysis results
- **Cross-platform**: Windows, Linux, macOS
- **Graceful degradation**: Works when agents, providers, file watching, or git detection fail
- **Shell adapters**: Bash, zsh, PowerShell hooks calling `sm -a <command>`
- **Deterministic fallback**: Provider outages fall back to rule-based output

## Requirements

- Python 3.8+
- Groq API key (for AI risk analysis)
- OpenRouter API key (for AI remediation)

## License

MIT
