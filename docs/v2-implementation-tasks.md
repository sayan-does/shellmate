# ShellMate v2.0 — Expanded Implementation Task List

This file consolidates and expands the actionable tasks required to implement the v2 requirements and design. It is intended to be comprehensive — use it as a living checklist. Break items into issues/PRs with owners and estimates.

Conventions
- Tasks are grouped by phase and component. Mark tasks done with [x] and add links to PRs/issues when completed.
- Priority: P0 (must for MVP), P1 (important), P2 (nice-to-have / future)

---

PHASE 0 — Project Setup (P0)
- [ ] Create repository structure for v2 (docs/, cli/, daemon/, agents/, providers/, ui/, tests/).
  - Verify: imports resolve (run a simple import smoke test from project root).
  - Add __init__.py files where needed to clarify package layout.
  - Add top-level README, CODE_OF_CONDUCT, CONTRIBUTING, LICENSE.
- [ ] Initialize git defaults and .gitignore, add basic CODEOWNERS.
- [ ] Add CI pipeline skeleton (unit tests, lint, formatting).
  - Create CI jobs: lint (ruff/flake), typecheck (mypy/pyright optional), unit (pytest), packaging (build wheel).
  - Add pre-commit hooks for formatting (black/isort) and simple linters.
  - Verify: CI runs on a branch and reports status.
- [ ] Update pyproject.toml version and metadata (v2.0.0).
  - Add build/test extras, define console_scripts entry points for `sm` CLI.
  - Verify: build wheel locally and install in a venv.
- [ ] Add development requirements (rich, watchdog, pytest-asyncio, psutil).
  - Add pinned dev dependencies in tooling file (requirements-dev.txt or pyproject[dev]).
  - Verify: pip install -r requirements-dev.txt in CI matrix job.
- [ ] Workspace conveniences
  - Add Makefile / task runner with commands: install-dev, test, lint, package, run-daemon-dev.
  - Add VSCode launch/test configs and minimal editor settings.

PHASE 1 — CLI & Session (P0)
- [ ] cli/parser.py: implement ShellMateCommandParser
  - Define CLI grammar for `sm -a <command>` and `sm <subcommand> [flags]`.
  - Implement robust tokenization: preserve quoting, escapes, pipes, redirects and detect an empty or whitespace-only command.
  - Produce ParsedCommand dataclass with fields: raw, tokens, sanitized, action, args, metadata.
  - Provide suggestions for invalid input (common shell mistakes) and unit tests for them.
  - Tests: quotes, nested quotes, escapes, pipes, redirects, env var expansion edge-cases.
- [ ] cli/main.py: wire parser and command routing
  - Keep Click for user-facing subcommands; use raw argv for the `-a` analyze flow only.
  - Implement consistent logging and an explicit non-exiting error path (raise exceptions that are caught at top-level to return non-zero codes).
  - Implement `sm enable`, `sm disable`, `sm status`, `sm config` to send IPC requests to daemon with timeouts and retries.
  - Tests: CLI unit tests with runner, end-to-end test that spawns a test daemon process.
- [ ] configuration & persistence
  - Define default config file locations (XDG on *nix, AppData on Windows) and config schema (TOML/JSON).
  - Implement minimal config loader with validation and docs for fields.
- [ ] daemon/session.py: SessionManager API
  - Implement create_session(pid, directory) with atomic write (write to tmp + rename) and session.json metadata (pid, created_at, owner_uid, socket_path).
  - Implement get_active_session() validating PID cross-platform using psutil (fallback to os.kill checks on unix).
  - Implement cleanup_session(pid) and cleanup_stale_sessions() that only remove owned files and are resilient to races.
  - Enforce session dir permission rules (chmod 700 on Unix, use ACLs on Windows). Add unit tests that run on CI matrix where possible.
- [ ] IPC client (ipc/client.py)
  - Implement JSON-over-TCP client with connection pooling and reconnect/backoff.
  - Provide request_id correlation, streaming response handling (server sends length-prefixed chunks or newline-delimited JSON), and cancel support.
  - Expose a small synchronous wrapper for CLI usage and an asyncio client for internal use.
  - Tests: connection failures, partial responses, concurrent clients.
- [ ] Tests: unit and integration tests for CLI, parser, session manager, IPC client
  - Provide fixtures for temporary session dirs and ephemeral daemons.

PHASE 2 — Daemon Server & Lifecycle (P0)
- [ ] daemon/server.py: IPC transport and request routing
  - Choose transport per platform: Unix domain socket on Unix, TCP localhost or named pipe on Windows. Provide an option to force TCP for testing.
  - Implement an asyncio server that accepts JSON requests and routes to handlers by `type` field.
  - Required handlers: analyze, get_status, context-gatherer, deep-research (enqueue), shutdown, health, metrics.
  - Implement graceful shutdown: stop accepting new connections, cancel outstanding tasks, flush state to disk.
  - Add per-connection read/write timeouts and input size limits to protect from abuse.
- [ ] daemon/lifecycle.py: manage background process
  - Implement cross-platform spawn: fork/exec + double-fork on Unix where appropriate; on Windows use subprocess.CREATE_NEW_PROCESS_GROUP.
  - Child must write PID and a ready token to session dir atomically only after listening socket is bound.
  - Parent polls startup status via /status until ready or times out; provide user-friendly errors.
  - Implement stop/terminate semantics: polite shutdown (SIGTERM/SIGINT) with timeout, then SIGKILL equivalent.
- [ ] daemon/startup_status.py
  - Define a small status model written to session dir and served over IPC: stages (starting, agents_ready, ready), agent readiness map, file counts, timestamps, last_error.
  - Ensure updates are atomic and resilient to crashes.
- [ ] session cleanup and crash recovery
  - Detect stale PID files and sockets and provide deterministic cleanup paths; do not remove sockets belonging to other users.
  - On abnormal termination start a short backoff to avoid crash loops.
- [ ] Tests: integration tests for lifecycle
  - Test enable/disable flow, race conditions during start/stop, and behavior when the daemon fails to bind.

PHASE 3 — Agents Framework (P0)
- [ ] agents/base.py: Agent abstract base and lifecycle
  - Define Agent abstract class with methods: start(loop), stop(), handle_request(request) and health_ping().
  - Define typed AgentRequest and AgentResponse dataclasses with serialization helpers.
  - Add structured logging and per-agent rate limiting config.
- [ ] agents/registry and loading
  - Implement agent registration API so server can enumerate available agents and their capabilities.
  - Support dynamic loading of agents from `agents/` as plug-ins (simple import-based discovery).
- [ ] agents/queues.py: request/response plumbing
  - Implement response_queues mapping, safe concurrent access, and helper to publish responses to awaiting callers.
  - Make sure to cleanup entries on timeouts and client disconnects.
- [ ] Message schema and validation
  - Define and publish JSON schema for requests and responses. Use pydantic or jsonschema for validation at ingress.
  - Version the schema to allow forward/backward compatibility.
- [ ] Tests
  - Unit tests for base agent behavior, registry, message validation, queue timeouts and cleanup.

PHASE 4 — Watcher Agent (P0/P1)
- [ ] agents/watcher.py core detection
  - detect_environment(): OS, shell (bash/zsh/pwsh), terminal emulator, interactive vs non-interactive, containerized detection.
  - detect_tech_stack(): detect package manifests (package.json, pyproject.toml, go.mod, Gemfile), presence of Dockerfile, CI descriptors, and common build tools.
  - detect_git(): safe git calls with subprocess timeouts and fallbacks; gather branch, staged/unstaged counts, last commit hash/message, repo root path.
  - get_context(command): decide which detections are relevant to the command (e.g., for `npm run` include package.json info), return EnvironmentContext.
  - Implement lightweight PII redaction for environment values.
- [ ] caching and persistence
  - Cache detection results in memory and write env_cache.json atomically to session dir.
  - Invalidate cache on workspace change or after TTL.
- [ ] event-driven updates
  - Optionally re-run detection on filesystem events (e.g., if package.json changes) or on explicit agent refresh requests.
- [ ] operational details
  - Startup: run a fast probe then schedule deeper detection on background.
  - Respect resource limits and timeouts; provide deterministic worst-case latency.
- [ ] Tests
  - Unit tests that mock filesystem, env vars and subprocess; integration tests in simple repo fixtures.

PHASE 5 — Librarian Agent (P0)
- [ ] agents/librarian.py scanning and indexing
  - scan_directory(root): recursively enumerate files filtered by CODE_EXTENSIONS and ignore rules (.gitignore). Collect meta: path, size, mtime, hash (opt), language, shebang.
  - Build index structures: _files (path → meta), inverted _token_index (token → set(paths)), path trie for prefix matches.
  - Provide incremental indexing: detect changed files by mtime/size/hash and update the index without re-scanning everything.
  - Write a human-readable index.md to session dir for debugging with a compact summary.
- [ ] filesystem watcher integration
  - Integrate watchdog observer (on platforms supported) and post events to an asyncio.Queue. Implement coalescing/debounce to avoid thrashing.
  - IndexUpdateHandler should enqueue high-level change events and allow background consumer to process them serially.
- [ ] thread-safety and performance
  - Use an asyncio.Queue consumed by a single coroutine to apply updates; avoid heavy locking.
  - Limit memory usage by bounding cached file content size and evicting entries over a configured threshold.
- [ ] search API
  - search(query): tokenized AND lookup on inverted index; fallback to substring path search; return ranked FileMatch with snippet and match positions.
  - Support filters: extensions, repo-relative path, modified-within days.
- [ ] persistence and recovery
  - Optionally snapshot index to disk (JSON or SQLite) and restore on startup with validation.
- [ ] Tests
  - Unit tests for scanning, incremental updates, search correctness, and watcher event handling. Add a small sample repo fixture.

PHASE 6 — Pipeline & Agent Integration (P0)
- [ ] daemon/pipeline.py stage design
  - Define a PipelineStage interface: input -> transform -> output, with error handling and timing instrumentation.
  - Current stages: sanitizer, parser, rules, cache lookup, agent-context-gather, provider_analyze, postprocess, response formatter.
  - Preserve early-exit behavior: cache hit, sanitizer-corrected commands, or high-confidence rule matches.
- [ ] agent context gathering stage
  - Decide per-request which agents to query (watcher, librarian, other agents) based on heuristics (command tokens, file paths, repo presence).
  - Implement per-agent queries concurrently with a hard timeout (e.g., 500ms) using asyncio.create_task and asyncio.wait_for. Collect partial results and timed_out list.
  - Merge contexts with deterministic precedence and size limits.
- [ ] query_agent() helper
  - Create a per-request ephemeral response queue, send request with request_id, await first response or timeout, and cleanup the response_queues entry on exit.
  - Add metrics for agent latency and timeout counts.
- [ ] AI prompt integration and safety
  - Integrate agent-provided context into provider prompts while redacting PII and limiting size.
  - Instrument prompt length and risk that the provider call might exceed token limits; apply truncation strategies.
- [ ] Tests
  - Use mocked agents to simulate normal, slow, and failing responses; assert pipeline behavior (partial results, fallback to minimal context, metrics recorded).

PHASE 7 — IPC Endpoints: /context-gatherer & /deep-research (P1)
- [ ] /context-gatherer endpoint
  - Accepts validated command payload and request metadata (cwd, env hint). Authenticate caller is local and owns session.
  - Query relevant agents with per-agent hard timeout (500ms) concurrently. Return aggregated context, list of timed_out agents, latency per-agent, and size of returned context.
  - Limit endpoint response size and include a `partial: true` flag when truncation occurs.
  - Tests: slow-agent simulation, malformed payloads, and authorization failures.
- [ ] /deep-research endpoint and research queue
  - Accept search/research requests and enqueue them with priority, TTL and optional callback url (local-only).
  - Return research_id immediately with status queued (202). Provide /research/{id} to fetch status/results and /research?recent to list recent jobs.
  - Background worker pool processes jobs, writes results to ephemeral store in session dir and updates progress. Implement retries on transient provider errors.
  - Implement TTL and cleanup policy for stored results and allow explicit delete.
  - Tests: queued lifecycle, cancellation, result retrieval and cleanup.
- [ ] security and validation
  - Validate all inputs with schema, enforce rate limits per session to avoid DoS, and ensure endpoints are accessible only from the same host and session owner.

PHASE 8 — Providers & AI Prompts (P0/P1)
- [ ] providers/base.py and interface
  - Define AIProvider interface: analyze_risk(prompt, context, max_tokens, timeout) -> structured response; generate_remediation(...) for fixes.
  - Standardize provider response schema (classification, confidence, explanation, remediation suggestions, metadata).
- [ ] providers/router.py: selection, retries and backoff
  - Implement provider router with selection logic, per-provider rate limits, retry/backoff policy and failover chains.
  - Support mocking providers for tests and local offline mode.
- [ ] provider adapters
  - Implement adapters for specific providers (groq/openrouter) that transform internal prompt+context into provider API calls, handle paging/streaming where supported, and map responses.
  - Ensure provider calls are cancellable and timed out by pipeline.
- [ ] security of keys and redaction
  - Load API keys from secure location (~/.shellmate/credentials or env) with strict file permissions. Never include raw keys in logs or telemetry.
  - Implement prompt redaction: strip known secrets (API keys, long hex tokens, email addresses) before sending to providers; log redaction events.
- [ ] prompt templates and size control
  - Use templated prompts and clearly document variable slots. Compute token/char estimates and truncate low-priority context fields when near limit.
- [ ] Tests
  - Mock provider responses to exercise happy path, slow provider, malformed responses, and fallback behavior.

PHASE 9 — UI, CLI UX & Shell Adapters (P1)
- [ ] ui/display.py and interactive UX
  - Implement a responsive startup progress display that polls /status (~200ms) with exponential backoff when idle.
  - Provide non-blocking UX for `sm -a` that shows progress, partial context, and allows cancel.
- [ ] presentation components
  - ui/banner.py: concise startup banner and diagnostic hints.
  - ui/analysis.py: hierarchical result view (risk, confidence, remediation steps) with color-coded levels and truncation rules.
  - ui/status.py: show per-agent latencies, cache stats, provider health and session info.
- [ ] CLI commands and ergonomics
  - Implement `sm -a`, `sm enable`, `sm disable`, `sm status`, `sm config`, `sm providers`, `sm research` with consistent flag pattern (verbosity, timeout, json output).
  - Support `--json` output for machine consumers and stable keys for parsing.
  - Provide clear exit codes: 0 success, 2 usage, 3 temporary error, 4 internal error.
- [ ] Shell adapters and install scripts
  - Provide small shell hook snippets for bash/zsh/fish/powershell to intercept commands and call `sm -a` appropriately.
  - Implement install/uninstall scripts that detect shell rc files, offer a dry-run, and respect user consent.
  - Tests: smoke tests in containers or VMs to ensure the hook doesn’t break normal shell behavior.

PHASE 10 — Rules, Sanitizer, and Cache (P0/P1)
- [ ] rules engine
  - Define rules format (YAML) with pattern types: exact, regex, token-based, fuzzy. Each rule includes category, confidence, recommended action and metadata.
  - Implement rule matcher with priority resolution and confidence thresholds; support disabling rules per-session.
  - Provide tools to validate and lint rules files.
- [ ] sanitizer
  - Implement sanitizer stage to normalize whitespace, collapse dangerous shell constructs where safe, correct common typos, and detect trivial no-ops.
  - For syntactic checks use lightweight language-specific linters where available (shellcheck integration optional) with strict timeouts.
  - On sanitizer correction, surface the suggested sanitized command and treat it as an early-exit or re-run candidate depending on policy.
- [ ] cache
  - Implement a pluggable cache interface. Default: LRU in-memory cache keyed by normalized command + environment fingerprint.
  - Support TTL, max-entries, and manual invalidation (`sm cache clear`). Optionally add approximate similarity matching using fingerprints (minhash) or an embeddings store later.
  - Instrument cache metrics: hit/miss, evictions.
- [ ] Tests
  - Unit tests for rule matching priority, sanitizer corrections, cache hit/miss behavior and eviction.

PHASE 11 — Observability, Logging & Metrics (P1)
- [ ] logging
  - Implement structured JSON logging with level, timestamp, correlation_id, request_id, and agent tags.
  - Add log rotation and size limits. Ensure logs redact sensitive values (API keys, tokens, email addresses) before writing.
- [ ] metrics
  - Collect metrics: end-to-end command latency, per-stage timings, cache hit rate, provider latencies, agent timeout counts, research queue depth.
  - Expose a /metrics endpoint (Prometheus format) on the control socket or write periodic snapshots to session dir.
- [ ] diagnostics and `sm doctor`
  - Implement `sm doctor` to run quick checks (session dir permissions, socket binding, provider auth) and surface remediation steps.
- [ ] tests
  - Tests that validate structured log schema, redaction rules, and basic metrics surfaces.

PHASE 12 — Security & Hardening (P0/P1)
- [ ] IPC & network hardening
  - Ensure server only binds to localhost/UDS and validate remote peer is same user where possible.
  - Validate and restrict maximum payload sizes and input complexity to mitigate DoS.
- [ ] secrets and permissions
  - Enforce strict file permissions for session dir and API key files (600/700). Offer encrypted storage option for keys (optional).
  - Ensure keys never appear in logs, stack traces, telemetry or persisted prompt snapshots.
- [ ] input validation and sanitization
  - Validate all IPC payloads with a JSON schema and reject/404 invalid requests.
  - Implement content sanitizer before sending code or files to providers: remove long tokens, email addresses, SSH keys, and other PII patterns.
- [ ] runtime hardening
  - Run provider calls in a sandboxed coroutine with strict CPU/time limits, and avoid executing arbitrary code received from providers.
  - Add dependency scanning (safety, SCA) as part of CI and block releases on critical vulnerabilities.
- [ ] threat modeling and audits
  - Document threat model, identify high-risk flows (provider exfiltration, local privilege escalation) and add tickets for mitigations.

PHASE 13 — Testing Matrix & CI (P0)
- [ ] coverage and targets
  - Set a minimum coverage target (e.g., 80%) for core modules; measure by CI badge and fail when below threshold.
- [ ] integration tests
  - Add integration tests for pipeline with mock agents, IPC client<->daemon flows, and lifecycle (enable/disable).
  - Use parametrized tests to run across Python versions and OS where possible using CI matrix.
- [ ] e2e tests
  - E2E tests for shell adapter install and a few sample commands; run these in container images or VM runners.
  - Mark e2e as optional or gated to nightly runs due to environment flakiness.
- [ ] CI jobs
  - Jobs: lint, unit, integration, packaging, e2e (optional). Add timeouts and retry logic for flaky external steps.
- [ ] flaky test management
  - Keep a DEFERRED_FLAKES list and require flake fixes when new failures appear; capture artifacts (logs, traces) on failures.

PHASE 14 — Documentation, Migration & Release (P1)
- [ ] user and developer docs
  - Update README with v2 quick start, examples, and troubleshooting.
  - Add architecture.md describing components, data flows and IPC schema.
  - Add CONTRIBUTING and developer setup docs for running tests and debugging the daemon.
- [ ] migration guide
  - Create MIGRATION.md documenting breaking changes, session/config migration steps, and automated migration scripts where possible.
- [ ] release process
  - Maintain CHANGELOG.md and draft release notes for v2.0.0. Automate packaging and publish to PyPI using GitHub Actions.
  - Create a release checklist: tests, SCA, changelog, tag, publish.
- [ ] API and schema docs
  - Document IPC endpoints, request/response schemas, and provider prompt templates for integrators.

PHASE 15 — Post-MVP Enhancements (P2)
- [ ] persistent index and DB options
  - Implement optional persistent index backed by SQLite or a lightweight KV store with smart invalidation hooks.
- [ ] advanced search and embeddings
  - Add optional fuzzy/semantic search plugin using embeddings with pluggable provider and offline caching.
- [ ] multi-session and workspace modes
  - Explore multi-session daemon or per-user multi-directory tracking; design session isolation and resource quotas.
- [ ] plugin/extension system
  - Design a plugin API for third-party agents/providers with safe sandboxes and capability scoping.
- [ ] IDE & CI integrations
  - Add connectors for IDEs (VSCode extension) and CI/CD detectors to provide context during runs.

Appendix — Quick Verification Checklist (smoke tests)
- [ ] sm enable creates session dir, starts daemon, writes session.json, and shows startup progress
- [ ] sm -a echo hi → pipeline runs quick path and returns SAFE/LOW result with latency < 200ms on local machine (CI-friendly expectation may be higher)
- [ ] sm -a rm -rf /tmp/test → Librarian finds related files and Watcher returns git context (if repo). Verify partial context when agents timeout.
- [ ] sm research --deep "<query>" → returns research_id immediately and result retrievable via /research/{id}
- [ ] sm disable cleans up session dir and stops daemon but preserves logs and diagnostics if `--preserve-logs` supplied
- [ ] sm status shows agent status, PID, directory, file count, provider status and last health check time

Notes and guidance
- Keep tasks small and testable. Prefer small, reviewable PRs (one feature + tests) rather than large monolithic changes.
- When in doubt, add a unit test first describing the expected behavior (TDD for critical paths: parser, pipeline timeouts, agent query handling).

Next step suggestions (pick one):
1. Split this document into per-area milestone files (cli-tasks.md, agents-tasks.md, ui-tasks.md) for issue creation.
2. Create issue templates for highest-priority P0 items and open starter PRs with scaffolding.
3. Implement a few small starter tasks (parser tests + parser implementation) and open a draft PR for review.

---

If you'd like, I can split this file into separate milestone files (cli-tasks.md, agents-tasks.md, ui-tasks.md) or create issue templates for the highest-priority items and open starter PRs for them. Which next step do you want me to take?
