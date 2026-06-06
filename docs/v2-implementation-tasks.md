# ShellMate v2.0 MVP - Implementation Tasks

This is the single task checklist for the v2.0 MVP. Requirements and design live in `docs/shellmate-v2-requirements-design.md`.

Priority key: P0 = required for MVP, P1 = important polish, P2 = explicitly post-MVP.

**Reference format:** Each task references relevant sections in the requirements/design doc:
- `FR-X` = Functional Requirement (section 4)
- `NFR-X` = Non-Functional Requirement (section 5)
- `Arch` = Architecture (section 6)
- `AC-X` = Acceptance Criteria (section 8)

---

## Phase 0 - Repo And Scope Cleanup (P0)

*Refs: Arch (Architecture overview), AC (Acceptance Criteria - single source of truth)*

- [x] Treat `docs/shellmate-v2-requirements-design.md` as the single MVP requirements/design source.
- [x] Treat this file as the single v2 task checklist.
- [x] Remove or archive duplicate v2 spec/checklist docs.
- [x] Update README/doc references to point only to these two files where needed.
- [x] Audit existing modules before adding new ones so implementation does not duplicate current `cli/`, `daemon/`, `providers/`, `ipc/`, `environment/`, or `adapters/` code.

## Phase 1 - CLI Parser And Commands (P0)

*Refs: FR-1 (CLI), Arch (Startup/Analysis flow), AC-1, AC-7, AC-8*

- [x] Implement or refactor `cli/parser.py` with `ShellMateCommandParser`.
- [x] Preserve all tokens after `-a` as the command under analysis.
- [x] Handle empty args, missing command after `-a`, old `analyze "cmd"` usage, and unknown subcommands.
- [x] Return a typed parsed-command model containing action, raw command, tokens/args, and suggestion/error metadata.
- [x] Refactor `cli/main.py` so `-a` uses raw argv parsing and Click does not consume the analyzed command.
- [x] Implement `sm enable`, `sm disable`, `sm status`, and `sm config` command routes.
- [x] Define CLI exit codes: `0` success, `2` usage, `3` temporary daemon/provider error, `4` internal error.
- [x] Render invalid usage with Rich error panels and actionable suggestions.
- [x] Add parser and CLI tests for quotes, flags, pipes, redirects, empty input, and shell-special tokens.

## Phase 2 - Configuration And Secrets (P0)

*Refs: FR-1 (CLI - sm config), FR-3 (Session Management - platform paths), FR-7 (Pipeline - secret redaction), NFR-Security (secret handling), AC-6*

- [ ] Define platform-specific config/state locations using XDG-style paths on Unix and AppData-style paths on Windows.
- [ ] Implement minimal config loader and validator.
- [ ] Implement `sm config` flow for provider selection and API key setup.
- [ ] Store secrets with restrictive file permissions or environment-backed fallback.
- [ ] Ensure secrets are never printed, logged, or included in prompt snapshots.
- [ ] Add tests for missing config, malformed config, missing API keys, and secret redaction.

## Phase 3 - Session Manager And Daemon Lifecycle (P0)

*Refs: FR-2 (Daemon Lifecycle), FR-3 (Session Management), Arch (Startup/Shutdown flow), NFR-Reliability (stale cleanup, graceful shutdown), AC-1, AC-7*

- [x] Implement `daemon/session.py` session creation, lookup, stale cleanup, and removal.
- [x] Write `session.json` atomically with PID, cwd, created time, owner, and IPC address.
- [x] Validate process liveness cross-platform with `psutil` or safe OS fallback.
- [x] Enforce restrictive session permissions on Unix and best-effort user-only permissions on Windows.
- [x] Implement daemon process start/stop in `daemon/lifecycle.py` or existing lifecycle code.
- [x] Bind local IPC before long-running agent startup.
- [x] Write session metadata only after IPC is ready.
- [x] Implement graceful shutdown with timeout and clear failure reporting.
- [x] Add lifecycle tests for enable, disable, stale session cleanup, startup timeout, and port/socket collision.

## Phase 4 - IPC Server And Client (P0)

*Refs: FR-2 (Daemon Lifecycle - IPC binding), FR-6 (Context Gathering - /context-gatherer), FR-7 (Pipeline - analyze handler), Arch (IPC architecture), NFR-Security (local binding, payload validation), NFR-Reliability (timeouts, size limits), Data Contracts (section 7)*

- [ ] Implement local-only JSON IPC server in `daemon/server.py`.
- [ ] MVP transport may be TCP bound to `127.0.0.1`; validate active session/owner where possible.
- [ ] Add request size limits, read/write timeouts, and malformed-payload handling.
- [ ] Required handlers: `analyze`, `/status`, `/context-gatherer`, `shutdown`, and `health`.
- [ ] Implement `ipc/client.py` helpers for status, analyze, shutdown, health, and context-gatherer diagnostics.
- [ ] Include request IDs and structured errors in responses.
- [ ] Add IPC tests for connection failure, invalid payloads, timeout behavior, and concurrent clients.

## Phase 5 - Startup Status And Rich Startup UI (P0)

*Refs: FR-2 (Daemon Lifecycle - CLI polls /status), FR-8 (UI/UX - startup progress), Arch (Startup flow), AC-1*

- [ ] Implement `daemon/startup_status.py` or equivalent shared daemon status model.
- [ ] Track stages: binding IPC, watcher starting/ready, librarian scanning/ready, providers checked, ready, failed.
- [ ] Agents update daemon startup status; CLI polls `/status` only.
- [ ] Implement `ui/display.py` startup progress using Rich.
- [ ] Handle daemon-not-ready connection errors during polling.
- [ ] Timeout startup UI with a clear diagnostic path.
- [ ] Add tests for status transitions and startup polling behavior.

## Phase 6 - Agent Framework (P0)

*Refs: FR-4 (Watcher Agent), FR-5 (Librarian Agent), Arch (Agent architecture), NFR-Reliability (agent exceptions must not crash daemon)*

- [ ] Implement `agents/base.py` with `Agent`, `AgentRequest`, and `AgentResponse` models.
- [ ] Implement per-agent request queues and per-request response queues.
- [ ] Clean up response queues on timeout, error, and disconnect.
- [ ] Add structured logs with request IDs and agent names.
- [ ] Do not implement plugin/dynamic third-party loading for MVP.
- [ ] Add unit tests for request/response routing, timeouts, cancellation, and cleanup.

## Phase 7 - Watcher Agent (P0)

*Refs: FR-4 (Watcher Agent), FR-6 (Context Gathering - concurrent queries), Arch (Watcher agent), NFR-Performance (< 20ms from cache), NFR-Security (redaction), AC-3*

- [ ] Implement `agents/watcher.py` using cached startup detection.
- [ ] Detect OS, shell, terminal when available, WSL/container/SSH/native hints, and interactive/non-interactive state.
- [ ] Detect tech stack indicators in the project root.
- [ ] Detect git context safely: check git availability, use subprocess timeouts, handle non-repo, empty repo, detached HEAD, and errors.
- [ ] Return context from cache only in request path.
- [ ] Redact sensitive environment values before returning/logging context.
- [ ] Add tests with mocked filesystem, env vars, subprocess calls, git states, and no-git systems.

## Phase 8 - Librarian Agent (P0)

*Refs: FR-5 (Librarian Agent), FR-6 (Context Gathering - concurrent queries), Arch (Librarian agent), NFR-Performance (< 100ms search, 5000 file cap), NFR-Reliability (permission errors, watchdog serialization), NFR-Security (project-root boundaries, snippet redaction), AC-4*

- [ ] Implement `agents/librarian.py` scan and index flow.
- [ ] Filter eligible files and skip `.git`, dependency dirs, virtualenvs, build output, and binary files.
- [ ] Cap MVP indexing at 5,000 eligible files and warn on partial coverage.
- [ ] Build in-memory file metadata and token/path index.
- [ ] Write session-local `index.md` only for debugging/inspection.
- [ ] Implement deterministic search returning up to 10 sanitized matches.
- [ ] Integrate watchdog where supported.
- [ ] Serialize watchdog updates through an async queue or equivalent lock-safe pattern.
- [ ] Add tests for scan filtering, large directory cap, permission errors, search ranking, snippet redaction, and concurrent update/query safety.

## Phase 9 - Context Gatherer (P0)

*Refs: FR-6 (Context Gathering), FR-7 (Pipeline - context gathering stage), Arch (Analysis flow - context gatherer helper), NFR-Performance (500ms hard cutoff), NFR-Reliability (timeout/failure isolation), Data Contracts (Context Gatherer Response), AC-5*

- [ ] Implement a daemon-local context gatherer helper used by the pipeline.
- [ ] Expose the same logic through `/context-gatherer` for diagnostics/external callers.
- [ ] Decide relevant agents from command tokens, file paths, and command categories.
- [ ] Query Watcher and Librarian concurrently.
- [ ] Enforce a 500ms total hard cutoff with no retry inside the user-facing budget.
- [ ] Return `watcher`, `librarian`, `timed_out`, `errors`, `partial`, `latency_ms`, and per-agent latency.
- [ ] Ensure slow, failing, or malformed agents do not block command analysis.
- [ ] Add unit and integration tests for healthy, slow-agent, failing-agent, malformed-agent, and no-context-needed scenarios.

## Phase 10 - Pipeline, Rules, Cache, And Providers (P0)

*Refs: FR-7 (Pipeline And Providers), FR-6 (Context Gathering integration), Arch (Analysis flow), NFR-Performance (early exits, AI analysis < 6s), NFR-Reliability (provider fallback, cancellable calls), NFR-Security (secret redaction in prompts), Data Contracts (Analysis Response), AC-2, AC-6*

- [ ] Refactor `daemon/pipeline.py` stages: sanitizer, parser, rules, cache lookup, context gatherer, provider analysis, postprocess, formatter.
- [ ] Preserve early exits for cache hits and high-confidence deterministic rules.
- [ ] Add command/path heuristics for context relevance.
- [ ] Pass sanitized context into provider prompts.
- [ ] Implement provider fallback for missing key, network failure, timeout, and malformed provider response.
- [ ] Ensure provider calls are cancellable and have strict timeouts.
- [ ] Add tests with mocked providers only; no real API keys in tests.

## Phase 11 - Analysis, Status, And Error UI (P1)

*Refs: FR-8 (UI/UX), Arch (Analysis flow - CLI renders Rich output), Data Contracts (Analysis Response), AC-2, AC-7*

- [ ] Implement `ui/analysis.py` for risk, explanation, alternatives, context used, and latency breakdown.
- [ ] Implement `ui/status.py` for daemon, agents, providers, and session details.
- [ ] Implement `ui/banner.py` for concise ready state and usage hints.
- [ ] Add color fallbacks for terminals without truecolor support.
- [ ] Truncate long explanations, context snippets, and tech-stack lists.
- [ ] Add snapshot/golden-output style tests where practical.

## Phase 12 - Shell Adapters (P0)

*Refs: FR-9 (Shell Adapters), FR-1 (CLI - sm -a), AC-8*

- [ ] Update bash adapter to call `sm -a <command>` safely.
- [ ] Update zsh adapter to call `sm -a <command>` safely.
- [ ] Update PowerShell adapter to call `sm -a <command>` safely.
- [ ] Verify adapters preserve quoting, flags, and shell-special constructs as much as the shell permits.
- [ ] Verify disabled-daemon behavior does not break normal shell usage.
- [ ] Add install/uninstall dry-run support if not already present.
- [ ] Add adapter smoke tests for bash, zsh, and PowerShell where CI supports them.

## Phase 13 - Observability And Security Hardening (P0/P1)

*Refs: NFR-Security (IPC local binding, payload validation, project-root boundaries, log redaction), NFR-Reliability (structured logs, log rotation), FR-3 (Session Management - logs outside session dir), FR-7 (Pipeline - secret redaction)*

- [ ] Add structured logs for daemon lifecycle, IPC requests, context gathering, provider calls, and errors.
- [ ] Add log redaction for API keys, long tokens, SSH keys, emails, and obvious secrets.
- [ ] Add log rotation and bounded log size.
- [ ] Enforce IPC local binding and active-session validation.
- [ ] Validate all IPC payloads and reject oversized requests.
- [ ] Enforce project-root boundaries for Librarian file access.
- [ ] Add security tests for path traversal, redaction, malformed IPC, and oversized payloads.

## Phase 14 - Testing And CI (P0)

*Refs: All FRs/NFRs (comprehensive coverage), NFR-Reliability (test coverage), NFR-Security (security tests), AC (all acceptance criteria), FR-7 (no real API keys in tests)*

- [ ] Add unit tests for CLI parser, config, session manager, IPC, agents, context gatherer, pipeline, providers, and UI formatting helpers.
- [ ] Add integration tests for enable/status/analyze/disable.
- [ ] Add integration tests for context-gatherer timeout and partial-result behavior.
- [ ] Add provider fallback tests with mocked providers.
- [ ] Add shell adapter smoke tests where supported.
- [ ] Configure CI for lint, unit tests, integration tests, and packaging.
- [ ] Ensure tests pass on at least Linux and Windows runners if CI capacity allows.
- [ ] Do not require network access or real provider credentials in CI.

## Phase 15 - Documentation And Release (P1)

*Refs: FR-1 (CLI), FR-2 (Daemon Lifecycle), FR-3 (Session Management - config locations), FR-9 (Shell Adapters), MVP Scope (In/Out of scope), Post-MVP Parking Lot*

- [ ] Update README with v2 CLI examples and daemon lifecycle.
- [ ] Create or update migration notes for v1 users, emphasizing no backward-compatible CLI support.
- [ ] Document config locations and provider setup.
- [ ] Document shell adapter install/uninstall.
- [ ] Document known MVP limitations and post-MVP parking lot.
- [ ] Update version metadata to `2.0.0`.
- [ ] Build package and test installation in a clean environment.
- [ ] Prepare changelog and release checklist.

## Post-MVP Parking Lot (P2)

*Refs: MVP Scope (Out of Scope), Section 9 (Post-MVP Parking Lot in requirements doc)*

- [ ] Persistent index with smart invalidation.
- [ ] Multi-session/multi-directory daemon support.
- [ ] User plugin API and dynamic third-party agents/providers.
- [ ] `/deep-research`, research queue, and `sm research`.
- [ ] Fuzzy search, semantic search, and embeddings.
- [ ] `sm providers`, `sm doctor`, Prometheus metrics, and richer diagnostics.
- [ ] IDE integrations and collaboration/team features.

## MVP Done When

*Refs: AC (Acceptance Criteria - section 8), All Phases (comprehensive verification)*

- [ ] Only the two canonical v2 docs remain for requirements/design and tasks.
- [ ] `sm enable` starts daemon and reports ready through `/status`.
- [ ] `sm -a <command>` analyzes commands without requiring quotes around the command.
- [ ] Watcher and Librarian provide context within the 500ms context budget or return partial results.
- [ ] Provider outages degrade to deterministic safety output.
- [ ] `sm disable` stops daemon and removes session-local files.
- [ ] Shell adapter smoke tests pass for supported shells.
- [ ] Unit and integration tests pass without real API keys.
