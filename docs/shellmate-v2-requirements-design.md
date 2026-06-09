# ShellMate v2.0 MVP — Requirements & Design

**Status:** MVP design source of truth (feasibility-adjusted)  
**Version target:** 2.0.0  
**Last updated:** 2026-06-09

This document is the single requirements and design plan for ShellMate v2.0.  
Implementation checklist: [`v2-implementation-tasks.md`](v2-implementation-tasks.md)  
OpenCode step-by-step guide: [`v2-release-tracker.md`](v2-release-tracker.md)

---

## 0. Product Vision

ShellMate is a **session-based, context-aware command safety layer** for the terminal.

1. **Analyze:** `sm -a <command>` — everything after `-a` is the command. No wrapping quotes.
2. **Initialize:** `sm enable` — CLI shows Rich loading until core subsystems are ready, then greets with usage.
3. **Multi-agent orchestration:** **[LangGraph](https://langchain-ai.github.io/langgraph/)** coordinates specialist agents (Watcher, Librarian) and analysis steps (rules, risk, remediation).
4. **Exit:** `sm disable` — stop daemon, delete session data, print **"ShellMate has been disabled."**

Session knowledge (Repomix pack, env snapshot) exists **only between enable and disable**.

---

## 1. Feasibility Audit (2026-06-09)

### 1.1 Verdict

| Overall | Assessment |
|---------|------------|
| **Ship v2.0 MVP** | **Feasible** — core infra ~85% built; LangGraph refactor + Repomix + polish ~1–2 weeks |
| **LangGraph orchestration** | **Feasible** — wrap existing agents as graph nodes; supervisor routing can be deterministic for MVP |
| **Greenfield rebuild** | **Not needed** — migrate `pipeline.py` + `context_gatherer.py` into LangGraph |

### 1.2 Already implemented (reuse as graph nodes)

| Capability | Module | LangGraph role |
|------------|--------|----------------|
| `sm -a` parsing | `cli/parser.py` | Pre-graph CLI ✅ |
| Daemon + IPC | `daemon/server.py` | Invokes compiled graph ✅ |
| Watcher agent | `agents/watcher.py` | **Graph node:** `watcher` |
| Librarian agent | `agents/librarian.py` | **Graph node:** `librarian` (→ Repomix) |
| Rules / sanitizer / cache | `rules/`, `sanitizer/`, `cache/` | **Graph nodes:** deterministic pre-steps |
| Providers | `providers/router.py` | **Graph nodes:** `risk_analyzer`, `remediation` |
| Custom orchestration (to replace) | `daemon/pipeline.py`, `agents/context_gatherer.py` | → **`orchestration/analysis_graph.py`** |

### 1.3 LangGraph orchestration (author decision 2026-06-09)

**Decision:** Multi-agent orchestration uses **LangGraph `StateGraph`**, not ad-hoc asyncio pipeline code.

| Aspect | MVP choice | Rationale |
|--------|------------|-----------|
| **Pattern** | **Supervisor + worker nodes** | Watcher and Librarian are workers; analysis flow is supervised |
| **Supervisor routing** | **Deterministic heuristics** (P0) | Works without API keys; predictable; fits 500ms budget |
| **LLM supervisor** | Optional (P2) | Route via LLM only when Groq key present and command is ambiguous |
| **Graph API** | **`StateGraph` (manual)** | Full control over parallel fan-out, early exit, timeouts — not `create_supervisor` alone |
| **State** | Shared `AnalysisState` TypedDict | Command, contexts, risk, remediation, errors, stage latencies |
| **Parallel workers** | LangGraph fan-out to `watcher` + `librarian` | Replace `context_gatherer.gather()` |
| **Early exit** | Conditional edges after `rules` / `cache` nodes | Preserve current pipeline optimizations |
| **Compiled graph** | Singleton compiled at daemon startup | `graph.ainvoke(state)` from IPC analyze handler |
| **Dependencies** | `langgraph`, `langchain-core` | Add to `pyproject.toml`; no full LangChain required |

**Feasibility:** Existing agent classes stay unchanged; orchestration layer is a **refactor** (~M effort), not a rewrite of Watcher/Librarian.

### 1.4 Repomix for Session RAG (author decision 2026-06-09)

Librarian worker node uses **Repomix** pack + grep (see FR-4/FR-5). Node.js 18+ required; legacy keyword index as fallback.

### 1.5 Other constraints (unchanged)

- **Ready** = IPC + agents initialized + Repomix pack (or fallback) + provider config checked — not LLM network ping
- FAISS command cache: background only; not part of LangGraph critical path
- API keys optional; rule fallback via graph `risk_analyzer` node

### 1.6 Legacy code stance

| Component | MVP stance |
|-----------|------------|
| `daemon/pipeline.py` | **Deprecate** → thin wrapper calling LangGraph |
| `agents/context_gatherer.py` | **Deprecate** → logic moves into graph supervisor + worker nodes |
| `agents/base.py` AgentManager | **Keep** — workers still use asyncio agents under graph nodes |
| `cache/semantic_cache.py` | Keep as graph `cache_lookup` node |
| `documentation/context7_client.py` | Optional post-remediation node (P2); skip if no key |

---

## 2. MVP Goal

- `sm -a <command>` with LangGraph-orchestrated multi-agent analysis
- Repomix-backed Librarian session RAG
- Watcher + Librarian as parallel LangGraph worker nodes
- Deterministic supervisor routing + rule fallback (no API key required)
- Rich enable/disable UX

---

## 3. MVP Scope

### In scope

| Area | MVP behavior |
|------|----------------|
| Orchestration | **LangGraph `StateGraph`** — supervisor pattern with worker nodes |
| CLI | `sm -a`, `sm enable`, `sm disable`, `sm status`, `sm config` |
| Workers | Watcher (env/git), Librarian (Repomix pack + grep) |
| Analysis nodes | sanitize, parse, rules, cache, risk_analyzer, remediation, format |
| Supervisor | Deterministic routing: which workers to invoke per command |
| Session RAG | Repomix pack in session dir; deleted on disable |
| Providers | Groq + OpenRouter when keyed; graph fallback nodes |
| IPC | analyze invokes graph; `/context-gatherer` invokes worker subgraph |
| Tests | Graph unit tests with mocked nodes; e2e unchanged |

### Out of scope

- LLM-based supervisor routing (P2)
- LangGraph Studio / LangSmith required for MVP (optional for dev)
- Persistent graph checkpointing across daemon restarts
- v1 CLI, multi-session daemon, Librarian embeddings

---

## 4. Constraints And Decisions

| Decision | Choice |
|----------|--------|
| **Orchestration** | **LangGraph `StateGraph`** in `orchestration/analysis_graph.py` |
| **Supervisor (P0)** | Deterministic Python function — not an LLM call |
| **Workers** | `watcher`, `librarian` — LangGraph nodes wrapping existing agents |
| **State schema** | `AnalysisState` TypedDict (see §9) |
| **Invocation** | `await analysis_graph.ainvoke(initial_state)` from IPC handler |
| **Context budget** | Graph-level `asyncio.wait` / timeout on worker fan-out — **500ms** |
| **Session RAG** | Repomix via Librarian node |
| **Node.js** | 18+ for Repomix |
| **Runtime** | Python 3.10+ |
| **Dependencies** | `langgraph>=0.2`, `langchain-core>=0.3` |

---

## 5. Terminology

| Term | Meaning |
|------|---------|
| **Analysis graph** | Compiled LangGraph `StateGraph` for one `sm -a` request |
| **Supervisor node** | Graph node that decides which workers to run (deterministic in MVP) |
| **Worker node** | Watcher or Librarian — gathers context, returns to merge node |
| **Main flow** | sanitize → parse → rules → cache → supervisor → workers → risk → remediation → format |
| **Session RAG** | Repomix pack in session dir (Librarian worker) |
| **Early exit** | Conditional edge to `format_response` → END (skip workers/LLM) |

---

## 6. Functional Requirements

### FR-1: CLI — `sm -a` (P0) ✅

Unchanged. Graph runs inside daemon on analyze IPC request.

---

### FR-2: Enable Flow (P0) ⚠️

Unchanged UX. Daemon startup must:

1. Start Watcher + Librarian agents (workers need live services)
2. Run Repomix pack (Librarian init)
3. **Compile LangGraph once:** `build_analysis_graph()` → store singleton
4. Report `startup_stage == "ready"`

LangGraph compile is fast (no LLM init in graph for MVP supervisor).

---

### FR-3 – FR-6: Disable, Repomix, Librarian, Watcher

Unchanged from prior spec. Workers are invoked **via LangGraph nodes**, not direct `context_gatherer` calls.

---

### FR-7: LangGraph Multi-Agent Orchestration (P0) ⚠️ **New — replaces pipeline**

**Module:** `orchestration/analysis_graph.py`  
**State:** `orchestration/state.py` → `AnalysisState`

#### Graph nodes (MVP)

| Node | Type | Description |
|------|------|-------------|
| `sanitize` | Deterministic | Typo/syntax check |
| `parse` | Deterministic | Command structure |
| `rules` | Deterministic | YAML rule engine |
| `cache_lookup` | Deterministic | FAISS semantic cache |
| `supervisor` | **Supervisor** | Decide workers: `watcher`, `librarian`, both, or none |
| `watcher` | **Worker** | Call Watcher agent; write `state["watcher"]` |
| `librarian` | **Worker** | Call Librarian agent / Repomix grep; write `state["librarian"]` |
| `merge_context` | Deterministic | Merge worker outputs; enforce 500ms; set `partial` / `timed_out` |
| `risk_analyzer` | LLM or fallback | Groq with full context in prompt |
| `remediation` | LLM or fallback | OpenRouter with context |
| `format_response` | Deterministic | Build IPC/CLI response dict |

#### Graph edges (MVP)

```text
START → sanitize → parse → rules
                              ├─ [matched ≥0.9] → format_response → END
                              └─ continue → cache_lookup
                                              ├─ [hit] → format_response → END
                                              └─ continue → supervisor
                                                              ├─ fan-out → watcher ──┐
                                                              ├─ fan-out → librarian ┼→ merge_context
                                                              └─ [no workers] ───────┘
                                                                    → risk_analyzer → remediation → format_response → END
```

#### Supervisor routing (deterministic P0)

```python
def supervisor_route(state: AnalysisState) -> list[str]:
    cmd = state["command"]
    workers = []
    workers.append("watcher")  # env/git context for most commands
    if needs_librarian(cmd):   # file paths, rm, cat, etc.
        workers.append("librarian")
    return workers
```

P2: replace with LLM supervisor when `GROQ_API_KEY` set and `config.use_llm_supervisor=true`.

#### Worker node contract

Each worker node:

1. Reads `state["command"]`
2. Calls existing agent via `AgentManager` / `get_watcher_agent()` / `get_librarian_agent()`
3. Returns partial state update `{ "watcher": {...} }` or `{ "librarian": {...} }`
4. Catches exceptions → `{ "errors": {"watcher": "..."} }` — never raises to crash graph

#### Integration points

| Caller | Action |
|--------|--------|
| `daemon/server.py` analyze handler | `result = await graph.ainvoke({"command": cmd, ...})` |
| `daemon/pipeline.py` | Thin wrapper: `return await run_analysis_graph(command)` |
| `/context-gatherer` IPC | Run subgraph: `supervisor → workers → merge_context` only |
| Tests | Mock worker nodes; test routing and early exit |

#### Deprecations

- `agents/context_gatherer.py` — logic absorbed into graph; keep thin wrapper for tests until migrated
- Direct `context_gatherer.gather()` calls from pipeline — remove after LGR-01

---

### FR-8: Context Gathering (P0) — via LangGraph

- Implemented as **supervisor + parallel worker nodes + merge_context**
- 500ms timeout on worker fan-out (graph interrupt or `asyncio.wait` inside merge node)
- Response fields unchanged: `watcher`, `librarian`, `timed_out`, `errors`, `partial`, `latency_ms`, `agent_latency_ms`
- `/context-gatherer` IPC runs worker subgraph only

---

### FR-9 – FR-11: UI, Adapters, Session

Unchanged.

---

## 7. Non-Functional Requirements

| Metric | Target |
|--------|--------|
| Graph invoke (no LLM) | < 50ms excluding workers |
| Worker fan-out | 500ms max (merge_context) |
| Full analysis (with LLM) | < 6s |
| Graph compile at startup | < 1s |

**Reliability:** Worker node exceptions caught; graph always reaches `format_response` with fallback risk.

**Testing:** Unit-test graph routing with `langgraph` in-memory; no real API keys.

---

## 8. Architecture

```text
User: sm -a <command>
  → CLI → IPC analyze
  → daemon/server.py
  → analysis_graph.ainvoke(AnalysisState)
        │
        ├─ sanitize → parse → rules → cache (early exit edges)
        │
        ├─ supervisor (deterministic routing)
        │     ├─ watcher node ────┐
        │     └─ librarian node ──┼─ merge_context (500ms)
        │                         │
        ├─ risk_analyzer node (Groq / fallback)
        ├─ remediation node (OpenRouter / fallback)
        └─ format_response → JSON to CLI

Daemon startup (sm enable):
  IPC → Watcher.start() + Librarian.repomix_pack() [parallel]
  → build_analysis_graph() [compile once]
  → ready

Agents (long-lived services):
  WatcherAgent, LibrarianAgent — unchanged; graph nodes call them
```

### Package layout (target)

```text
orchestration/
  __init__.py
  state.py              # AnalysisState TypedDict
  analysis_graph.py     # build_analysis_graph(), get_analysis_graph()
  nodes/
    deterministic.py    # sanitize, parse, rules, cache, format
    supervisor.py       # supervisor_route, supervisor_node
    workers.py          # watcher_node, librarian_node, merge_context
    providers.py        # risk_analyzer_node, remediation_node
```

---

## 9. Data Contracts

### AnalysisState (LangGraph shared state)

```python
class AnalysisState(TypedDict, total=False):
    command: str
    request_id: str
    cwd: str
    # Pre-processing
    sanitized_command: str
    parsed: dict
    rule_result: dict
    cache_hit: bool
    early_exit: Optional[str]
    # Supervisor / workers
    workers_requested: list[str]
    watcher: dict
    librarian: dict
    timed_out: list[str]
    errors: dict
    partial: bool
    agent_latency_ms: dict
    # Analysis output
    risk: str
    confidence: float
    message: str
    explanation: str
    alternatives: list
    context_used: dict
    stages: dict
    # Control
    next: str  # routing key for conditional edges
```

### IPC analyze response

Unchanged shape (derived from final `AnalysisState` in `format_response` node).

### Context gatherer response

Unchanged — produced by partial graph run through `merge_context`.

---

## 10. Acceptance Criteria

### P0

| ID | Criterion |
|----|-----------|
| AC-1 | `sm -a echo hi` works |
| AC-LGR-1 | Analyze IPC invokes LangGraph; no direct `context_gatherer.gather()` in hot path |
| AC-LGR-2 | Supervisor invokes Watcher + Librarian in parallel for `sm -a rm ./file` |
| AC-LGR-3 | Rule match ≥0.9 early-exits graph before workers |
| AC-LGR-4 | Graph completes with fallback when no API keys |
| AC-LGR-5 | Worker timeout → `partial=true`, analysis still returns |
| AC-3 | Enable loading + greeting |
| AC-4 | Disable message |
| AC-5 | Repomix pack lifecycle |

### P1

| ID | Criterion |
|----|-----------|
| AC-LGR-6 | Graph routing unit tests with mocked workers |
| AC-10 | Context in provider prompts via graph state |

---

## 11. Remaining Work (prioritized)

### P0

| ID | Task | Effort |
|----|------|--------|
| **LGR-01** | **LangGraph: `AnalysisState`, nodes, `build_analysis_graph()`, wire IPC** | **L** |
| LGR-02 | Deprecate `context_gatherer.py`; migrate tests | M |
| LGR-03 | `pipeline.py` → thin wrapper over graph | S |
| REP-01 | Repomix Librarian backend | M |
| REL-01/02 | Provider nodes use graph state context | S |
| ENB-01/02 | Enable UX + parallel agent startup | S |
| DIS-01 | Disable message | S |
| REL-04 | IPC session validation | S–M |
| REL-06 | Test credential isolation | S |

**L** = 2–3 days, **M** = 1 day, **S** = hours

### P1

WCH, UI, ADP, PKG, DOC, graph unit tests, optional LangSmith tracing

### P2

- LLM-based supervisor routing
- LangGraph checkpointing / persistence
- Context7 as graph node

---

## 12. Migration Plan (pipeline → LangGraph)

1. Add `langgraph` + `langchain-core` to `pyproject.toml`
2. Create `orchestration/state.py` with `AnalysisState`
3. Implement deterministic nodes by extracting logic from `pipeline.py`
4. Implement worker nodes calling existing Watcher/Librarian agents
5. Implement supervisor + parallel edges + merge_context timeout
6. Wire `daemon/server.py` analyze handler to `graph.ainvoke`
7. Run existing e2e tests — must pass without behavior change
8. Remove dead code from `context_gatherer.py` / slim `pipeline.py`

---

## 13. Post-MVP Parking Lot

- LLM supervisor (Groq routes workers dynamically)
- LangGraph Studio visual debugging
- LangSmith tracing in CI
- Hierarchical graphs (supervisor of supervisors)
- Persistent RAG, multi-session, macOS CI, keychain, etc.

---

## 14. Author Notes → Spec Mapping

| # | Note | Spec |
|---|------|------|
| 1 | `sm -a` no quotes | FR-1 |
| 2 | Session RAG (Repomix) | FR-4, Librarian worker node |
| 3 | Librarian → Main Agent | FR-7 LangGraph supervisor → workers → risk |
| 4 | Watcher on demand | FR-7 supervisor routing |
| 5 | Rich loading | FR-2 |
| 6 | Enable until live | FR-2 |
| 7 | Disable message | FR-3 |
| 8 | Parallel agents | FR-7 LangGraph fan-out + enable startup |
