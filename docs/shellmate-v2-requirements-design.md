# ShellMate v2.0 MVP - Requirements & Design

**Status:** MVP design source of truth
**Version target:** 2.0.0
**Last updated:** 2026-06-06

This document is the single requirements and design plan for the ShellMate v2.0 MVP. The companion implementation checklist is `docs/v2-implementation-tasks.md`.

---

## 1. MVP Goal

ShellMate v2.0 upgrades the current command-safety flow into a daemon-backed, context-aware command analysis system.

The MVP must deliver:

- A simpler CLI: `sm -a <command>`.
- A single-user background daemon for command analysis.
- Project context from two agents: Watcher and Librarian.
- Rich terminal output for startup, status, errors, and analysis results.
- Cross-platform behavior on Windows, Linux, and macOS.
- Graceful degradation when agents, providers, file watching, or git detection fail.

---

## 2. MVP Scope

### In Scope

- `sm -a <command>` command analysis.
- `sm enable`, `sm disable`, `sm status`, and `sm config`.
- Single active daemon/session per user.
- Session-local file index rebuilt on `sm enable` and deleted on `sm disable`.
- Watcher agent for environment, tech stack, and git snapshot detection.
- Librarian agent for vectorless file/path search using an in-memory index.
- `/status`, `analyze`, `shutdown`, `health`, and `/context-gatherer` IPC handlers.
- Existing provider support with context-aware prompts and deterministic fallback when providers fail.
- Shell adapter updates for bash, zsh, and PowerShell.
- Unit and integration tests for parser, daemon lifecycle, agents, context gathering, provider fallback, and shell adapter smoke behavior.

### Out Of Scope For MVP

- Backward-compatible v1 CLI support.
- Multi-session or multi-directory daemon support.
- Persistent RAG index across enable/disable cycles.
- Embeddings, semantic search, fuzzy search, or ML-based RAG.
- User plugin system or dynamic third-party agent loading.
- `/deep-research`, `sm research`, `sm providers`, and `sm doctor`.
- Full Prometheus metrics endpoint. Basic structured logs are in scope.
- Persistent dashboard or full TUI app.

---

## 3. Constraints And Decisions

- Runtime: Python 3.8+ with asyncio.
- OS support: Windows, Linux, macOS.
- Shell support: bash, zsh, PowerShell. cmd/fish support is desirable but not required for MVP unless already supported by existing adapters.
- Daemon model: one daemon per user, one active project directory at a time.
- IPC model: local-only JSON IPC. MVP may use TCP on `127.0.0.1` with same-user/session validation. Unix sockets/named pipes may be added later if the implementation already supports them cleanly.
- Agent timeout: the total context-gathering phase has a hard user-facing cutoff of 500ms. No retry is allowed inside this 500ms budget.
- RAG model: vectorless keyword/path search only.
- Index lifetime: session-only. Delete the index on clean shutdown.
- File watching: use watchdog when available. If watching fails, keep the startup index and warn that live updates are disabled.

---

## 4. Functional Requirements

### FR-1: CLI

- `sm -a <command>` treats everything after `-a` as the command to analyze.
- Commands with flags, quotes, pipes, redirects, and shell-special tokens must preserve user intent as far as argv allows.
- `sm enable` starts the daemon for the current directory.
- `sm disable` gracefully stops the daemon and removes session files.
- `sm status` shows daemon, agent, provider, and session state.
- `sm config` configures provider credentials/settings without printing secrets.
- Invalid CLI usage must show a concise suggestion and exit with a usage code when run as a normal CLI process.
- Shell hooks may choose to return control to the prompt after displaying the same error.

### FR-2: Daemon Lifecycle

- `sm enable` validates stale sessions before starting a new daemon.
- The daemon must bind IPC/status before long-running agent startup so the CLI can poll startup progress.
- The daemon writes session metadata atomically only after IPC is ready.
- The CLI polls `/status` for startup progress and never reads in-memory daemon queues.
- `sm disable` sends a shutdown request, waits briefly for graceful shutdown, then reports failure if the daemon does not stop.
- Stale PID/session files must be cleaned up only after process ownership and liveness checks.

### FR-3: Session Management

- Store session data under the platform-appropriate ShellMate state directory.
- Session metadata includes PID, project directory, created time, IPC address, and owner identity when available.
- Unix session directories use restrictive permissions (`700` for directories, `600` for sensitive files). Windows must use the best available user-only equivalent.
- Clean shutdown removes temporary session data, including the index and environment cache.
- Logs may remain outside the session directory for diagnostics and must be rotated.

### FR-4: Watcher Agent

- Detect OS, shell, terminal if available, environment type, and whether execution appears to be WSL/container/SSH/native.
- Detect root-level tech stack indicators such as `package.json`, `pyproject.toml`, `requirements.txt`, `Cargo.toml`, `go.mod`, `Gemfile`, `composer.json`, `Dockerfile`, `docker-compose.yml`, `Makefile`, `vite.config.*`, and `tsconfig.json`.
- Detect git context when git is installed and the directory is a repository.
- Git context includes branch or detached HEAD, staged/unstaged change counts, last commit hash/message when available, and repository root.
- Detection runs at startup and is cached in memory.
- Agent requests return cached context only; they must not perform slow detection in the request path.
- Missing git, non-git directories, empty repos, detached HEAD, and subprocess errors must degrade gracefully.

### FR-5: Librarian Agent

- Recursively index known code, config, shell, build, and docs files from the active project directory.
- Respect obvious ignore boundaries such as `.git`, virtualenvs, dependency directories, build output, and binary files.
- Maintain an in-memory index for search. `index.md` is only a debugging/session artifact, not the search backend.
- Use token/path keyword search with deterministic ranking.
- Return at most 10 matches per request with path, match type, metadata, and sanitized snippet when available.
- Watchdog callbacks must not mutate the index directly from a watcher thread. They must enqueue events for an async consumer or use equivalent serialization.
- For large projects, index up to 5,000 eligible files for MVP, warn clearly, and continue with partial coverage.

### FR-6: Context Gathering

- Context gathering is implemented as a daemon helper used by the pipeline and exposed through `/context-gatherer` for diagnostics/external callers.
- The pipeline should call the in-process helper directly, not loop back through IPC while already inside the daemon.
- Context gathering chooses relevant agents based on command tokens, file references, and known command categories.
- Watcher and Librarian requests run concurrently.
- The total context gathering phase must return within 500ms.
- Responses include context data, `timed_out`, `errors`, `partial`, and per-agent latency fields.
- Timeouts, failed agents, and malformed agent responses must not block command analysis.

### FR-7: Pipeline And Providers

- Pipeline stages: sanitize, parse, rules, cache lookup, context gathering, provider analysis, postprocess, response formatting.
- Preserve early exits for cache hits, sanitizer-corrected commands, and high-confidence deterministic rules.
- Provider prompts include sanitized command, relevant environment context, relevant file context, and git context when available.
- Provider inputs must redact secrets and high-risk PII before network calls.
- Provider failure must fall back to deterministic rule-based output.
- No tests may require real provider API keys.

### FR-8: UI/UX

- Use Rich for formatted terminal output.
- Startup progress shows daemon binding, agent startup, indexing progress, provider config status, and ready/error state.
- Status output includes daemon PID/directory/uptime, agent readiness/file count, provider configuration, and last health check.
- Analysis output includes risk level, explanation, alternatives/remediation, context used, and latency breakdown.
- Error output includes clear next steps.
- Provide plain-text-safe fallbacks for terminals without color/truecolor support.

### FR-9: Shell Adapters

- Bash, zsh, and PowerShell adapters must call `sm -a <command>` without breaking normal shell behavior.
- Adapter install/uninstall must respect user consent and support a dry-run if currently available or easy to add.
- Adapter tests must cover quoting, commands with flags, and disabled-daemon behavior.

---

## 5. Non-Functional Requirements

### Performance

- Startup for typical projects under 1,000 eligible files: target < 10s.
- Startup for larger projects: warn and remain usable with partial index.
- Context gathering: hard cutoff 500ms total.
- Watcher context request: typical < 20ms from cache.
- Librarian search request: typical < 100ms from in-memory index.
- AI-backed analysis: target < 6s total, excluding provider outages.

### Reliability

- Agent exceptions must not crash the daemon.
- IPC handlers must use read/write timeouts and input size limits.
- Shutdown must cancel agent tasks and stop watchdog observers.
- Stale sessions must be cleaned deterministically.
- File permission errors during indexing must skip files and continue.

### Security

- IPC binds only locally and validates the active session/owner where possible.
- IPC rejects malformed payloads and oversized requests.
- Librarian must not read outside the active project root.
- File snippets and prompts must redact secrets, long tokens, SSH keys, email addresses, and provider keys.
- API keys must never appear in logs, stack traces, prompt snapshots, or UI output.
- Logs must be structured enough for debugging and rotated to a bounded size.

---

## 6. Architecture

```text
User CLI / shell adapter
        |
        | local JSON IPC
        v
ShellMate daemon
  - IPC server and request router
  - startup status model
  - command pipeline
  - provider router
  - context gatherer helper
        |
        +--> Watcher agent: cached environment, tech stack, git snapshot
        |
        +--> Librarian agent: in-memory file index, watchdog event queue
        |
        +--> Session manager: session metadata, cleanup, logs pointer
```

### Startup Flow

1. CLI receives `sm enable`.
2. CLI checks and cleans stale session metadata.
3. CLI starts daemon process.
4. Daemon binds local IPC and initializes startup status.
5. Daemon writes session metadata atomically.
6. CLI polls `/status`.
7. Daemon starts Watcher and Librarian agents.
8. Agents update startup status as they initialize.
9. CLI displays progress until ready or timeout.

### Analysis Flow

1. CLI receives `sm -a <command>`.
2. CLI sends `analyze` request to daemon.
3. Daemon pipeline sanitizes/parses/checks rules/cache.
4. Pipeline calls in-process context gatherer helper when context may be useful.
5. Context gatherer queries relevant agents concurrently within 500ms.
6. Pipeline calls provider or deterministic fallback.
7. Daemon returns structured result.
8. CLI renders Rich output.

### Shutdown Flow

1. CLI sends `shutdown` request.
2. Daemon stops accepting new analysis work.
3. Daemon cancels agent tasks and stops watchdog observer.
4. Daemon closes IPC server.
5. Daemon removes session data.
6. CLI reports disabled state.

---

## 7. Data Contracts

### Analyze Request

```json
{
  "type": "analyze",
  "request_id": "uuid",
  "command": "rm -rf ./build",
  "cwd": "/path/to/project"
}
```

### Context Gatherer Response

```json
{
  "request_id": "uuid",
  "watcher": {},
  "librarian": {"matches": []},
  "timed_out": [],
  "errors": {},
  "partial": false,
  "latency_ms": 42,
  "agent_latency_ms": {"watcher": 5, "librarian": 34}
}
```

### Analysis Response

```json
{
  "request_id": "uuid",
  "risk": "SAFE|LOW|MEDIUM|HIGH|CRITICAL",
  "confidence": 0.0,
  "message": "summary",
  "explanation": "details",
  "alternatives": [],
  "context_used": {"watcher": false, "librarian": false},
  "latency_ms": 0,
  "stage_latency_ms": {}
}
```

---

## 8. Acceptance Criteria

- `sm enable` starts a daemon, creates a session, shows progress via `/status`, and reaches ready state.
- `sm -a echo hi` returns a SAFE/LOW result without requiring quotes.
- `sm -a git status` includes git context when run in a git repo.
- `sm -a rm ./some-file` queries Librarian when the file is inside the active project.
- Agent context gathering returns within 500ms and marks slow agents as timed out.
- Provider outage still returns a deterministic safety result.
- `sm disable` stops the daemon and removes session-local files.
- Invalid CLI input prints a suggestion and uses the documented usage exit code.
- Bash, zsh, and PowerShell adapter smoke tests pass.
- Unit and integration tests run without real provider credentials.

---

## 9. Post-MVP Parking Lot

- Persistent index with smart invalidation.
- Multi-session/multi-directory daemon support.
- Plugin API for third-party agents/providers.
- `/deep-research` background endpoint and `sm research`.
- Fuzzy search, semantic search, or embeddings.
- `sm doctor`, richer metrics endpoint, and Prometheus export.
- IDE integrations and collaboration features.
