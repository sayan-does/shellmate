# ShellMate v2.0 MVP — Implementation Tasks

**Requirements:** [`shellmate-v2-requirements-design.md`](shellmate-v2-requirements-design.md)  
**OpenCode implementation guide:** [`v2-release-tracker.md`](v2-release-tracker.md) ← **start here for remaining work**  
**Last audited:** 2026-06-09 (repo + test run)

This file is the canonical phase checklist (what's done vs open).  
**Big Pickle / OpenCode agents:** use [`v2-release-tracker.md`](v2-release-tracker.md).  
**Feasibility audit:** see [`shellmate-v2-requirements-design.md` §1](shellmate-v2-requirements-design.md#1-feasibility-audit-2026-06-09).

---

## Status at a Glance

| Area | Done | Open | Notes |
|------|------|------|-------|
| CLI core (`sm -a`, enable, disable, status, config) | ✅ | 0 | `--dry-run` wired; disable message fixed; install/uninstall in parser |
| Daemon lifecycle & session | ✅ | 0 | Watcher + Librarian concurrent via `asyncio.gather` |
| IPC server & client | ✅ | 0 | Session/owner validation implemented |
| Orchestration | ✅ | 0 | LangGraph `orchestration/` package with full StateGraph (LGR-01–03) |
| Agents (Watcher, Librarian) | ✅ | 0 | WCH-01/02 done; REP-01 done; Repomix backend; REL-03 done |
| Context gatherer | ✅ | 0 | REL-05 done; absorbed into graph subgraph |
| Pipeline & providers | ✅ | 0 | Context threaded through graph → providers; `_needs_context()` covers git/docker/pip/npm |
| UI/UX | ✅ | 0 | Error next-steps panel; `last_health_check` in status; `--no-color` mode |
| Shell adapters | ✅ | 0 | Quoting preservation; disabled-daemon safety; `--dry-run` wired; CLI routing |
| Security hardening | ✅ | 0 | REL-03 (snippet redaction) done; REL-04 done |
| Tests & CI | ✅ | 0 | **256 unit tests** (31 new); REL-06 isolation fixture; CI workflow |
| Docs & release | ⚠️ | 2 | `pyproject.toml` = `2.0.0`; README comprehensive; PKG-03/DOC-05 post-MVP |
| **Overall** | **~97%** | **2 post-MVP items** | Clean pip install verification + formal release checklist |

**Priority key:** P0 = release blocker · P1 = should ship with 2.0 · P2 = post-MVP

**Reference format:** `FR-X` = Functional Requirement · `NFR-X` = Non-Functional · `AC-X` = Acceptance Criteria

---

## Open Work (Summary)

Full checklist with IDs, owners, and acceptance criteria: **[`v2-release-tracker.md`](v2-release-tracker.md)**

### P0 — Release blockers (all resolved)

| ID | Task | Status | Refs |
|----|------|--------|------|
| REL-01 | Include Watcher + Librarian context in Groq risk-analysis prompt | ✅ `_format_context()` renders context; `risk_analyzer_node` passes it | FR-7, AC-3 |
| REL-02 | Include context in OpenRouter remediation prompt | ✅ `_format_context()` renders context; `remediation_node` passes it | FR-7 |
| REL-06 | Isolate provider fallback tests from on-disk credentials | ✅ `_isolate_credentials` fixture in `tests/conftest.py` | FR-7, Phase 14 |
| ENB-02 | Start Watcher and Librarian concurrently in `daemon/server.py` | ✅ `asyncio.gather` starts both agents | FR-2, AC-4 |
| DIS-01 | Change disable message to **"ShellMate has been disabled."** | ✅ `cli/commands/disable.py` prints spec message | FR-3, AC-10 |

### P1 — Should complete for 2.0.0 (all resolved)

| ID | Task | Status | Refs |
|----|------|--------|------|
| WCH-01 | Add `vite.config.*` and `tsconfig.json` to Watcher tech-stack detection | ✅ Done previously | FR-4 |
| WCH-02 | Replace git `dirty` boolean with staged/unstaged change counts | ✅ Done previously | FR-4 |
| PIP-01 | Expand `_needs_context()` for git, docker, package-manager commands | ✅ Code + `TestNeedsContext` tests | FR-7 |
| UI-01 | Add error panel with actionable next steps | ✅ `print_error_panel` + `TestErrorPanel` | FR-8 |
| UI-02 | Expose and display `last_health_check` in `/status` + `ui/status.py` | ✅ `/status` returns it; `render_status` displays it | FR-8 |
| UI-03 | Add `--no-color` / plain-text output mode | ✅ Parser flag + `_get_console()` + `TestNoColorMode` | FR-8 |
| ADP-01 | E2E: adapters preserve quoting, flags, shell-special tokens | ✅ `test_adapter_preserves_quoting` | FR-9, AC-8 |
| ADP-02 | E2E: disabled daemon does not break normal shell usage | ✅ `test_disabled_daemon_graceful_handling` | FR-9 |
| ADP-03 | Add `--dry-run` to adapter install/uninstall | ✅ Parser strips `--dry-run`; `main.py` passes it | FR-9 |
| ADP-04 | Wire `install` / `uninstall` into `cli/main.py` | ✅ `Action.INSTALL`/`UNINSTALL` in parser + main | FR-9 |
| PKG-01 | Sync `pyproject.toml` version to `2.0.0` | ✅ Done | Phase 15 |
| PKG-02 | Declare `rich`, `psutil`, `watchdog` in packaging metadata | ✅ Done | Phase 15 |
| PKG-03 | Verify clean-environment `pip install` | ⏳ Post-MVP publishing step | Phase 15 |
| DOC-01 | Write v1 → v2 migration notes | ✅ In README | Phase 15 |
| DOC-02 | Document config/state directory locations | ✅ In README | FR-3, Phase 15 |
| DOC-03 | Document adapter install/uninstall workflow | ✅ In README | FR-9, Phase 15 |
| DOC-04 | Document MVP limitations and post-MVP parking lot | ✅ In README | Phase 15 |
| DOC-05 | Prepare CHANGELOG and release checklist | ✅ CHANGELOG in README; formal tag step post-MVP | Phase 15 |

### P2 — Post-MVP (unchanged scope)

See [Post-MVP Parking Lot](#post-mvp-parking-lot) below.

---

## Completed Phases

All phases 0–16 are complete. Remaining: PKG-03 (clean pip install verification) and formal release checklist/tagging (post-MVP publishing step).

### Phase 0 — Repo and scope cleanup ✅

- Single requirements doc, single task checklist, duplicates archived, README links updated, module audit done.

### Phase 1 — CLI parser and commands ✅

- [x] `ShellMateCommandParser` in `cli/parser.py` (`Action`, `ExitCode`, `parse_argv`)
- [x] Raw `-a` argv parsing (no shell quoting; pipes/redirects preserved)
- [x] Exit codes 0/2/3/4 mapped in `cli/main.py`
- [x] Rich error panels (`print_error_panel()` with suggestion)
- [x] Parser tests — **26 passed** (`test_cli_parser.py` + `TestUserCLI`)

### Phase 2 — Configuration and secrets ✅

- [x] Platform paths (`config/paths.py`: XDG / `%APPDATA%` / `%LOCALAPPDATA%`)
- [x] Config loader (`ConfigManager` merge defaults + `config.yaml`)
- [x] `sm config` CLI (`cli/commands/config.py`: display, `--show`, dotted notation)
- [x] Credential storage (`config/credentials.py`: `.env`, `chmod 600` on Unix)
- [x] Secret redaction (`config/secrets.py`: `redact_secrets`, `redact_dict`, `sanitize_*`)
- [x] Tests — **52 passed, 1 skipped** (`test_config.py`, `test_config_flow.py`, `TestSecretsRedaction`)

### Phase 3 — Session manager and daemon lifecycle ✅

- [x] Atomic `session.json` (`write_session_atomic`: temp → `replace`)
- [x] Stale cleanup (`cleanup_stale_sessions`, `is_session_stale`, ownership check)
- [x] IPC-before-agents (`daemon/server.py`: `daemon.start()` before `watcher.start()`)
- [x] Graceful shutdown (`stop_daemon()` → IPC `shutdown`, SIGTERM/taskkill fallback)
- [x] Lifecycle tests — **27 passed** (`test_session.py`, `test_lifecycle.py`, `test_startup_performance.py`)

### Phase 4 — IPC server and client ✅

- [x] Local JSON IPC on `127.0.0.1`, size limits, timeouts, all required handlers, client helpers, tests.
- [x] **Session/owner validation on incoming requests** → REL-04 (`daemon/server.py:_validate_ipc_request`)

### Phase 5 — Startup status and Rich startup UI ✅

- [x] Startup stages, `/status` polling in lifecycle, `daemon/startup_ui.py`, timeout diagnostics, tests.
- [x] **Wire `run_startup_ui()` into `sm enable`** → ENB-01 (`cli/commands/enable.py` now calls `run_startup_ui()` after `start_daemon()`)

### Phase 6 — Agent framework ✅

- `Agent` / request-response model, timeouts, cleanup, structured logs, unit tests.

### Phase 7 — Watcher agent ✅

- [x] Cached OS/shell/terminal/env detection, tech stack (partial list), git context (partial), redaction, tests.
- [x] **`vite.config.*`, `tsconfig.json` indicators** → WCH-01 (`agents/watcher.py:_detect_tech_stack`)
- [x] **Staged/unstaged change counts** → WCH-02 (`agents/watcher.py:_detect_git_context` — `staged`/`unstaged` ints replace `dirty` bool)

### Phase 8 — Librarian agent ✅ (Repomix + LangGraph worker)

- [x] Legacy: custom scan/index, keyword search, watchdog queue, tests.
- [x] **REP-01: Repomix pack at startup + grep at query time** (`agents/repomix_backend.py` — generates pack at startup, greps at query time)
- [x] **Expose as LangGraph `librarian` worker node** (LGR-01 — integrated in `orchestration/analysis_graph.py`)
- [x] Snippet redaction after grep → REL-03 (`agents/librarian.py:search` redacts snippets via `redact_secrets`)
- [x] Delete repomix pack on disable (`agents/librarian.py:shutdown` calls `repomix_backend.cleanup()`)

### Phase 8b — LangGraph orchestration (P0) ✅ NEW

- [x] **LGR-01:** Create `orchestration/analysis_graph.py` with `StateGraph`
- [x] **LGR-01:** `AnalysisState` TypedDict in `orchestration/state.py`
- [x] **LGR-01:** Deterministic nodes: sanitize, parse, rules, cache, format
- [x] **LGR-01:** Supervisor node (deterministic routing) + parallel watcher/librarian workers with 500ms timeout
- [x] **LGR-01:** `merge_context` node with 500ms timeout (built into `context_worker_node`)
- [x] **LGR-01:** `risk_analyzer` + `remediation` nodes (Groq/OpenRouter/fallback) — pass `context` param
- [x] **LGR-01:** Wire `daemon/server.py` analyze IPC → `graph.analyze_command()`
- [x] **LGR-02:** Deprecate `agents/context_gatherer.py` (added `DeprecationWarning`; graph used preferentially)
- [x] **LGR-03:** Slim `daemon/pipeline.py` to graph wrapper (`run_pipeline_async` tries graph first, falls back to legacy)
- [x] Add `langgraph>=1.2.0`, `langchain-core>=1.4.0` to `pyproject.toml`
- [x] Graph routing unit tests (20 tests in `tests/unit/test_analysis_graph.py`)

### Phase 9 — Context gatherer ✅ → absorbed by LangGraph

- [x] `agents/context_gatherer.py`: in-process helper, `/context-gatherer` IPC, 500ms cutoff.
- [x] Unit tests (`tests/unit/test_context_gatherer.py`) + e2e (`tests/e2e/test_context_gatherer.py`).
- [x] **Per-agent latency tracking** → REL-05 (`_query_watcher` / `_query_librarian` now populate `_latency_ms`; `gather()` populates `agent_latency`)
- [x] **Replace with LangGraph worker subgraph** (LGR-01, LGR-02 — graph's `context_worker_node` runs watcher/librarian/repomix in parallel)
- [x] `/context-gatherer` IPC runs supervisor → workers → merge_context only (`daemon/server.py:_handle_context_gatherer` uses `graph.gather_context()`)

### Phase 10 — Pipeline, rules, cache, and providers ✅ → LangGraph nodes

- [x] Legacy pipeline stages in `daemon/pipeline.py`; passes `context=context_result` to `analyze_risk()`.
- [x] **Provider prompts include gathered context** → REL-01, REL-02 (`risk_analyzer_node`/`remediation_node` in graph pass `context=`; `_format_context()` renders watcher+librarian data into prompts; verified by `TestProviderContextWiring`)
- [x] **Migrate stages to LangGraph nodes** (LGR-01)
- [x] **Broaden `_needs_context()` heuristics** → PIP-01 (git, docker, docker-compose, pip, npm, yarn, pnpm triggers; verified by `TestNeedsContext`)

### Phase 11 — Analysis, status, and error UI ✅

- [x] `ui/analysis.py`, `ui/status.py`, `ui/banner.py`, `cli/version.py` (`VERSION = "2.0.0"`).
- [x] Unit tests in `tests/unit/test_ui.py` (analysis, status, banner rendering).
- [x] **Error next-steps panel** → UI-01 (`print_error_panel` accepts `next_steps` param; verified by `TestErrorPanel`)
- [x] **`last_health_check` in status** → UI-02 (`/status` response includes `last_health_check`; `render_status` displays it; verified by `TestHealthCheckInStatus`)
- [x] **`--no-color` mode** → UI-03 (`_get_console()` returns `_plain_console` when `no_color=True`; verified by `TestNoColorMode`)

### Phase 12 — Shell adapters ✅

- [x] Bash/zsh/PowerShell adapters, `--quiet analyze`, zsh duplicate fix.
- [x] `adapters/__init__.py` helpers; `tests/unit/test_adapters.py` (file existence, syntax validation).
- [x] `cli/commands/install.py` and `uninstall.py` exist (Click commands).
- [x] **Quoting/flags E2E through sourced adapters** → ADP-01 (adapters use `"$cmd"` / `$Command` to preserve quoting; smoke-tested in `test_adapter_preserves_quoting`)
- [x] **Disabled-daemon shell safety E2E** → ADP-02 (adapters suppress stderr; `test_disabled_daemon_graceful_handling` verifies error suppression)
- [x] **Install/uninstall `--dry-run`** → ADP-03 (parser strips `--dry-run` and sets `parsed.dry_run`; `main.py` passes it to command functions; verified by `TestAdapterParsing`)
- [x] **Wire install/uninstall into CLI** → ADP-04 (`Action.INSTALL` / `Action.UNINSTALL` in parser; `cli/main.py` routes to Click commands)

### Phase 13 — Security hardening ✅

- [x] Structured logs, log rotation, payload validation, project-root boundaries, security tests.
- [x] **IPC session validation** → REL-04 (same as Phase 4 — `daemon/server.py:_validate_ipc_request` validates session ownership)

### Phase 14 — Testing and CI ✅

- [x] **369 tests** across 25 files (unit + e2e); new suites: `test_security`, `test_ui`, `test_agents`, `test_context_gatherer`, `test_librarian`, `test_ipc`, `test_adapters`.
- [x] `.github/workflows/ci.yml` — Linux + Windows matrix, Python 3.10–3.13, e2e on Ubuntu.
- [x] E2E expansions: `test_agent_behaviors`, `test_config_flow`, `test_context_gatherer`, `test_edge_cases`, `test_startup_performance`.
- [x] **Credential-isolated provider/IPC tests** → REL-06 (`tests/conftest.py` now has `_isolate_credentials` autouse fixture that patches `providers.router.load_env` and resets provider globals; `test_fallback_risk_analysis` passes regardless of on-disk credentials)
- [ ] *(Optional)* Performance benchmarks in CI → P2

### Phase 15 — Documentation and release ✅

- [x] Centralized `VERSION = "2.0.0"` in `cli/version.py`.
- [x] `docs/v2-implementation-report.md` (audit snapshot, 2026-06-09).
- [x] **`pyproject.toml` version → `2.0.0`**; added `rich>=13.0.0`, `psutil>=5.9.0`, `watchdog>=4.0.0` to deps → PKG-01, PKG-02
- [x] **README fully documents** v2 lifecycle, migration notes (DOC-01), config/state directory locations (DOC-02), adapter install/uninstall workflow (DOC-03), MVP limitations and parking lot (DOC-04), changelog (DOC-05)
- [ ] Clean install verification, formal release checklist → PKG-03, DOC-05 (post-MVP publishing step)

### Phase 16 — Performance optimizations ✅

- IPC-before-agents startup, `asyncio.Event` for indexing, lifecycle sync fix, cache locking, agent Future fix, provider `close()`, watchdog debounce, batched cache saves, 31 new e2e edge-case tests.

---

## MVP Done When

| Criterion | Status |
|-----------|--------|
| Canonical v2 docs only | ✅ |
| `sm enable` → ready via `/status` | ✅ |
| `sm -a <command>` without quotes | ✅ |
| Context within 500ms or partial | ✅ |
| Provider outage → deterministic fallback | ✅ |
| `sm disable` cleans session files | ✅ |
| `sm disable` prints "ShellMate has been disabled." | ✅ DIS-01 |
| Adapter smoke tests pass | ✅ |
| Tests pass without real API keys | ✅ REL-06 (credential isolation fixture) |
| **`sm -a git status` includes git context in analysis** | ✅ REL-01 (context threaded through graph → providers) |
| **Librarian snippets redacted** | ✅ REL-03 |
| **IPC validates session/owner** | ✅ REL-04 |
| **`sm enable` shows Rich startup UI** | ✅ ENB-01 |
| **`agent_latency` tracked in context** | ✅ REL-05 |
| **LangGraph orchestration replaces legacy pipeline** | ✅ LGR-01/02/03 |
| **Watcher + Librarian start concurrently** | ✅ ENB-02 |
| **Docs and packaging ready for 2.0.0 tag** | ✅ (README + pyproject.toml done; formal tag step post-MVP) |

**Formal 2.0.0 release:** all **5 P0** items resolved. Remaining: PKG-03 (clean pip install) and formal release tagging.

---

## Audit Evidence (2026-06-10)

| Check | Result |
|-------|--------|
| **Phase 1 verification** (`test_cli_parser.py`) | **26 passed** |
| **Phase 2 verification** (`test_config.py`, `TestSecretsRedaction`) | **52 passed, 1 skipped** |
| **Phase 3 verification** (`test_session.py`, `test_lifecycle.py`) | **27 passed** |
| **Context gatherer** (`test_context_gatherer.py` unit + e2e) | **10 passed** |
| **Phase 10 verification** (providers, rules, cache, pipeline, parser, sanitizer) | **30 passed** |
| **Phase 8b verification** (`test_analysis_graph.py`) | **33 passed** (incl 13 new PIP-01 + REL-01/02 tests) |
| **Phase 11 verification** (`test_ui.py`) | **18 passed** (incl 7 new UI-01/02/03 tests) |
| **Phase 12 verification** (`test_adapters.py`) | **23 passed** (incl 7 new ADP-03/04 tests) |
| **DIS-01/ENB-02 verification** (`test_disable.py`) | **4 passed** |
| `python -m pytest tests/unit/ -q` | **256 passed, 2 skipped, 0 failed** (31 new tests) |
| `orchestration/` package | Present (LGR-01 ✅) |
| `providers/groq_provider.py` `_format_context()` | Formats context (REL-01 ✅) |
| `providers/openrouter_provider.py` `_format_context()` | Formats context (REL-02 ✅) |
| `providers/` context wiring | `risk_analyzer_node`/`remediation_node` pass `context=` (REL-01/02 ✅) |
| `agents/repomix_backend.py` | Present (REP-01 ✅) |
| `daemon/server.py` IPC validation | `_validate_ipc_request()` (REL-04 ✅) |
| `daemon/server.py` concurrent startup | `asyncio.gather` for watcher + librarian (ENB-02 ✅) |
| `cli/commands/enable.py` | Calls `run_startup_ui()` (ENB-01 ✅) |
| `cli/commands/disable.py` | Prints "ShellMate has been disabled." (DIS-01 ✅) |
| `cli/parser.py` install/uninstall | `Action.INSTALL`/`UNINSTALL` (ADP-04 ✅) |
| `cli/parser.py` `--dry-run` | Parsed and set on `ParsedCommand` (ADP-03 ✅) |
| `cli/main.py` `--no-color` | `_get_console()` returns `_plain_console` (UI-03 ✅) |
| `pyproject.toml` version | `2.0.0` (PKG-01 ✅); deps include `rich`, `psutil`, `watchdog` (PKG-02 ✅) |
| `tests/conftest.py` | `_isolate_credentials` fixture (REL-06 ✅) |

**All 5 P0 items resolved.** 31 new tests added. Overall 256/258 unit tests passing.

---

## Post-MVP Parking Lot

*Refs: requirements doc section 9*

- [x] **Agent enrichment & UX (2.1.0)** — LLM supervisor, command guide, enable/analysis UX → [`docs/agent-enrichment-plan/tasks.md`](agent-enrichment-plan/tasks.md)
- [ ] Persistent index with smart invalidation
- [ ] Multi-session / multi-directory daemon
- [ ] User plugin API and dynamic third-party agents
- [ ] `/deep-research`, `sm research`
- [ ] Fuzzy / semantic search and embeddings
- [ ] `sm providers`
- [ ] IDE integrations and collaboration features
- [ ] macOS CI runner
- [ ] Continuous performance benchmarks
- [ ] JSON Schema validation for IPC contracts
- [ ] Optional Unix domain socket IPC transport
- [ ] System keychain storage for API keys
