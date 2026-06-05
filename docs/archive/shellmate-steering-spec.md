# ShellMate

**Intelligent Command Safety Layer for Modern Terminals**

| Field | Value |
|---|---|
| Version | 2.0 MVP Specification |
| Status | Design Approved |
| License Target | MIT |

---

## Table of Contents

1. [Vision](#1-vision)
2. [Core Objectives](#2-core-objectives)
3. [Non-Goals (MVP)](#3-non-goals-mvp)
4. [High-Level Architecture](#4-high-level-architecture)
5. [Terminal Compatibility Layer](#5-terminal-compatibility-layer)
6. [Environment Detection Engine](#6-environment-detection-engine)
7. [IPC Layer](#7-ipc-layer)
8. [ShellMate Daemon](#8-shellmate-daemon)
9. [Sanitizer](#9-sanitizer)
10. [Parser](#10-parser)
11. [Rule Engine](#11-rule-engine)
12. [Semantic Cache](#12-semantic-cache)
13. [Risk Agent](#13-risk-agent)
14. [Documentation Intelligence Layer](#14-documentation-intelligence-layer)
15. [Remediation Agent](#15-remediation-agent)
16. [Provider Routing](#16-provider-routing)
17. [Decision Pipeline](#17-decision-pipeline)
18. [User Experience Levels](#18-user-experience-levels)
19. [CLI Reference](#19-cli-reference)
20. [Plugin System](#20-plugin-system)
21. [Repository Structure](#21-repository-structure)
22. [Observability](#22-observability)
23. [Security Principles](#23-security-principles)
24. [MVP Acceptance Criteria](#24-mvp-acceptance-criteria)

---

## 1. Vision

ShellMate is an open-source terminal safety platform that analyzes commands before execution, helping users avoid destructive actions, syntax mistakes, and misuse of rapidly evolving developer tools.

It operates locally as a lightweight daemon and integrates with multiple terminal environments through shell-specific hooks and adapters. The system prioritizes **deterministic validation**, then rule-based analysis, then documentation retrieval, and only then AI-assisted reasoning.

**Design pillars:**

- Low latency
- Explainability
- Offline capability
- Extensibility
- Open-source contribution

---

## 2. Core Objectives

### Primary Goals

- Detect dangerous commands before execution
- Detect typos and malformed syntax
- Provide safe alternatives
- Support modern developer tooling
- Support multiple terminal environments
- Operate with minimal infrastructure
- Minimize LLM usage through deterministic processing
- Remain fully usable when cloud providers are unavailable

### Secondary Goals

- Learn from previous analyses via semantic cache
- Leverage official documentation for validation
- Support future MCP integrations
- Enable community-maintained rule packs

---

## 3. Non-Goals (MVP)

The MVP will **not** include:

- Command sandboxing or execution virtualization
- GUI application
- Cloud backend
- User telemetry or tracking
- Remote storage
- Automatic command modification

---

## 4. High-Level Architecture

```
User Command
     │
     ▼
Terminal Adapter
     │
     ▼
IPC Client
     │
     ▼
ShellMate Daemon
     │
     ├─► Sanitizer
     │
     ├─► Parser
     │
     ├─► Rule Engine
     │
     ├─► Semantic Cache
     │
     ├─► Risk Agent
     │
     ├─► Documentation Intelligence Layer
     │
     ├─► Remediation Agent
     │
     ▼
Response Formatter
     │
     ▼
Terminal
```

---

## 5. Terminal Compatibility Layer

**Purpose:** Identify the user's execution environment and attach the correct interception mechanism.

| Platform | Supported Shells |
|---|---|
| Linux | Bash, Zsh, Fish |
| macOS | Bash, Zsh |
| Windows | PowerShell, CMD, Git Bash, WSL |

**Planned future support:** Nushell · Warp · WezTerm · Alacritty · Kitty · Ghostty

---

## 6. Environment Detection Engine

**Purpose:** Determine the execution environment at installation time and at runtime.

### Detection Targets

| Dimension | Values |
|---|---|
| Operating System | Linux, Windows, macOS |
| Shell Type | bash, zsh, fish, powershell, cmd |
| Execution Environment | native, wsl, container, ssh |
| Terminal Emulator | Windows Terminal, Warp, WezTerm, Kitty, Ghostty, Alacritty, iTerm2 |

### Output Schema

```json
{
  "os": "linux",
  "shell": "zsh",
  "environment": "native",
  "terminal": "wezterm"
}
```

---

## 7. IPC Layer

**Technology:** Unix Socket (Linux/macOS) · Windows Named Pipe (Windows)

**Responsibilities:**

- Send command requests to the daemon
- Receive structured analysis results
- Handle reconnection and daemon discovery

---

## 8. ShellMate Daemon

**Purpose:** Central orchestration service that owns the full analysis pipeline.

**Responsibilities:**

- Receive and queue incoming requests
- Execute the analysis pipeline
- Manage semantic cache and provider connections
- Route documentation lookups
- Return structured responses to IPC clients

---

## 9. Sanitizer

**Purpose:** Detect simple command mistakes deterministically, without invoking AI.

**Checks performed:**

- Whitespace normalization
- Trailing character detection (e.g., stray commas, semicolons)
- Duplicate flag detection
- Shell syntax validation
- Basic typo detection

**Example:**

```
Input:   git push origin main,
Output:  Did you mean: git push origin main
```

---

## 10. Parser

**Technology:** Python `shlex`

**Purpose:** Convert raw command strings into structured objects for downstream analysis.

**Output Schema:**

```json
{
  "program": "git",
  "subcommand": "push",
  "flags": ["--force"],
  "arguments": ["origin", "main"]
}
```

---

## 11. Rule Engine

**Purpose:** Deterministic risk detection via curated rule sets.

| Category | Matched Patterns |
|---|---|
| File Deletion | `rm -rf`, `shred` |
| Filesystem | `mkfs`, `fdisk` |
| Permissions | `chmod -R 777` |
| Process Control | `kill -9` |
| Network Execution | `curl \| bash`, `wget \| sh` |
| System Destruction | `dd`, fork bombs |

---

## 12. Semantic Cache

**Technology:** FAISS · sentence-transformers (`all-MiniLM-L6-v2`)

**Purpose:** Avoid repeated AI inference for semantically equivalent commands.

**Similarity Threshold:** `0.92`

**Cache Object Schema:**

```json
{
  "command": "rm -rf /tmp/test",
  "risk": "HIGH",
  "confidence": 0.97,
  "explanation": "Recursively deletes /tmp/test without confirmation.",
  "alternatives": ["rm -ri /tmp/test"],
  "timestamp": "2025-06-01T12:00:00Z"
}
```

---

## 13. Risk Agent

**Provider:** Groq

**Purpose:** Classify commands that deterministic systems cannot confidently assess.

**Responsibilities:**

- Risk level classification
- Confidence score estimation
- Short natural-language reasoning

**Output Schema:**

```json
{
  "risk": "HIGH",
  "confidence": 0.91,
  "reason": "Command overwrites the MBR and may render the system unbootable."
}
```

**Constraints:**

- JSON output only
- No remediation or command suggestions (handled by Remediation Agent)

---

## 14. Documentation Intelligence Layer

**Purpose:** Retrieve current, authoritative documentation and command usage guidance. This layer exists because modern developer tooling evolves faster than model training cycles.

### Documentation Sources

| Priority | Source |
|---|---|
| 1 | Official Documentation |
| 2 | Context7 MCP |
| 3 | Future MCP Providers |

### Responsibilities

- Command syntax and flag description retrieval
- Usage examples retrieval
- Migration guidance (version-aware)

### Dynamic Tool Registry

The following tools are subject to documentation lookup by default:

`uv` · `claude` · `opencode` · `aider` · `pnpm` · `bun` · `deno` · `docker` · `kubectl` · `terraform`

### Trigger Conditions

Documentation retrieval is triggered when **any** of the following are true:

- Command is unrecognized
- Risk confidence < `0.75`
- Command belongs to the dynamic tool registry

### Output Schema

```json
{
  "tool": "uv",
  "documentation": ["uv run executes a script in an isolated environment."],
  "examples": ["uv run script.py", "uv run --with requests script.py"]
}
```

---

## 15. Remediation Agent

**Purpose:** Generate safer alternatives that preserve the original user intent.

### Provider Chain

| Priority | Provider |
|---|---|
| Primary | OpenRouter GPT-OSS-120B |
| Fallback 1 | Nemotron |
| Fallback 2 | Laguna |
| Fallback 3 | Local (Ollama) |

### Responsibilities

- Explain the identified risk in plain language
- Generate up to 3 safer alternatives
- Recommend safer flags or workflows

### Output Schema

```json
{
  "explanation": "This command will recursively delete files without a recovery option.",
  "alternatives": [
    "rm -ri /path/to/dir",
    "trash /path/to/dir",
    "mv /path/to/dir ~/.Trash/"
  ]
}
```

**Constraints:**

- Maximum 3 alternatives
- Must never alter the user's original intent

---

## 16. Provider Routing

```
Risk Analysis
─────────────
Groq ──► Local Fallback (Ollama)

Remediation
───────────
OpenRouter GPT-OSS-120B
    │
    ▼
Nemotron
    │
    ▼
Laguna
    │
    ▼
Local (Ollama)
```

### Local Fallback

| Field | Value |
|---|---|
| Runtime | Ollama |
| Model | `qwen2.5:3b` |
| Use Cases | Offline operation · Provider outage · Rate limit recovery |

---

## 17. Decision Pipeline

```
1.  Receive command
2.  Detect environment
3.  Run sanitizer
4.  If typo detected → return correction (stop)
5.  Parse command
6.  Execute rule engine
7.  If rule match → return result (stop)
8.  Check semantic cache
9.  If cache hit → return cached result (stop)
10. Execute risk agent
11. Evaluate confidence score
12. If documentation required → retrieve documentation
13. Execute remediation agent
14. Format response
15. Return response to terminal
```

---

## 18. User Experience Levels

| Level | Behavior |
|---|---|
| **SAFE** | No interruption |
| **LOW** | Informational notice |
| **MEDIUM** | Warning displayed |
| **HIGH** | Prominent warning |
| **CRITICAL** | Explicit confirmation required before execution |

---

## 19. CLI Reference

```bash
shellmate install          # Install ShellMate and shell hooks
shellmate uninstall        # Remove ShellMate and all hooks
shellmate enable           # Enable command interception
shellmate disable          # Disable command interception
shellmate status           # Show daemon and provider status
shellmate doctor           # Run environment diagnostics
shellmate config           # View or edit configuration
shellmate logs             # Tail daemon logs
shellmate cache clear      # Clear the semantic cache
shellmate providers        # List configured AI providers
shellmate update-rules     # Fetch latest community rule packs
```

---

## 20. Plugin System

ShellMate exposes four extension points for community contributions:

| Extension Point | Description |
|---|---|
| **Rule Plugins** | Custom rule packs for additional risk patterns |
| **Documentation Providers** | Additional MCP integrations and doc sources |
| **AI Providers** | Additional LLM backends |
| **Terminal Adapters** | Support for additional shells and environments |

---

## 21. Repository Structure

```
shellmate/
├── cli/                # CLI entry points and commands
├── daemon/             # Core daemon and orchestration
├── ipc/                # Unix socket / named pipe layer
├── adapters/           # Shell-specific hooks and adapters
├── environment/        # Environment detection engine
├── sanitizer/          # Typo and syntax checks
├── parser/             # Command parser (shlex-based)
├── rules/              # Built-in and community rule packs
├── cache/              # FAISS semantic cache
├── agents/             # Risk Agent and Remediation Agent
├── providers/          # AI provider clients and routing
├── documentation/      # Documentation Intelligence Layer
├── plugins/            # Plugin interfaces and loader
├── config/             # Configuration schemas and defaults
├── tests/              # Unit, integration, and E2E tests
└── docs/               # User and developer documentation
```

---

## 22. Observability

### Log Levels

`DEBUG` · `INFO` · `WARNING` · `ERROR`

### Tracked Events

| Event | Description |
|---|---|
| `environment.detected` | OS, shell, and terminal identified |
| `rule.match` | A deterministic rule was triggered |
| `cache.hit` | Result served from semantic cache |
| `cache.miss` | No cache match; proceeding to AI |
| `provider.request` | AI provider call initiated |
| `provider.failure` | AI provider call failed; fallback triggered |
| `documentation.retrieved` | Official docs fetched successfully |
| `mcp.retrieved` | MCP documentation fetched |
| `daemon.lifecycle` | Daemon start, stop, or restart event |

---

## 23. Security Principles

- **No AI execution** — AI agents never execute commands directly
- **No auto-modification** — ShellMate never silently modifies a user's command
- **No telemetry** — No usage data is collected or transmitted
- **No history upload** — Command history never leaves the local machine
- **No user data collection** — Zero PII collection of any kind
- **Local-first** — All analysis remains local except explicitly configured provider API calls

---

## 24. MVP Acceptance Criteria

A release is considered MVP-complete when all of the following pass:

- [ ] Environment detection works correctly across Linux, macOS, and Windows
- [ ] Bash hook support works end-to-end
- [ ] PowerShell hook support works end-to-end
- [ ] WSL support works end-to-end
- [ ] Daemon architecture initializes, receives, and responds correctly
- [ ] Sanitizer detects common typos and malformed commands
- [ ] Parser generates valid structured command objects
- [ ] Rule engine detects all built-in dangerous command patterns
- [ ] FAISS semantic cache stores, retrieves, and expires results correctly
- [ ] Groq risk analysis returns valid JSON within latency targets
- [ ] OpenRouter remediation returns valid alternatives
- [ ] Ollama local fallback activates correctly on provider failure
- [ ] Context7 documentation retrieval returns accurate results
- [ ] `pip install shellmate` completes without errors
- [ ] `shellmate enable` installs shell hooks automatically
- [ ] Full end-to-end command analysis works across Linux, macOS, Windows, and WSL
