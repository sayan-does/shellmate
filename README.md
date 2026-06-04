# ShellMate

Intelligent Command Safety Layer for Modern Terminals.

## Installation

```bash
pip install shellmate
```

## Quick Start

```bash
# Install shell hooks
shellmate install

# Enable the daemon
shellmate enable

# Analyze a command
shellmate analyze "rm -rf /"

# Check status
shellmate status

# Run diagnostics
shellmate doctor
```

## Features

- **Environment Detection** - Detects OS, shell, terminal, and execution environment
- **Sanitizer** - Catches typos, trailing characters, duplicate flags, syntax errors
- **Parser** - Parses commands into structured objects for analysis
- **Rule Engine** - 30+ built-in rules detecting dangerous command patterns
- **Semantic Cache** - FAISS-powered cache for fast repeated analysis
- **AI Risk Analysis** - Groq-powered risk classification
- **AI Remediation** - OpenRouter-powered safer alternatives
- **Documentation Intelligence** - Context7-powered documentation lookup
- **Terminal Adapters** - Bash, Zsh, and PowerShell hooks
- **Plugin System** - Extensible plugin architecture

## Requirements

- Python 3.10+
- Groq API key (for risk analysis)
- OpenRouter API key (for remediation)

## License

MIT
