# ShellMate

Intelligent shell autocomplete with consequence preview.

**Version:** 3.0.0  
**Package:** [`shellmate-cli`](https://pypi.org/project/shellmate-cli/)  
**License:** MIT  
**Python:** 3.10+

ShellMate watches what you type and shows **inline risk annotations** before you press Enter. A background daemon analyzes commands with deterministic rules, an exact-match cache, and a LangGraph pipeline that pulls project context plus Groq / OpenRouter / Grok (xAI) for AI risk and remediation.

## How it works

```
You type in the shell
    → ble.sh (Linux/WSL) or PSReadLine (Windows) adapter
    → IPC to daemon (TCP 127.0.0.1:9823)
    → LangGraph analysis pipeline
    → Inline annotation / confirmation gate
```

1. **Instant catastrophic check** — local YAML rules (`rules/catastrophic.yaml`), no API.
2. **Debounced partial analysis** — after a short pause while typing.
3. **Full analysis** — rules → cache → AI + context agents when risk is unclear.

## Installation

### From PyPI

```bash
pip install shellmate-cli
```

### From source

```bash
git clone https://github.com/sayan-does/shellmate.git
cd shellmate
pip install -e .
```

## Quick start

### 1. Prerequisites

| Platform | Required |
|----------|----------|
| Linux / WSL | [ble.sh](https://github.com/akinomyoga/ble.sh) (e.g. under `~/.local/share/blesh/ble.sh`) |
| Windows | PowerShell with PSReadLine |
| All | At least one of `GROQ_API_KEY`, `OPENROUTER_API_KEY`, or `XAI_API_KEY` |

### 2. Install hooks and configure keys

```bash
sm install          # copy adapter → ~/.shellmate/adapters/ and append RC/profile hook
sm config           # select provider (Groq / OpenRouter / Grok xAI), paste API key
```

Dry-run without changing files:

```bash
sm install --dry-run
```

### 3. Start the daemon

```bash
sm enable
```

Starts the daemon for the current directory (Watcher, Librarian, and other agents). Check with `sm status`.

### 4. Type normally

Inline annotations appear under the line as you type. Catastrophic commands require a second Enter to confirm.

### 5. Stop / remove

```bash
sm disable          # stop daemon
sm uninstall        # remove shell hooks (keeps config)
```

## Autocomplete features

ShellMate’s main UX is **in-shell autocomplete annotations** (not a separate `sm -a` command). Adapters hook ble.sh or PSReadLine and talk to the daemon over IPC.

### Two-phase typing feedback

| Phase | Latency | What happens |
|-------|---------|--------------|
| **1 — Instant** | &lt;10ms, no API | `/instant-check` against `rules/catastrophic.yaml`. Blocking commands get an immediate annotation. |
| **2 — Debounced** | ~300ms after you pause | `/analyze-partial` runs the analysis pipeline and **replaces** the annotation in place with risk + badges. |

```bash
$ git push --force
[!] rewrites history [PROD] BH

$ rm -rf /
[!] BLOCKING - Type again to confirm
```

### Consequence preview (Tab × 2)

1. **First Tab** — completion / ghost-text suggestion  
2. **Second Tab** — accept suggestion and show a **consequence preview** below the prompt:

```text
  → Force-pushes and rewrites remote history
  → Reversible: No  |  remote: origin/main
  → Safe alt: git push --force-with-lease
```

On HIGH / CRITICAL / blocking severity, Enter is gated until you confirm again.

| Platform | Completion surface |
|----------|-------------------|
| Linux / WSL (ble.sh) | Tab bound to ShellMate complete widget |
| PowerShell 7.2+ | PSReadLine predictor (`powershell_predictor.ps1`) when available |
| PowerShell 5.1 | Tab handler ghost-text fallback |

### Double-Enter confirmation

Dangerous commands do not run on the first Enter:

1. First Enter → blocked; annotation asks you to confirm  
2. Second Enter (same command) → allowed  

Applies to catastrophic instant matches and to HIGH/CRITICAL consequence previews.

### Annotation badges

Short inline text under the command (ASCII-safe on all platforms):

| Kind | Examples |
|------|----------|
| Risk | `[OK]` `[i]` `[!]` `[!!]` `[X]` |
| Environment | `[PROD]` `[STAGE]` `[DEV]` `[CI]` |
| Time | `BH` (business hours) · `AH` (after hours) |
| Chain / consequence | `[BROKEN]` `[ESCALATION]` `[IRREVERSIBLE]` |

### Bracket syntax

Typed as part of the command line; adapters/daemon strip and honor them:

| Syntax | Purpose | Example |
|--------|---------|---------|
| `[?…]` | Ask a question about the command | `docker rm $(docker ps -aq) [?why dangerous]` |
| `[!…]` | Directive to the analyzer | `rm -rf /tmp [!force]` |
| `[@key=value]` | Override context (e.g. environment) | `git reset --hard [@env=production]` |

### Surfaces

| Adapter | Shell | Role |
|---------|-------|------|
| `ble_adapter.sh` | bash/zsh + ble.sh | Primary Linux/WSL autocomplete |
| `powershell_adapter.ps1` | PowerShell + PSReadLine | Primary Windows autocomplete |
| `powershell_predictor.ps1` | PowerShell 7.2+ | Optional ghost-text predictor |
| `bash_adapter.sh` / `zsh_adapter.zsh` | — | Deprecated stubs |

Requires at least one of `GROQ_API_KEY`, `OPENROUTER_API_KEY`, or `XAI_API_KEY` for AI annotations and consequence previews. Instant catastrophic checks still use local rules.

## CLI

| Command | Description |
|---------|-------------|
| `sm install` | Install shell hooks (bash/zsh → ble adapter, PowerShell → PS adapter) |
| `sm uninstall` | Remove shell hooks |
| `sm config` | Configure API keys and settings |
| `sm enable` | Start daemon (autocomplete mode) |
| `sm disable` | Stop daemon and clean session |
| `sm status` | Daemon, agents, providers, credentials |
| `sm --help` | Help |
| `sm --version` | Version |
| `sm --no-color <cmd>` | Plain text output |

### `sm config` usages

```bash
sm config                        # validate existing keys; select provider → paste key
sm config --show                 # masked credentials
sm config provider risk_analysis xai grok-3-mini   # set provider role
sm config cache.max_entries 200  # YAML override (dotted key)
```

Interactive setup asks you to pick Groq, OpenRouter, or Grok (xAI), then paste the key. Existing keys are checked against the provider API.
### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 2 | Usage error |
| 3 | Temporary error (e.g. interrupt) |
| 4 | Internal error |

## Shell adapters

See [Autocomplete features](#autocomplete-features) for behavior. `sm install` copies the ble or PowerShell adapter into `~/.shellmate/adapters/` and appends a source line to your RC / profile.

## Architecture

### Analysis pipeline

Defined in `shellmate/orchestration/analysis_graph.py` (LangGraph `StateGraph`):

```mermaid
flowchart TD
    START([start]) --> sanitize --> parse --> command_chain --> rules --> cache
    cache -->|early exit| format
    cache -->|needs AI| supervisor
    supervisor -->|gather context| context_worker
    supervisor -->|env only| env_context
    context_worker --> risk_analyzer
    env_context --> risk_analyzer
    risk_analyzer --> consequence_builder --> remediation --> command_guide --> format
    format --> query
    query --> END([end])
```

| Node | Role |
|------|------|
| `sanitize` / `parse` | Typo / syntax checks; tokenize |
| `command_chain` | Multi-step / chain pattern detection |
| `rules` | YAML rules under `shellmate/rules/definitions/` |
| `cache` | Exact-match in-memory cache (no FAISS) |
| `supervisor` | Groq (or heuristic) decides context needs |
| `context_worker` / `env_context` | Parallel agent queries or env-only path |
| `risk_analyzer` | Groq risk assessment |
| `consequence_builder` | Structured consequence preview |
| `remediation` | OpenRouter safer alternatives |
| `command_guide` | Groq “what you meant” guide |
| `format` / `query` | Final payload; optional `[?…]` query handling |

**Early exits** (skip AI): sanitizer correction, high-confidence rule match, cache hit.

### Agents (daemon)

Started with `sm enable`:

| Agent | Purpose |
|-------|---------|
| Watcher | OS, shell, git, tech-stack snapshot |
| Librarian | Project file index + search |
| Environment | Environment / staging signals |
| CommandChain | Chain-pattern analysis |
| Query | Answers `[?…]` queries |

Repomix-style pack search runs alongside Librarian in the context worker when needed.

### Providers

| Stage | Default | Fallback |
|-------|---------|----------|
| Supervisor / risk / guide | Groq | Grok (xAI) / heuristic |
| Remediation | OpenRouter | Grok (xAI) / Groq guide / generic text |

Configure **at least one** of Groq, OpenRouter, or Grok (xAI). Groq covers risk analysis, supervisor routing, and command guide; OpenRouter covers remediation; xAI can cover both risk and remediation. Instant catastrophic gating still uses local rules either way.
## Configuration

### Directories

| Purpose | Linux / macOS | Windows |
|---------|---------------|---------|
| Config + `.env` | `~/.config/shellmate` | `%APPDATA%\ShellMate` |
| State / sessions / logs | `~/.local/state/shellmate` | `%LOCALAPPDATA%\ShellMate` |
| Cache dir | `~/.cache/shellmate` | `%LOCALAPPDATA%\ShellMate\cache` |
| Installed adapters | `~/.shellmate/adapters/` | `%USERPROFILE%\.shellmate\adapters\` |

Credentials file: `<config_dir>/.env` (permissions restricted on Unix).

### Environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `GROQ_API_KEY` | At least one of Groq / OpenRouter / xAI | Risk analysis, supervisor, command guide |
| `OPENROUTER_API_KEY` | At least one of Groq / OpenRouter / xAI | Remediation alternatives |
| `XAI_API_KEY` | At least one of Groq / OpenRouter / xAI | Risk analysis and remediation via Grok |
| `CONTEXT7_API_KEY` | No | Optional docs lookup |
| `GROQ_SUPERVISOR_MODEL` | No | Override supervisor model (default `qwen/qwen3.8-27b`) |
| `XAI_MODEL` | No | Override Grok model (default `grok-3-mini`) |

Optional YAML overrides live in `<config_dir>/config.yaml`.

## Requirements

- Python 3.10+
- ble.sh (Linux/WSL) or PowerShell + PSReadLine (Windows)
- At least one of `GROQ_API_KEY`, `OPENROUTER_API_KEY`, or `XAI_API_KEY` (Groq + OpenRouter recommended for full risk + remediation)

### Dependencies (authoritative: `pyproject.toml`)

- `click`, `rich`, `pyyaml` — CLI / UI
- `langgraph`, `langchain-core` — orchestration
- `groq`, `openai`, `aiohttp` — providers
- `psutil`, `watchdog` — runtime monitoring
- `numpy` — declared runtime dependency

## Development

```bash
git clone https://github.com/sayan-does/shellmate.git
cd shellmate
pip install -e ".[dev]"
python -m build
```

CI builds and smoke-tests the wheel on Python 3.10–3.12. Publishing runs on `v*` tags via Trusted Publishing (`.github/workflows/publish.yml`).

## License

MIT
