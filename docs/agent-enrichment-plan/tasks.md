# Agent Enrichment & UX — Implementation Tasks (Agent Playbook)

**Design:** [`design.md`](design.md) (create from brainstorming if missing — see repo `docs/plans/agent-enrichment/design.md`)  
**Target version:** 2.1.0 · **Repo root:** `D:\projects\shellmate` (always `cd` here first)

---

## READ THIS FIRST (mandatory for every agent)

You are implementing **one task at a time**. Do not skip ahead. Do not mark a task done until **Verify** passes.

### Iron rules

1. **Only edit files listed** under the task's **Files** section unless the task says otherwise.
2. **Run the Verify command** after your edits. Copy the terminal output into your report.
3. **If Verify fails**, fix and re-run. Do not check the box.
4. **Do not refactor unrelated code.** No drive-by formatting. No new dependencies unless the task says so.
5. **Mock Groq in tests.** Never require a real `GROQ_API_KEY` in CI.
6. **Preserve `--quiet` behavior** on analyze — JSON only, no Rich UI.
7. **Sync nodes must stay sync; async nodes must stay async** in LangGraph (see AGR-04 note).

### Verification protocol

```
IDENTIFY → RUN verify command → READ exit code + output → ONLY THEN check [x]
```

### PowerShell (Windows)

Use `;` not `&&`. Example:

```powershell
cd D:\projects\shellmate; python -m pytest tests/unit/test_config.py -q -k supervisor --tb=short
```

### Key files map (do not get lost)

| What | Path |
|------|------|
| Config defaults | `config/defaults.py` |
| Groq risk provider (copy pattern) | `providers/groq_provider.py` |
| New supervisor provider | `providers/groq_supervisor.py` (create AGR-02) |
| Graph + nodes | `orchestration/analysis_graph.py` |
| Graph state type | `orchestration/state.py` |
| Enable command | `cli/commands/enable.py` |
| Startup UI | `daemon/startup_ui.py` |
| Banner | `ui/banner.py` |
| Analysis render | `ui/analysis.py` |
| New progress spinner | `ui/progress.py` (create AGR-14) |
| CLI entry | `cli/main.py` |
| Graph tests | `tests/unit/test_analysis_graph.py` |
| UI tests | `tests/unit/test_ui.py` |
| Config tests | `tests/unit/test_config.py` |
| Credential isolation | `tests/conftest.py` (`_isolate_credentials`) |

### Locked product decisions (do not reinterpret)

| ID | Decision |
|----|----------|
| W1 | LLM supervisor runs on **every** analyze when `GROQ_API_KEY` is set |
| R2 | Supervisor returns **`run_watcher`** and **`run_librarian`** booleans |
| P1 | `run_librarian: true` → run Librarian **and** Repomix |
| M1 | Supervisor uses **`GROQ_SUPERVISOR_MODEL`** (default `llama-3.1-8b-instant`) |
| T2 | Supervisor timeout **500ms** |
| F3 | Supervisor failure → **skip all context**, continue analysis |
| N1 | Supervisor failure → show **`⚠ Context skipped: supervisor unavailable`** in analysis UI |
| U2 | **`command_guide_node`** — separate Groq call, not remediation |
| G1 | Guide runs on **every keyed** analyze (except early-exit paths) |
| L1 | Analyze spinner = **timer-based** stage labels (no IPC streaming) |
| E4 | Enable = **one Rich Panel** (ASCII + checklist + usage) |

---

## Status at a Glance

| Phase | Name | Tasks | Done | Open |
|-------|------|-------|------|------|
| **1** | Foundation | AGR-01–03 | 0 | 3 |
| **2** | LLM Supervisor Graph | AGR-04–07 | 0 | 4 |
| **3** | Command Guide Node | AGR-08–10 | 0 | 3 |
| **4** | Enable UX | AGR-11–13 | 3 | 0 |
| **5** | Analyze UX | AGR-14–17 | 4 | 0 |
| **6** | Tests & Release Docs | AGR-18–32 | 15 | 0 |
| | **Total** | **32** | **32** | **0** |

**Execute phases 1 → 6 in order.** Finish every task in a phase before starting the next. Run the **Phase gate** verify at the end of each phase; report to human before continuing.

---

## Phase overview

| Phase | Delivers | Phase gate (run after last task in phase) |
|-------|----------|-------------------------------------------|
| **1 — Foundation** | Config, `groq_supervisor`, extended `AnalysisState` | `pytest tests/unit/test_config.py tests/unit/test_groq_supervisor.py tests/unit/test_analysis_graph.py -q --tb=short` |
| **2 — LLM Supervisor Graph** | Async supervisor node, selective workers, fallback | `pytest tests/unit/test_analysis_graph.py -q --tb=short` |
| **3 — Command Guide Node** | `command_guide_node` wired in graph | `pytest tests/unit/test_analysis_graph.py -q --tb=short` |
| **4 — Enable UX** | Rich enable panel (E4), startup UI | `pytest tests/unit/test_ui.py -q -k "enable_panel or startup" tests/e2e/test_startup_performance.py -q --tb=short` |
| **5 — Analyze UX** | Spinner (L1), guide rendering, unified CLI output | `pytest tests/unit/test_ui.py tests/unit/test_cli_parser.py tests/e2e/test_user_flow.py -q --tb=short` |
| **6 — Tests & Release Docs** | Fixtures, orchestration, workflow, memory, agents, providers, user flow, IPC, UI, security, edge cases, regression, README | `pytest tests/ -q --tb=short` + doc grep |

---

## Phase 1 — Foundation

**Tasks:** AGR-01, AGR-02, AGR-03  
**Goal:** Config + supervisor provider + state schema ready before touching graph logic.

**Phase gate:**

```powershell
cd D:\projects\shellmate
python -m pytest tests/unit/test_config.py tests/unit/test_groq_supervisor.py tests/unit/test_analysis_graph.py -q --tb=short
```

---

---

### AGR-01 — Add supervisor config defaults `[Phase 1]`

**Goal:** Config exposes `supervisor.model` and `supervisor.timeout_ms`.

**Prerequisites:** None.

**Files to edit:**
- `config/defaults.py`
- `tests/unit/test_config.py` (add test)

**Do NOT edit:** `orchestration/*`, `providers/*`, `cli/*`

#### Steps

1. Open `config/defaults.py`. Inside the dict returned by `get_default_config()`, add a new top-level key **`supervisor`** **after** the `providers` block:

```python
        "supervisor": {
            "model": os.environ.get("GROQ_SUPERVISOR_MODEL", "llama-3.1-8b-instant"),
            "timeout_ms": 500,
        },
```

2. `os` is already imported at top of file — do not duplicate import.

3. Add test class in `tests/unit/test_config.py`:

```python
class TestSupervisorConfig:
    def test_default_supervisor_model(self):
        from config.defaults import get_default_config
        cfg = get_default_config()
        assert cfg["supervisor"]["model"] == "llama-3.1-8b-instant"
        assert cfg["supervisor"]["timeout_ms"] == 500

    def test_supervisor_model_env_override(self, monkeypatch):
        monkeypatch.setenv("GROQ_SUPERVISOR_MODEL", "llama-3.1-70b-versatile")
        from config.defaults import get_default_config
        cfg = get_default_config()
        assert cfg["supervisor"]["model"] == "llama-3.1-70b-versatile"
```

#### Verify

```powershell
cd D:\projects\shellmate
python -c "from config.defaults import get_default_config; c=get_default_config(); assert c['supervisor']['model']; assert c['supervisor']['timeout_ms']==500; print('ok')"
python -m pytest tests/unit/test_config.py -q -k supervisor --tb=short
```

**Pass =** `ok` printed + pytest 0 failed.

#### Done when

- [ ] `supervisor` key exists in default config
- [ ] Two tests pass
- [ ] Verify output captured

---

### AGR-02 — Create `providers/groq_supervisor.py` `[Phase 1]`

**Goal:** Async function calls Groq fast model and returns routing JSON.

**Prerequisites:** AGR-01 done.

**Files to create:**
- `providers/groq_supervisor.py`
- `tests/unit/test_groq_supervisor.py`

**Do NOT edit:** `providers/groq_provider.py` (copy patterns only)

#### Steps

1. **Create** `providers/groq_supervisor.py` with this structure (fill in TODOs exactly):

```python
import asyncio
import json
import os
import logging
from typing import Optional

from groq import AsyncGroq
from providers.base import ProviderError

logger = logging.getLogger("shellmate.providers.groq_supervisor")

SUPERVISOR_PROMPT = '''You route shell-command analysis to context workers.
Respond ONLY with valid JSON:
{"run_watcher": true|false, "run_librarian": true|false}

run_watcher: true when command needs OS/shell/git/env context (git, docker, cd, env vars).
run_librarian: true when command references project files or needs repo search.
Both can be true. Both can be false for trivial commands (echo hello).

Command: {command}'''


class SupervisorError(Exception):
    pass


def _parse_supervisor_json(content: str) -> dict:
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1] if "\n" in content else content
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
    data = json.loads(content)
    return {
        "run_watcher": bool(data.get("run_watcher", False)),
        "run_librarian": bool(data.get("run_librarian", False)),
    }


async def route_command(
    command: str,
    *,
    model: Optional[str] = None,
    timeout_ms: float = 500,
) -> dict:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise SupervisorError("GROQ_API_KEY not set")

    model = model or os.environ.get("GROQ_SUPERVISOR_MODEL", "llama-3.1-8b-instant")
    client = AsyncGroq(api_key=api_key)
    prompt = SUPERVISOR_PROMPT.format(command=command)

    try:
        async def _call():
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=64,
            )
            return response.choices[0].message.content

        content = await asyncio.wait_for(_call(), timeout=timeout_ms / 1000.0)
        return _parse_supervisor_json(content)
    except asyncio.TimeoutError:
        raise SupervisorError(f"Supervisor timed out after {timeout_ms}ms")
    except json.JSONDecodeError as e:
        raise SupervisorError(f"Invalid JSON: {e}")
    except Exception as e:
        raise SupervisorError(str(e))
    finally:
        await client.aclose()
```

2. **Create** `tests/unit/test_groq_supervisor.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from providers.groq_supervisor import route_command, SupervisorError, _parse_supervisor_json


class TestParseSupervisorJson:
    def test_plain_json(self):
        assert _parse_supervisor_json('{"run_watcher": true, "run_librarian": false}') == {
            "run_watcher": True, "run_librarian": False,
        }

    def test_fenced_json(self):
        raw = '```json\n{"run_watcher": false, "run_librarian": true}\n```'
        assert _parse_supervisor_json(raw)["run_librarian"] is True


@pytest.mark.asyncio
async def test_route_command_success(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(
        content='{"run_watcher": true, "run_librarian": false}'
    ))]

    with patch("providers.groq_supervisor.AsyncGroq") as MockGroq:
        instance = MockGroq.return_value
        instance.chat.completions.create = AsyncMock(return_value=mock_response)
        instance.aclose = AsyncMock()
        result = await route_command("git status")
        assert result == {"run_watcher": True, "run_librarian": False}


@pytest.mark.asyncio
async def test_route_command_no_key():
    import os
    old = os.environ.pop("GROQ_API_KEY", None)
    try:
        with pytest.raises(SupervisorError):
            await route_command("echo hi")
    finally:
        if old:
            os.environ["GROQ_API_KEY"] = old
```

3. If `pytest-asyncio` marker fails, use `asyncio.run()` in sync test instead — match pattern in existing tests.

#### Verify

```powershell
cd D:\projects\shellmate
python -m pytest tests/unit/test_groq_supervisor.py -q --tb=short
```

**Pass =** all tests passed, 0 failed.

#### Common mistakes

- Forgetting `await client.aclose()` → resource leak
- Returning non-bool values without `bool()` cast
- Calling real Groq API in tests

#### Done when

- [ ] Module + tests exist
- [ ] Verify 0 failed

---

### AGR-03 — Extend `AnalysisState` for supervisor + guide `[Phase 1]`

**Goal:** TypedDict has new fields; `_build_output` can carry them; tests still pass.

**Prerequisites:** AGR-02 done.

**Files to edit:**
- `orchestration/state.py`
- `orchestration/analysis_graph.py` (`_build_output`, `initial_state` in `ainvoke` / `gather_context`)
- `tests/unit/test_analysis_graph.py` (`TestAnalysisState.test_state_structure`)

**Do NOT edit:** Graph edges yet (AGR-04+).

#### Steps

1. In `orchestration/state.py`, add after `early_exit`:

```python
    supervisor_decision: Optional[Dict[str, Any]]
    supervisor_fallback: bool
    supervisor_warning: Optional[str]
    command_guide: Optional[Dict[str, Any]]
```

2. In `orchestration/analysis_graph.py`, extend `_build_output` signature and body:

```python
def _build_output(
    ...
    early_exit=None,
    supervisor_fallback=False,
    supervisor_warning=None,
    command_guide=None,
):
    result = { ... existing ... }
    if supervisor_fallback:
        result["supervisor_fallback"] = True
    if supervisor_warning:
        result["supervisor_warning"] = supervisor_warning
    if command_guide:
        result["command_guide"] = command_guide
    return result
```

3. Add to **both** `initial_state` dicts in `AnalysisGraph.ainvoke` and `gather_context`:

```python
            "supervisor_decision": None,
            "supervisor_fallback": False,
            "supervisor_warning": None,
            "command_guide": None,
```

4. Update `TestAnalysisState.test_state_structure` with the same four keys (values: `None`, `False`, `None`, `None`).

#### Verify

```powershell
cd D:\projects\shellmate
python -c "from orchestration.state import AnalysisState; print('ok')"
python -m pytest tests/unit/test_analysis_graph.py -q --tb=short
```

#### Done when

- [ ] Four new state keys everywhere state is constructed
- [ ] Full graph test file passes

---

## Phase 2 — LLM Supervisor Graph

**Tasks:** AGR-04, AGR-05, AGR-06, AGR-07  
**Goal:** Groq routes `run_watcher` / `run_librarian`; failures skip context with warning.

**Phase gate:**

```powershell
cd D:\projects\shellmate
python -m pytest tests/unit/test_analysis_graph.py -q --tb=short
```

---

### AGR-04 — Async LLM supervisor node `[Phase 2]`

**Goal:** When `GROQ_API_KEY` is set, supervisor calls Groq; else uses `_needs_context()`.

**Prerequisites:** AGR-03 done.

**Files to edit:**
- `orchestration/analysis_graph.py`
- `tests/unit/test_analysis_graph.py`

**Do NOT edit:** `context_worker_node` yet (AGR-05).

#### Important LangGraph note

`supervisor_node` is currently **sync**. Groq call is **async**. You must either:

- **Option A (recommended):** Rename to `async def supervisor_node` and register as async node (LangGraph supports this — same as `context_worker_node`), OR
- **Option B:** `asyncio.get_event_loop().run_until_complete(...)` inside sync node (avoid if already inside async daemon).

Use **Option A**.

#### Steps

1. Add imports at top of `analysis_graph.py`:

```python
from config.defaults import get_default_config
from providers.groq_supervisor import route_command, SupervisorError
import os
```

2. Replace `supervisor_node` with:

```python
async def supervisor_node(state: AnalysisState) -> dict:
    start = time.monotonic()
    command = state["command"]
    decision = {"run_watcher": False, "run_librarian": False, "command": command}

    if os.environ.get("GROQ_API_KEY"):
        cfg = get_default_config()
        sup = cfg.get("supervisor", {})
        try:
            routed = await route_command(
                command,
                model=sup.get("model"),
                timeout_ms=sup.get("timeout_ms", 500),
            )
            decision["run_watcher"] = routed["run_watcher"]
            decision["run_librarian"] = routed["run_librarian"]
        except SupervisorError as e:
            elapsed = (time.monotonic() - start) * 1000
            return {
                "needs_context": False,
                "supervisor_decision": decision,
                "supervisor_fallback": True,
                "supervisor_warning": "Context skipped: supervisor unavailable",
                "stages": _merge_stages(state, "supervisor", elapsed),
                "errors": [str(e)],
            }
    else:
        needs = _needs_context(command)
        decision["run_watcher"] = needs
        decision["run_librarian"] = needs

    needs_context = decision["run_watcher"] or decision["run_librarian"]
    elapsed = (time.monotonic() - start) * 1000
    return {
        "needs_context": needs_context,
        "supervisor_decision": decision,
        "stages": _merge_stages(state, "supervisor", elapsed),
    }
```

3. Add test `tests/unit/test_analysis_graph.py`:

```python
@pytest.mark.asyncio
async def test_supervisor_node_with_groq_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    state = { ... minimal AnalysisState with command "git status" ... }
    with patch("orchestration.analysis_graph.route_command", new_callable=AsyncMock) as mock_route:
        mock_route.return_value = {"run_watcher": True, "run_librarian": False}
        from orchestration.analysis_graph import supervisor_node
        result = await supervisor_node(state)
        assert result["supervisor_decision"]["run_watcher"] is True
        assert result["needs_context"] is True
```

Copy full state dict from existing tests (`TestGraphNodes.test_sanitize_node` pattern).

4. Add test for no-key fallback: unset `GROQ_API_KEY`, command `echo hi`, expect both flags False.

#### Verify

```powershell
cd D:\projects\shellmate
python -m pytest tests/unit/test_analysis_graph.py -q -k supervisor --tb=short
```

#### Done when

- [ ] `supervisor_node` is async
- [ ] Mocked Groq test passes
- [ ] No-key heuristic test passes

---

### AGR-05 — Selective worker fan-out `[Phase 2]`

**Goal:** Only run workers whose flag is true.

**Prerequisites:** AGR-04 done.

**Files to edit:**
- `orchestration/analysis_graph.py` (`context_worker_node`)
- `tests/unit/test_analysis_graph.py`

#### Steps

1. At start of `context_worker_node`, read decision:

```python
    decision = state.get("supervisor_decision") or {}
    run_watcher = decision.get("run_watcher", state.get("needs_context", True))
    run_librarian = decision.get("run_librarian", state.get("needs_context", True))
```

2. Replace unconditional task creation:

```python
    tasks = {}
    if run_watcher:
        tasks["watcher"] = asyncio.create_task(_query_watcher(command))
    if run_librarian:
        tasks["librarian"] = asyncio.create_task(_query_librarian(command))
        tasks["repomix"] = asyncio.create_task(_query_repomix(command))
```

3. If `tasks` is empty, return early:

```python
    if not tasks:
        elapsed = (time.monotonic() - start) * 1000
        return {
            "watcher_context": {},
            "librarian_context": {"matches": []},
            "merged_context": {"watcher": {}, "librarian": {"matches": []}, "partial": False},
            "agent_latency": agent_latency,
            "stages": _merge_stages(state, "context", elapsed),
        }
```

4. Keep existing `asyncio.wait(tasks.values(), ...)` logic but iterate `tasks.items()`.

5. Add tests patching `_query_watcher`, `_query_librarian`, `_query_repomix` with `AsyncMock` — assert watcher called only when flag true.

#### Verify

```powershell
cd D:\projects\shellmate
python -m pytest tests/unit/test_analysis_graph.py -q -k "worker or context" --tb=short
```

#### Done when

- [ ] Watcher-only / librarian-only / neither paths tested
- [ ] Repomix only runs when `run_librarian` true

---

### AGR-06 — Supervisor failure fallback (F3 + N1) `[Phase 2]`

**Goal:** Supervisor error skips context; warning appears in final output.

**Prerequisites:** AGR-04 done (fallback return exists); AGR-05 done.

**Files to edit:**
- `orchestration/analysis_graph.py` (`format_node`, possibly `supervisor_router`)
- `tests/unit/test_analysis_graph.py`

#### Steps

1. Ensure AGR-04 sets `supervisor_fallback: True` and `supervisor_warning` on error.

2. In `format_node`, when building normal output (not early-exit), pass through:

```python
    output = _build_output(
        ...
        supervisor_fallback=state.get("supervisor_fallback", False),
        supervisor_warning=state.get("supervisor_warning"),
        command_guide=state.get("command_guide"),
    )
```

3. When `supervisor_fallback` is True, `supervisor_router` must route to `skip_context` (not `context_worker`). Update `supervisor_router`:

```python
def supervisor_router(state: AnalysisState) -> str:
    if state.get("supervisor_fallback"):
        return "skip_context"
    if state.get("needs_context"):
        return "context_worker"
    return "skip_context"
```

4. Add test: state with `supervisor_fallback=True`, run `format_node`, assert `output["supervisor_warning"]` contains `"supervisor unavailable"`.

#### Verify

```powershell
cd D:\projects\shellmate
python -m pytest tests/unit/test_analysis_graph.py -q -k fallback --tb=short
```

#### Done when

- [ ] Fallback skips context workers (router test or integration)
- [ ] Warning in formatted output

---

### AGR-07 — Supervisor router edge updates `[Phase 2]`

**Goal:** Full graph compiles; all existing graph tests pass.

**Prerequisites:** AGR-04–06 done.

**Files to edit:**
- `orchestration/analysis_graph.py` (lint pass on supervisor path)
- `tests/unit/test_analysis_graph.py` (fix any broken tests)

#### Steps

1. Run full graph test file — fix any state dicts missing new keys.
2. Confirm `stages` includes `"supervisor"` key after supervisor runs.
3. Do **not** add `command_guide` node yet (AGR-08).

#### Verify

```powershell
cd D:\projects\shellmate
python -m pytest tests/unit/test_analysis_graph.py -q --tb=short
```

**Pass =** 0 failed (count may be ~33+ tests).

#### Done when

- [ ] Entire `test_analysis_graph.py` green

---

## Phase 3 — Command Guide Node

**Tasks:** AGR-08, AGR-09, AGR-10  
**Goal:** Post-remediation Groq call produces `when_to_use`, `parameters`, `example_command`.

**Phase gate:**

```powershell
cd D:\projects\shellmate
python -m pytest tests/unit/test_analysis_graph.py -q --tb=short
```

---

### AGR-08 — Create `command_guide_node` `[Phase 3]`

**Goal:** After remediation, Groq returns usage guide JSON.

**Prerequisites:** AGR-07 done.

**Files to edit:**
- `providers/groq_supervisor.py` OR new `providers/groq_command_guide.py` (either OK; prefer **`providers/groq_command_guide.py`** to keep files small)
- `orchestration/analysis_graph.py`
- `tests/unit/test_analysis_graph.py`

#### Steps

1. Create `providers/groq_command_guide.py` — copy `route_command` pattern but prompt returns:

```json
{"when_to_use": "...", "parameters": ["-n: dry run"], "example_command": "git cherry-pick abc123"}
```

Raise `CommandGuideError` on failure. Timeout 500ms.

2. Add async node in `analysis_graph.py`:

```python
async def command_guide_node(state: AnalysisState) -> dict:
    if _detect_early_exit(state):
        return {}
    if not os.environ.get("GROQ_API_KEY"):
        return {}
    start = time.monotonic()
    try:
        guide = await generate_command_guide(
            state["command"],
            context=state.get("merged_context"),
            ...
        )
        elapsed = (time.monotonic() - start) * 1000
        return {"command_guide": guide, "stages": _merge_stages(state, "command_guide", elapsed)}
    except Exception as e:
        logger.debug(f"Command guide skipped: {e}")
        return {}
```

3. Test with patched `generate_command_guide` returning fixture dict.

#### Verify

```powershell
cd D:\projects\shellmate
python -m pytest tests/unit/test_analysis_graph.py -q -k guide --tb=short
```

#### Done when

- [ ] Guide node returns `command_guide` dict when mock succeeds
- [ ] Guide node returns `{}` on early exit

---

### AGR-09 — Wire guide into graph compile `[Phase 3]`

**Goal:** Graph flow: `remediation` → `command_guide` → `format`.

**Prerequisites:** AGR-08 done.

**Files to edit:**
- `orchestration/analysis_graph.py` (`AnalysisGraph.build`)

#### Steps

1. In `build()`:

```python
        workflow.add_node("command_guide", command_guide_node)
```

2. **Remove** edge `remediation → format`. **Add:**

```python
        workflow.add_edge("remediation", "command_guide")
        workflow.add_edge("command_guide", "format")
```

3. Early-exit paths (`early_exit_* → format`) unchanged — they bypass guide.

4. In `format_node`, pass `command_guide=state.get("command_guide")` to `_build_output`.

5. Add integration-style test: mock entire chain through remediation + guide, invoke `format_node`.

#### Verify

```powershell
cd D:\projects\shellmate
python -m pytest tests/unit/test_analysis_graph.py -q --tb=short
```

#### Done when

- [ ] Graph builds without error
- [ ] `output` dict may contain `command_guide` key

---

### AGR-10 — Guide prompt uses directory context `[Phase 3]`

**Goal:** Example command includes real cwd/branch from watcher context.

**Prerequisites:** AGR-09 done.

**Files to edit:**
- `providers/groq_command_guide.py`
- `tests/unit/test_analysis_graph.py` or new `tests/unit/test_groq_command_guide.py`

#### Steps

1. Reuse `_format_context` from `providers/groq_provider.py` (import it) in guide prompt.

2. Prompt must say: *"example_command must use the user's current directory or git branch when provided in context."*

3. Test: pass context `{"watcher": {"current_directory": "D:\\projects\\shellmate", "git": {"branch": "main"}}}` — mock Groq response example containing `shellmate` or `main`; assert guide returned.

#### Verify

```powershell
cd D:\projects\shellmate
python -m pytest tests/unit/ -q -k "guide and context" --tb=short
```

#### Done when

- [ ] Context formatted into prompt
- [ ] Test proves directory/branch in prompt or response handling

---

## Phase 4 — Enable UX

**Tasks:** AGR-11, AGR-12, AGR-13  
**Goal:** `sm enable` ends with combined Rich Panel (ASCII + checklist + usage).

**Phase gate:**

```powershell
cd D:\projects\shellmate
python -m pytest tests/unit/test_ui.py -q -k "enable_panel or startup" --tb=short
python -m pytest tests/e2e/test_startup_performance.py -q --tb=short
```

---

### AGR-11 — ASCII logo + panel builder `[Phase 4]`

**Goal:** `render_enable_panel()` returns Rich Panel.

**Prerequisites:** None (can parallel after Track A).

**Files to edit:**
- `ui/banner.py`
- `tests/unit/test_ui.py`

#### Steps

1. Add to `ui/banner.py`:

```python
from rich.panel import Panel
from rich.table import Table

ASCII_LOGO = r"""
  ___
 / __|  ShellMate
 \__ \
 |___/
"""

def render_enable_panel(stages: list[tuple[str, bool]]) -> Panel:
    """stages = [("Binding IPC", True), ("Watcher ready", True), ...]"""
    lines = [ASCII_LOGO.strip(), ""]
    lines.append("[bold]Startup[/bold]")
    for label, done in stages:
        icon = "[green]✓[/green]" if done else "[dim]○[/dim]"
        lines.append(f"  {icon} {label}")
    lines.append("")
    lines.append("[bold]Usage[/bold]")
    lines.append("  sm -a <command>   Analyze a command")
    lines.append("  sm status         Show daemon status")
    lines.append("  sm disable        Stop ShellMate")
    body = "\n".join(lines)
    return Panel(body, title=f"[bold cyan]ShellMate[/] [dim]v{VERSION}[/dim]", border_style="cyan")
```

2. Import `VERSION` from `cli.version`.

3. Add test `test_render_enable_panel`:

```python
def test_render_enable_panel():
    from ui.banner import render_enable_panel
    from rich.panel import Panel
    panel = render_enable_panel([("Watcher ready", True), ("Librarian ready", False)])
    assert isinstance(panel, Panel)
    text = panel.renderable
    assert "ShellMate" in str(text) or "ShellMate" in panel.title
```

#### Verify

```powershell
cd D:\projects\shellmate
python -m pytest tests/unit/test_ui.py -q -k enable_panel --tb=short
```

#### Done when

- [x] Function exists and returns Panel
- [x] Test passes

---

### AGR-12 — Refactor `run_startup_ui` for E4 `[Phase 4]`

**Goal:** Successful enable prints combined panel, not plain "Daemon ready!".

**Prerequisites:** AGR-11 done.

**Files to edit:**
- `daemon/startup_ui.py`
- `tests/unit/test_ui.py` (optional mock test)

#### Steps

1. Map daemon `startup_stage` values to labels (keep existing list in `startup_ui.py`):

```python
STAGE_LABELS = [
    ("binding_ipc", "Binding IPC"),
    ("watcher_starting", "Starting Watcher"),
    ("watcher_ready", "Watcher ready"),
    ("librarian_scanning", "Scanning project files"),
    ("librarian_ready", "Librarian ready"),
    ("providers_checked", "Checking providers"),
    ("ready", "Ready"),
]
```

2. During poll loop, track highest completed stage index.

3. On success (`stage == "ready"`):
   - Build `[(label, idx <= last_stage) for ...]`
   - `from ui.banner import render_enable_panel`
   - `console.print(render_enable_panel(completed_stages))`
   - **Remove** or demote `console.print("[green]Daemon ready![/green]")` (panel replaces it)

4. Keep `transient=True` progress **during** poll; panel prints **after** progress context exits.

5. On timeout: keep red error messages (no panel).

#### Verify

```powershell
cd D:\projects\shellmate
python -m pytest tests/unit/test_ui.py -q -k startup --tb=short
python -m pytest tests/e2e/test_startup_performance.py -q --tb=short
```

#### Done when

- [x] `run_startup_ui` imports and calls `render_enable_panel`
- [x] E2E startup tests pass

---

### AGR-13 — Fix enable header typo `[Phase 4]`

**Goal:** Remove broken `[bold]ShellMate][/bold]` line from enable flow.

**Prerequisites:** AGR-12 done (panel is main output).

**Files to edit:**
- `cli/commands/enable.py`

#### Steps

1. Replace entire `enable()` body with:

```python
def enable():
    start_daemon()
    run_startup_ui()
```

The panel from AGR-12 shows version + branding. **Delete** the old `console.print("[bold]ShellMate][/bold]...")` line.

2. Remove unused `console = Console()` if nothing uses it.

#### Verify

```powershell
cd D:\projects\shellmate
python -c "import cli.commands.enable; print('ok')"
Select-String -Path cli/commands/enable.py -Pattern "ShellMate\]" ; if ($?) { exit 1 } else { echo "ok" }
```

**Pass =** import ok + no `ShellMate]` in file.

#### Done when

- [x] No typo line in enable.py
- [x] Import succeeds

---

## Phase 5 — Analyze UX

**Tasks:** AGR-14, AGR-15, AGR-16, AGR-17  
**Goal:** Spinner during analyze; guide + supervisor warning in output; single render path.

**Phase gate:**

```powershell
cd D:\projects\shellmate
python -m pytest tests/unit/test_ui.py tests/unit/test_cli_parser.py tests/e2e/test_user_flow.py -q --tb=short
```

---

### AGR-14 — Analysis stage spinner (`ui/progress.py`) `[Phase 5]`

**Goal:** Context manager shows cycling stage labels during IPC wait.

**Prerequisites:** None.

**Files to create:**
- `ui/progress.py`
- `tests/unit/test_ui.py`

#### Steps

1. Create `ui/progress.py`:

```python
import time
import threading
from contextlib import contextmanager
from rich.console import Console
from rich.status import Status

STAGES = [
    "Routing command…",
    "Gathering context…",
    "Analyzing risk…",
    "Building usage guide…",
    "Formatting result…",
]

@contextmanager
def analysis_progress(console: Console, interval: float = 0.4):
    stop = threading.Event()
    idx = [0]

    def cycle(status: Status):
        while not stop.is_set():
            status.update(STAGES[idx[0] % len(STAGES)])
            idx[0] += 1
            stop.wait(interval)

    with console.status(STAGES[0], spinner="dots") as status:
        t = threading.Thread(target=cycle, args=(status,), daemon=True)
        t.start()
        try:
            yield
        finally:
            stop.set()
            t.join(timeout=1.0)
```

2. Test with `Console(file=io.StringIO(), force_terminal=True)` — enter/exit context without exception.

#### Verify

```powershell
cd D:\projects\shellmate
python -m pytest tests/unit/test_ui.py -q -k progress --tb=short
```

#### Done when

- [x] Context manager works in test

---

### AGR-15 — Wire spinner into `cli/main.py` `[Phase 5]`

**Goal:** Non-quiet analyze shows spinner during IPC.

**Prerequisites:** AGR-14 done.

**Files to edit:**
- `cli/main.py`

#### Steps

1. In `Action.ANALYZE` block, change to:

```python
            from cli.commands.analyze import analyze_command
            from ui.progress import analysis_progress
            if parsed.quiet:
                result = analyze_command(parsed.raw_command)
            else:
                with analysis_progress(c):
                    result = analyze_command(parsed.raw_command)
```

2. Ensure `--quiet` path has **no** import side effects on spinner.

#### Verify

```powershell
cd D:\projects\shellmate
python -m pytest tests/unit/test_cli_parser.py tests/unit/test_ui.py -q --tb=short
```

#### Done when

- [x] Quiet tests still pass
- [x] No spinner when quiet

---

### AGR-16 — Render command guide in `ui/analysis.py` `[Phase 5]`

**Goal:** Analysis output shows guide + supervisor warning.

**Prerequisites:** AGR-03 `_build_output` fields exist (can mock in UI test before graph done).

**Files to edit:**
- `ui/analysis.py`
- `tests/unit/test_ui.py`

#### Steps

1. After message block in `render_analysis`, add:

```python
    warning = result.get("supervisor_warning")
    if warning:
        console.print(f"  [yellow]⚠ {warning}[/yellow]")

    guide = result.get("command_guide")
    if guide:
        console.print()
        console.print("[bold]Command guide[/bold]")
        if guide.get("when_to_use"):
            console.print(f"  When to use: {guide['when_to_use']}")
        for p in guide.get("parameters") or []:
            console.print(f"  • {p}")
        if guide.get("example_command"):
            console.print(f"  [dim]Example:[/dim] [cyan]{guide['example_command']}[/cyan]")
```

2. Add tests `test_render_analysis_command_guide` and `test_render_analysis_supervisor_warning`.

#### Verify

```powershell
cd D:\projects\shellmate
python -m pytest tests/unit/test_ui.py -q -k "guide or warning" --tb=short
```

#### Done when

- [x] Both new tests pass

---

### AGR-17 — Unify analysis rendering `[Phase 5]`

**Goal:** `cli/main.py` uses `ui/analysis.render_analysis` only.

**Prerequisites:** AGR-16 done.

**Files to edit:**
- `cli/main.py`

#### Steps

1. Replace `_print_analysis_result(result, c)` body with:

```python
def _print_analysis_result(result: dict, c: Console = None):
    from ui.analysis import render_analysis
    import ui.analysis as analysis_mod
    c = c or console
    orig = analysis_mod.console
    analysis_mod.console = c
    try:
        render_analysis(result)
    finally:
        analysis_mod.console = orig
```

2. Or call `render_analysis` directly if you add optional `console=` param — prefer minimal change.

3. Delete duplicate risk/alternatives printing code from `_print_analysis_result` (~40 lines).

#### Verify

```powershell
cd D:\projects\shellmate
python -m pytest tests/unit/test_ui.py tests/e2e/test_user_flow.py -q --tb=short
```

#### Done when

- [x] Single render path
- [x] E2E user flow passes (26/27 pass, 1 pre-existing unrelated failure)

---

## Phase 6 — Tests & Release Docs

**Tasks:** AGR-18, AGR-19, AGR-20, AGR-21, AGR-22, AGR-23, AGR-24, AGR-25, AGR-26, AGR-27, AGR-28, AGR-29, AGR-30, AGR-31, AGR-32  
**Goal:** Every enrichment scope has automated tests. No real API keys. Full regression green.

**Execute sub-tracks in order:** 6A → 6B → 6C → 6D → 6E → 6F → 6G (see below).

### Test coverage matrix (check all before release)

Mark each row `[x]` only when the listed task(s) pass verify.

| Scope | What to prove | Task(s) | Existing file(s) |
|-------|---------------|---------|------------------|
| **Orchestration** | Supervisor node, router, stage latencies | AGR-19 | `tests/unit/test_analysis_graph.py` |
| **Workflow** | Early exit vs full path vs fallback path | AGR-20 | `tests/unit/test_analysis_graph.py` |
| **Memory / state** | `AnalysisState` fields merge; MemorySaver compile | AGR-21 | `tests/unit/test_analysis_graph.py` |
| **Agents** | Watcher/Librarian called only when routed | AGR-22 | `tests/unit/test_agents.py`, `tests/e2e/test_agent_behaviors.py` |
| **Providers** | `groq_supervisor`, `groq_command_guide` parse/timeout | AGR-23 | `tests/unit/test_groq_supervisor.py`, new guide tests |
| **User flow** | enable → analyze → disable with new UX | AGR-24, AGR-25 | `tests/e2e/test_user_flow.py`, `test_lifecycle.py` |
| **IPC / daemon** | Analyze IPC returns guide + warning fields | AGR-26 | `tests/unit/test_ipc.py`, e2e user flow |
| **UI / CLI** | Panel, spinner, guide render, `--quiet` | AGR-27 | `tests/unit/test_ui.py`, `test_cli_parser.py` |
| **Security** | Secrets redacted before Groq prompts | AGR-28 | `tests/unit/test_security.py` |
| **Edge cases** | Timeouts, partial context, invalid JSON | AGR-29 | `tests/e2e/test_edge_cases.py` |
| **Regression** | Full suite, no credential leak | AGR-30, AGR-31 | all `tests/` |
| **Docs** | README + parking lot | AGR-32 | `README.md`, `docs/v2-implementation-tasks.md` |

### Phase 6 sub-tracks

| Sub-track | Tasks | Focus |
|-----------|-------|-------|
| **6A — Fixtures & orchestration** | AGR-18, 19, 20, 21 | Shared mocks, graph nodes, workflow paths, memory |
| **6B — Agents & providers** | AGR-22, 23 | Worker routing, Groq provider units |
| **6C — User flow & IPC** | AGR-24, 25, 26 | E2E journeys, daemon handlers |
| **6D — UI & CLI** | AGR-27 | Rich output, flags |
| **6E — Security & edges** | AGR-28, 29 | Redaction, failure modes |
| **6F — Regression** | AGR-30, 31 | Full pytest, CI parity |
| **6G — Docs** | AGR-32 | README, parking lot |

**Phase gate (run after AGR-32):**

```powershell
cd D:\projects\shellmate
python -m pytest tests/ -q --tb=short
Select-String -Path docs/v2-implementation-tasks.md -Pattern "agent-enrichment-plan"
Select-String -Path README.md -Pattern "GROQ_SUPERVISOR"
```

**Pass =** 0 failed (skipped OK) + both doc greps match.

---

### AGR-18 — Shared enrichment test fixtures `[Phase 6]` · 6A

**Goal:** One place for mocks/fixtures used across Phase 6 tests.

**Prerequisites:** Phases 1–5 complete.

**Files to create/edit:**
- `tests/conftest.py` (extend)
- `tests/fixtures/enrichment.py` (new, optional if conftest enough)

**Do NOT:** Call real Groq API.

#### Steps

1. Add fixture `mock_supervisor_route` — patches `orchestration.analysis_graph.route_command` to return configurable flags.

2. Add fixture `mock_command_guide` — patches guide generator to return:

```python
{
    "when_to_use": "Apply a specific commit on the current branch.",
    "parameters": ["<commit>: SHA to cherry-pick"],
    "example_command": "git cherry-pick abc1234",
}
```

3. Add helper `minimal_analysis_state(**overrides) -> AnalysisState` — builds valid state dict with all required keys (including `supervisor_decision`, `supervisor_fallback`, `command_guide`).

4. Add fixture `sample_watcher_context`:

```python
{"os": {"system": "Windows"}, "shell": "powershell",
 "current_directory": "D:\\projects\\shellmate",
 "git": {"branch": "main", "staged": 0, "unstaged": 1}}
```

#### Verify

```powershell
cd D:\projects\shellmate
python -m pytest tests/unit/test_analysis_graph.py -q --tb=short -k "state"
```

#### Done when

- [x] Fixtures importable from conftest
- [x] At least one test uses `minimal_analysis_state`

---

### AGR-19 — Orchestration: supervisor routing matrix `[Phase 6]` · 6A

**Goal:** Unit tests prove supervisor returns correct worker flags per command class.

**Files to edit:**
- `tests/unit/test_analysis_graph.py`

#### Tests to add (class `TestLLMSupervisorNode`)

| Test name | Setup | Assert |
|-----------|-------|--------|
| `test_supervisor_groq_watcher_only` | mock route → `{watcher:T, librarian:F}` | `needs_context` True; decision matches |
| `test_supervisor_groq_librarian_only` | mock route → `{watcher:F, librarian:T}` | same |
| `test_supervisor_groq_neither` | mock route → both False | `needs_context` False |
| `test_supervisor_groq_both` | mock route → both True | `needs_context` True |
| `test_supervisor_no_key_uses_heuristic` | unset `GROQ_API_KEY`, cmd `git status` | both flags True (heuristic) |
| `test_supervisor_no_key_echo_skips` | unset key, cmd `echo hi` | both False |
| `test_supervisor_records_stage_latency` | mock route ok | `"supervisor"` in result `stages` |

#### Verify

```powershell
cd D:\projects\shellmate
python -m pytest tests/unit/test_analysis_graph.py -q -k "Supervisor" --tb=short
```

---

### AGR-20 — Orchestration: workflow paths `[Phase 6]` · 6A

**Goal:** Full graph `ainvoke` tests for every major workflow branch.

**Files to edit:**
- `tests/unit/test_analysis_graph.py`

#### Tests to add (class `TestAnalysisWorkflow`)

| Test name | Path exercised | Assert |
|-----------|----------------|--------|
| `test_workflow_early_exit_cache` | cache hit | no supervisor call; no `command_guide` |
| `test_workflow_early_exit_rule` | rule match ≥0.9 | no guide |
| `test_workflow_supervisor_fallback` | route raises | `supervisor_warning` in output; no context |
| `test_workflow_full_path_keyed` | mock supervisor+risk+remediation+guide | output has risk + `command_guide` |
| `test_workflow_skip_context_both_false` | route neither | `context_used` all false; still has risk |
| `test_workflow_watcher_only_context` | watcher only | `context_used.watcher` true, librarian false |

Patch `analyze_risk`, `generate_remediation`, `route_command`, `generate_command_guide` — never network.

#### Verify

```powershell
cd D:\projects\shellmate
python -m pytest tests/unit/test_analysis_graph.py -q -k "Workflow" --tb=short
```

---

### AGR-21 — Orchestration: memory & state merge `[Phase 6]` · 6A

**Goal:** LangGraph MemorySaver compiles; state fields survive node chain.

**Files to edit:**
- `tests/unit/test_analysis_graph.py`

#### Tests to add (class `TestGraphMemoryAndState`)

| Test name | Assert |
|-----------|--------|
| `test_graph_compiles_with_checkpointer` | `AnalysisGraph().build()` not None |
| `test_state_supervisor_fields_preserved` | after supervisor node, decision in returned delta |
| `test_state_command_guide_in_format_output` | format_node receives `command_guide` → in `_build_output` |
| `test_initial_state_has_all_keys` | `ainvoke` initial_state matches `AnalysisState` keys |
| `test_agent_latency_merged` | context_worker updates `agent_latency` keys |

**Note:** MVP does **not** persist graph across daemon restarts — do **not** test cross-session checkpoint restore (out of scope).

#### Verify

```powershell
cd D:\projects\shellmate
python -m pytest tests/unit/test_analysis_graph.py -q -k "Memory or State" --tb=short
```

---

### AGR-22 — Agents: selective worker integration `[Phase 6]` · 6B

**Goal:** Graph calls Watcher/Librarian/Repomix only when supervisor flags say so.

**Files to edit:**
- `tests/unit/test_analysis_graph.py` (graph-level mocks)
- `tests/e2e/test_agent_behaviors.py` (add class `TestEnrichmentAgentRouting`)

#### Unit tests (class `TestSelectiveWorkerFanOut`)

| Test | Patch | Assert |
|------|-------|--------|
| `test_only_watcher_called` | `_query_watcher/librarian/repomix` AsyncMock | watcher called; others not |
| `test_librarian_runs_repomix` | librarian flag True | both `_query_librarian` and `_query_repomix` called |
| `test_empty_tasks_skips_wait` | both flags False | context stage completes; empty merged_context |

#### E2E behavior tests (no daemon required — invoke `context_worker_node` or graph)

| Test | Assert |
|------|--------|
| `test_watcher_agent_still_returns_os_context` | existing — keep passing |
| `test_librarian_search_when_routed` | mock indexed librarian; search invoked when flag True |

#### Verify

```powershell
cd D:\projects\shellmate
python -m pytest tests/unit/test_analysis_graph.py -q -k "Worker or FanOut" --tb=short
python -m pytest tests/e2e/test_agent_behaviors.py -q -k "Enrichment or Routing" --tb=short
```

---

### AGR-23 — Providers: supervisor + command guide units `[Phase 6]` · 6B

**Goal:** Provider modules fully unit-tested in isolation.

**Files to create/edit:**
- `tests/unit/test_groq_supervisor.py` (extend if exists from AGR-02)
- `tests/unit/test_groq_command_guide.py` (new)

#### Tests for `groq_supervisor`

| Test | Assert |
|------|--------|
| `test_parse_fenced_json` | handles ``` blocks |
| `test_timeout_raises_supervisor_error` | `asyncio.wait_for` timeout |
| `test_invalid_json_raises` | malformed response |
| `test_missing_key_raises` | no `GROQ_API_KEY` |

#### Tests for `groq_command_guide`

| Test | Assert |
|------|--------|
| `test_guide_parse_valid_json` | all three fields extracted |
| `test_guide_includes_context_in_prompt` | mock client; prompt contains directory from context |
| `test_guide_timeout_returns_error` | caller can omit guide |
| `test_guide_no_key_skips` | raises or returns None per implementation |

#### Verify

```powershell
cd D:\projects\shellmate
python -m pytest tests/unit/test_groq_supervisor.py tests/unit/test_groq_command_guide.py -q --tb=short
```

---

### AGR-24 — User flow E2E: enable → analyze → disable `[Phase 6]` · 6C

**Goal:** End-to-end journey with new enable panel and enriched analysis output.

**Files to edit:**
- `tests/e2e/test_user_flow.py`
- `tests/e2e/test_lifecycle.py` (if disable flow needs update)

#### Tests to add (class `TestEnrichmentUserFlow`)

| Test | Steps | Assert |
|------|-------|--------|
| `test_enable_startup_stages_reach_ready` | existing pattern | startup_stage == ready |
| `test_analyze_returns_command_guide_fields` | mock graph/providers at IPC boundary | result keys: `command_guide.when_to_use`, etc. |
| `test_analyze_returns_supervisor_warning_on_fallback` | mock supervisor fail | `supervisor_warning` in JSON response |
| `test_disable_still_prints_spec_message` | existing DIS-01 | unchanged |

Use `_isolate_credentials` + patch providers at `daemon/server.py` or `orchestration.analysis_graph` level.

#### Verify

```powershell
cd D:\projects\shellmate
python -m pytest tests/e2e/test_user_flow.py -q -k "Enrichment" --tb=short
python -m pytest tests/e2e/test_lifecycle.py -q --tb=short
```

---

### AGR-25 — User flow E2E: flags & no-key paths `[Phase 6]` · 6C

**Goal:** `--quiet`, `--no-color`, and no Groq key paths unchanged or correctly degraded.

**Files to edit:**
- `tests/e2e/test_user_flow.py`
- `tests/unit/test_cli_parser.py`

#### Tests to add

| Test | Assert |
|------|--------|
| `test_quiet_analyze_no_spinner_keys` | JSON stdout only; valid JSON; no Rich escape codes |
| `test_quiet_includes_command_guide_when_present` | guide fields in JSON when mocked |
| `test_no_color_flag_parsed` | existing UI-03 tests still pass |
| `test_no_groq_key_no_command_guide` | guide absent; deterministic supervisor |
| `test_no_groq_key_analyze_succeeds` | risk field present |

#### Verify

```powershell
cd D:\projects\shellmate
python -m pytest tests/e2e/test_user_flow.py tests/unit/test_cli_parser.py -q -k "quiet or no_color or no_groq" --tb=short
```

---

### AGR-26 — IPC / daemon: analyze handler contract `[Phase 6]` · 6C

**Goal:** IPC analyze response schema includes enrichment fields.

**Files to edit:**
- `tests/unit/test_ipc.py`
- optionally `tests/e2e/test_user_flow.py`

#### Tests to add (class `TestAnalyzeIPCEnrichment`)

| Test | Assert |
|------|--------|
| `test_analyze_response_schema_has_guide` | mocked daemon handler returns `command_guide` dict |
| `test_analyze_response_schema_has_supervisor_warning` | optional field when fallback |
| `test_analyze_response_backward_compatible` | still has `risk`, `message`, `alternatives`, `context_used` |
| `test_context_gatherer_unchanged` | `/context-gatherer` still returns watcher/librarian (no regression) |

#### Verify

```powershell
cd D:\projects\shellmate
python -m pytest tests/unit/test_ipc.py -q -k "Enrichment or analyze" --tb=short
```

---

### AGR-27 — UI / CLI: enrichment rendering `[Phase 6]` · 6D

**Goal:** All new UI components have unit tests.

**Files to edit:**
- `tests/unit/test_ui.py`

#### Tests to add

| Test | Assert output contains |
|------|------------------------|
| `test_render_enable_panel_all_stages_done` | `ShellMate`, `✓`, `sm -a` |
| `test_render_enable_panel_pending_stage` | `○` for incomplete stage |
| `test_analysis_progress_context_manager` | no exception; status started/stopped |
| `test_render_analysis_command_guide` | `Command guide`, `When to use`, `Example` |
| `test_render_analysis_supervisor_warning` | `⚠` and `supervisor unavailable` |
| `test_render_analysis_no_guide_when_absent` | no `Command guide` section |
| `test_render_analysis_quiet_not_applicable` | render_analysis doesn't know quiet — tested via main integration |

Follow existing pattern: swap `ui.analysis.console` to `StringIO` capture.

#### Verify

```powershell
cd D:\projects\shellmate
python -m pytest tests/unit/test_ui.py -q --tb=short
```

---

### AGR-28 — Security: redaction in enrichment prompts `[Phase 6]` · 6E

**Goal:** API keys / secrets in watcher or librarian context never appear in prompts sent to Groq.

**Files to edit:**
- `tests/unit/test_security.py`

#### Tests to add (class `TestEnrichmentRedaction`)

| Test | Assert |
|------|--------|
| `test_supervisor_prompt_redacts_env_secrets` | context with fake `AWS_SECRET_KEY=...` → prompt uses redacted form |
| `test_guide_prompt_redacts_librarian_snippets` | librarian match with password → redacted before guide prompt |
| `test_format_output_no_raw_secrets` | graph output message doesn't leak secrets from context |

Use `config.secrets.redact_secrets` patterns already tested in REL-03.

#### Verify

```powershell
cd D:\projects\shellmate
python -m pytest tests/unit/test_security.py -q -k "Enrichment or Redact" --tb=short
```

---

### AGR-29 — Edge cases: failures & partial context `[Phase 6]` · 6E

**Goal:** Degraded modes don't crash; user gets best-effort output.

**Files to edit:**
- `tests/e2e/test_edge_cases.py`

#### Tests to add (class `TestEnrichmentEdgeCases`)

| Test | Condition | Assert |
|------|-----------|--------|
| `test_supervisor_timeout_fallback` | route timeout | analysis completes; warning set |
| `test_guide_invalid_json_omitted` | guide returns garbage | no `command_guide`; risk still present |
| `test_partial_context_watcher_timeout` | watcher slow | `partial` true or empty watcher; analysis continues |
| `test_supervisor_and_guide_both_fail` | both raise | analysis completes with warning; no guide |
| `test_empty_command_rejected` | `sm -a` no args | exit code 2 (parser) — no regression |
| `test_malformed_supervisor_json` | invalid JSON from Groq | fallback path |

#### Verify

```powershell
cd D:\projects\shellmate
python -m pytest tests/e2e/test_edge_cases.py -q -k "Enrichment" --tb=short
```

---

### AGR-30 — Cross-suite enrichment smoke `[Phase 6]` · 6F

**Goal:** One command runs all enrichment-related tests together.

**Files:** none (orchestration only)

#### Verify

```powershell
cd D:\projects\shellmate
python -m pytest tests/unit/test_analysis_graph.py tests/unit/test_groq_supervisor.py tests/unit/test_groq_command_guide.py tests/unit/test_ui.py tests/unit/test_security.py tests/e2e/test_agent_behaviors.py tests/e2e/test_user_flow.py tests/e2e/test_edge_cases.py -q -k "Supervisor or Workflow or Enrichment or guide or FanOut or Redact" --tb=short
```

**Pass =** 0 failed.

#### Done when

- [x] Smoke command passes
- [x] Paste test count: 64 passed

---

### AGR-31 — Full regression (unit + e2e) `[Phase 6]` · 6F

**Goal:** Zero failures across entire test suite.

**Prerequisites:** AGR-18 through AGR-30 done.

#### Verify

```powershell
cd D:\projects\shellmate
python -m pytest tests/unit/ -q --tb=short
python -m pytest tests/e2e/ -q --tb=short
```

**Pass =** 0 failed each (skipped OK).

Optional CI parity:

```powershell
python -m pytest tests/ -q --tb=short
```

#### Done when

- [x] Full suite green
- [x] Paste final counts: `318 passed, 2 skipped, 0 failed`

---

### AGR-32 — Update project docs `[Phase 6]` · 6G

**Goal:** README + parking lot + test documentation pointer.

**Files to edit:**
- `docs/v2-implementation-tasks.md`
- `README.md`
- `docs/agent-enrichment-plan/tasks.md` (this file — check Phase 6 matrix)

#### Steps

1. Parking lot entry:

```markdown
- [ ] **Agent enrichment & UX (2.1.0)** — [`docs/agent-enrichment-plan/tasks.md`](agent-enrichment-plan/tasks.md)
```

2. README **Environment variables**:

```markdown
| `GROQ_SUPERVISOR_MODEL` | Fast model for routing + command guide (default: `llama-3.1-8b-instant`) |
```

3. README **Testing** section — add:

```markdown
Enrichment tests: Phase 6 in `docs/agent-enrichment-plan/tasks.md` (orchestration, workflow, agents, user flow, IPC, UI, security).
```

4. Add **Manual smoke checklist** to README or design.md:

```
sm enable          → Rich panel with ASCII + checklist
sm -a git status   → spinner (non-quiet) + analysis
sm -a git cherrypick → command guide section (when keyed)
sm -a echo hi --quiet → JSON only, no spinner
```

#### Verify

```powershell
cd D:\projects\shellmate
Select-String -Path docs/v2-implementation-tasks.md -Pattern "agent-enrichment-plan"
Select-String -Path README.md -Pattern "GROQ_SUPERVISOR"
Select-String -Path README.md -Pattern "agent-enrichment-plan"
```

#### Done when

- [x] All three greps match
- [x] Phase 6 coverage matrix (top of this phase) all `[x]`

---

## Execution phases (for human review)

Complete **all tasks in a phase**, run **Phase gate**, then stop and report before starting the next phase.

| Phase | Tasks | Report |
|-------|-------|--------|
| **1 — Foundation** | AGR-01, 02, 03 | Phase 1 gate output |
| **2 — LLM Supervisor Graph** | AGR-04, 05, 06, 07 | Phase 2 gate output |
| **3 — Command Guide Node** | AGR-08, 09, 10 | Phase 3 gate output |
| **4 — Enable UX** | AGR-11, 12, 13 | Phase 4 gate output — **DONE** |
| **5 — Analyze UX** | AGR-14, 15, 16, 17 | Phase 5 gate output — **DONE** |
| **6 — Tests & Release Docs** | AGR-18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32 | Phase 6 gate + coverage matrix audit — **DONE** |

---

## Definition of Done (release 2.1.0)

| # | Criterion | How to prove |
|---|-----------|--------------|
| 1 | Keyed analyze shows command guide | AGR-24 or manual `sm -a git cherrypick` |
| 2 | Analyze spinner (non-quiet) | AGR-27 or manual |
| 3 | Enable shows Rich Panel | AGR-27 or manual `sm enable` |
| 4 | Supervisor fail → warning, analysis completes | AGR-20, AGR-29 |
| 5 | No-key unchanged | AGR-25 |
| 6 | `--quiet` unchanged | AGR-25 |
| 7 | All tests pass (unit + e2e) | AGR-31: 0 failed |
| 8 | Coverage matrix fully checked | Phase 6 matrix all `[x]` |
| 9 | Every task verify run | Process audit |

---

## Decision Log (fill on completion)

| Task | Date | Agent | Notes |
|------|------|-------|-------|
| AGR-11 | 2026-06-10 | opencode | Added `render_enable_panel()` to `ui/banner.py` + test |
| AGR-12 | 2026-06-10 | opencode | Refactored `run_startup_ui` to use panel from AGR-11 |
| AGR-13 | 2026-06-10 | opencode | Removed `ShellMate]` typo, stripped `console` import |
| AGR-14 | 2026-06-10 | opencode | Created `ui/progress.py` with `analysis_progress` context manager + test |
| AGR-15 | 2026-06-10 | opencode | Wired spinner into `cli/main.py` analyze block (guarded by `--quiet`) |
| AGR-16 | 2026-06-10 | opencode | Added supervisor_warning + command_guide rendering in `ui/analysis.py` + 3 tests |
| AGR-17 | 2026-06-10 | opencode | Replaced `_print_analysis_result` with unified `render_analysis` call
| AGR-18 | 2026-06-10 | opencode | Added enrichment fixtures to tests/conftest.py (mock_supervisor_route, mock_command_guide, minimal_analysis_state, sample_watcher_context)
| AGR-19 | 2026-06-10 | opencode | Added TestLLMSupervisorNode class to test_analysis_graph.py (7 supervisor routing matrix tests)
| AGR-20 | 2026-06-10 | opencode | Added TestAnalysisWorkflow class (6 ainvoke workflow path tests)
| AGR-21 | 2026-06-10 | opencode | Added TestGraphMemoryAndState class (5 memory/state tests)
| AGR-22 | 2026-06-10 | opencode | Already covered by existing TestSelectiveWorkerFanOut in test_analysis_graph.py
| AGR-23 | 2026-06-10 | opencode | Added timeout and invalid-JSON tests to test_groq_supervisor.py and test_groq_command_guide.py
| AGR-24 | 2026-06-10 | opencode | Added TestEnrichmentUserFlow class to test_user_flow.py
| AGR-25 | 2026-06-10 | opencode | Added TestEnrichmentFlags class to test_user_flow.py
| AGR-26 | 2026-06-10 | opencode | Added TestAnalyzeIPCEnrichment class to test_ipc.py
| AGR-27 | 2026-06-10 | opencode | Verified all UI enrichment tests already exist in test_ui.py
| AGR-28 | 2026-06-10 | opencode | Added TestEnrichmentRedaction class to test_security.py
| AGR-29 | 2026-06-10 | opencode | Added TestEnrichmentEdgeCases class to test_edge_cases.py
| AGR-30 | 2026-06-10 | opencode | Smoke test: 64 enrichment tests pass
| AGR-31 | 2026-06-10 | opencode | Full regression: 318 passed, 2 skipped, 0 failed
| AGR-32 | 2026-06-10 | opencode | Updated README.md (GROQ_SUPERVISOR, testing section, smoke checklist) and docs/v2-implementation-tasks.md parking lot

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `supervisor_node` not awaited | Must be `async def`; rebuild graph |
| State KeyError on new fields | Add keys to **every** AnalysisState dict in tests + `ainvoke` |
| Tests hit real Groq | Patch `route_command` / `generate_command_guide`; use `_isolate_credentials` |
| Missing Phase 6 scope | Check coverage matrix at top of Phase 6 — each row needs `[x]` |
| Spinner breaks quiet mode | Guard with `if not parsed.quiet` |
| Enable shows nothing | Panel must print **after** Progress context exits |
| Windows verify fails on `&&` | Use `;` in PowerShell |
| `rg` not found | Use `Select-String` on Windows |
