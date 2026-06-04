Title: Verification Before Completion — /context-gatherer Implementation Checklist

Purpose
- This task file lists the changes required to implement and verify the /context-gatherer endpoint (low-latency project state & context aggregator) and related pipeline/agent integration. It is derived from and must stay consistent with:
  - docs/shellmate-v2-requirements-design.md
  - shellmate-v2-mvp-plan.md

Scope
- Implement /context-gatherer IPC handler in the daemon.
- Ensure the daemon can return aggregated Watcher + Librarian context within a hard 500ms user-facing cutoff.
- Add tests, CI checks, and verification steps to confirm correct behavior across typical platforms.

File to add/modify
- New: docs/verification-before-completion.md (this file)
- Modify: daemon/server.py (add handler)
- Modify: daemon/pipeline.py (use context-gatherer where appropriate)
- Modify: agents/watcher.py (ensure get_context API)
- Modify: agents/librarian.py (ensure search API + in-memory index access)
- Modify: ipc/client.py (add /context-gatherer client helper)
- Modify: tests/ to add unit/integration tests described below

Prerequisites & assumptions
- Follow constraints in docs/shellmate-v2-requirements-design.md (Python 3.8+, asyncio, cross-platform). See Decision 8 and FR-5.1 for timeout semantics.
- Agents expose request/response queues per the MVP plan and support the request format described in daemon/pipeline.py.
- Session manager and IPC server are present and the daemon runs bound to localhost only.

Acceptance Criteria (must pass before completion)
1. /context-gatherer responds within 500ms in normal conditions and returns partial context with timed_out list if agents are slow.
2. Agent timeouts enforced with asyncio.wait_for and the pipeline continues without agent context on timeout.
3. Thread-safety: Librarian index updates (watchdog) do not race with agent queries (use a serialized update queue or lock).
4. Unit and integration tests cover healthy, slow, failing-agent scenarios.
5. CLI/pipeline uses the endpoint correctly for command analysis flows and degrades gracefully.

Detailed Tasks

1) Define request/response schema (P0)
  - Add JSON schema docs and dataclass definitions in agents/base.py or ipc/schema.py:
    - Request: {"request_id": str, "action": "get_context", "command": str}
    - Response: {"request_id": str, "watcher": Optional[dict], "librarian": Optional[dict], "timed_out": List[str], "latency_ms": int}
  - Reference: docs/shellmate-v2-requirements-design.md Message Format (lines ~668-705)

2) Daemon: /context-gatherer handler (P0)
  - Add handler in daemon/server.py that accepts incoming context-gatherer requests over the existing IPC (JSON/TCP).
  - Validate origin: ensure connection is from localhost.
  - Implementation outline:
    - Parse request and create a unique internal request_id if not provided.
    - Determine if watcher and/or librarian should be queried (reuse should_query_watcher() and has_file_references()).
    - For each needed agent, dispatch an internal AgentRequest and await response via per-request asyncio.Queue using asyncio.wait_for(..., timeout=0.5).
    - Collect successes and record which agents timed out.
    - Compute aggregate latency and respond with the JSON response schema.
  - Ensure robust error handling: exceptions from agents should be caught and returned as null context + logged.
  - Logging: structured log entry for each request (timestamp, request_id, agents_used, timed_out list, latency_ms)

3) Pipeline integration and client helper (P0)
  - daemon/pipeline.py: when pipeline needs context, call internal helper that invokes the same logic as /context-gatherer (prefer direct in-process call for efficiency if running in same daemon; otherwise call IPC endpoint). Document both code paths.
  - ipc/client.py: add context_gatherer(client, command, timeout=0.5) helper that calls /context-gatherer and returns parsed response.
  - Update CLI flow to call pipeline which will use context_gatherer.

4) Agent-side contracts (P0)
  - agents/watcher.py: implement get_context(command) synchronous async API to return EnvironmentContext dict; lightweight and cached. Must be safe to call concurrently.
  - agents/librarian.py: implement search(query) API returning list of FileMatch objects; must use in-memory index and support concurrent queries. Ensure thread-safe index access.
  - Both agents should accept agent requests via their response_queue and return AgentResponse objects as defined in message schema.

5) Concurrency & safety (P0)
  - Librarian: implement event queue pattern where watchdog (thread) enqueues file events to an asyncio.Queue consumed by Librarian's async loop which performs index mutations. This avoids thread->async race conditions.
  - Protect in-memory structures with asyncio.Lock when needed during read-modify operations.

6) Tests (P0)
  - Unit tests:
    - Handler unit: call /context-gatherer handler with mocked agents that respond quickly; assert full context returned and latency < 500ms.
    - Timeout unit: mock one agent to sleep > 500ms; assert timed_out includes that agent and response returned within ~500ms.
    - Error unit: mock agent raising exception; assert response contains null context for that agent and pipeline proceeds.
  - Integration tests:
    - Start test daemon, register test agents (in-process or mocked), call /context-gatherer over IPC, verify response formats and logs.
    - End-to-end: sm -a <command> triggers pipeline which uses context_gatherer and includes context in AI prompt (mock AI provider); verify UI displays context panel when present.
  - E2E tests (optional but recommended): run in CI on Linux and Windows runners to verify cross-platform behavior.

7) CLI & UI (P1)
  - CLI: no direct calls to /context-gatherer from UI rendering; the pipeline should supply context to the CLI output. Add ipc helper for debug CLI commands to call /context-gatherer (admin diagnostic).
  - UI: ensure status panel continues to use /status; only debug or diagnostics should use /context-gatherer directly.

8) Observability & logging (P1)
  - Add structured logs for each /context-gatherer request: request_id, command, agents_queried, timed_out, latency_ms.
  - Increment metric counters: context_requests_total, context_timeouts_total, context_latency_ms histogram.

9) Security & permissions (P1)
  - Ensure IPC bound to 127.0.0.1 only; consider Unix domain socket on Unix-likes and proper file permissions.
  - Validate incoming requests schema; reject malformed requests with 400.
  - Ensure no API keys or PII are included in returned context; sanitize file snippets before inclusion.

10) Documentation & developer notes (P1)
  - Update docs/shellmate-v2-requirements-design.md to reference /context-gatherer as the IPC contract for context queries (if not already present).
  - Update shellmate-v2-mvp-plan.md to list /context-gatherer as implemented and add verification steps.
  - Add docs example of request/response JSON and sample CLI debug command to call the endpoint.

Verification Checklist (must be green before marking feature complete)
- [ ] Unit tests pass for handler, pipeline integration, agent contracts
- [ ] Integration tests (daemon + agents) pass in CI
- [ ] Performance: /context-gatherer responds within 500ms for sample repo (<=1000 files) on CI environment with SSD; CI records latency histogram
- [ ] Thread-safety: Librarian index updates do not crash or corrupt structure under concurrent events + queries
- [ ] Security: IPC bound to localhost, session dir permissions set, input sanitization in place
- [ ] Logging & metrics captured and accessible (commands.log contains entries for context requests)

Implementation Notes and references
- Timeout enforcement pattern: use asyncio.wait_for(agent_response_future, timeout=0.5) in the daemon/pipeline and /context-gatherer handler (see docs/shellmate-v2-requirements-design.md Decision 8).
- Use per-request response_queues (response_queues[request_id] = asyncio.Queue()) to receive agent replies; ensure cleanup after timeout or error.
- Prefer in-process direct function calls for pipeline->agents when running in same daemon to avoid IPC overhead, but keep /context-gatherer IPC handler for remote callers and diagnostics.

Deliverables
- Source code changes (daemon/server.py, daemon/pipeline.py, ipc/client.py, agents/*)
- Tests added under tests/unit and tests/integration
- Docs updated (design and MVP plan references)
- CI updated to run the new tests and measure latency

Timeline estimates (rough)
- Design review & schema: 1 day
- Handler & pipeline integration: 2-3 days
- Agent contract adjustments & thread-safety: 2 days
- Tests & CI updates: 1-2 days
- Docs & cleanup: 0.5-1 day
