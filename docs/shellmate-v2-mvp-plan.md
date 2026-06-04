# ShellMate v2.0 MVP - Implementation Plan

> **Goal:** Transform ShellMate into a multi-agent system with simplified CLI, contextual RAG, and rich UX

## Overview

This plan breaks down the v2.0 implementation into actionable tasks with clear verification criteria.

---

## Phase 1: CLI Foundation

### Task 1.1: Create New Command Parser
- [ ] Create `cli/parser.py` with `ShellMateCommandParser` class
- [ ] Implement `parse(args)` method to handle `sm -a <command>` format
- [ ] Handle subcommands: enable, disable, status, config
- [ ] Create `InvalidCommandFormat` exception class
- [ ] Return `ParsedCommand` dataclass with action, command, and suggestion fields

**Verify:** `python -m cli.parser` test cases pass

**Note:** Must handle edge cases:
- Empty args: `[]` → show usage
- Only `-a`: `["-a"]` → error "missing command"
- Dash in command: `sm -a git commit -m "msg"` → preserve all args after `-a`

### Task 1.2: Update CLI Main
- [ ] Refactor `cli/main.py` to use new parser
- [ ] **CRITICAL:** Handle Click vs raw argv conflict - use Click only for entry point, not argument parsing
- [ ] Remove Click argument parsing for `-a` flag (use raw sys.argv slicing)
- [ ] Keep Click `@click.command()` decorators for subcommands
- [ ] Add error handler that catches `InvalidCommandFormat` and displays with Rich Panel
- [ ] Don't exit on error - return to prompt (wait for KeyboardInterrupt)

**Verify:** `sm -a echo test` parses correctly, `sm invalid` shows suggestion and doesn't exit

**Implementation Note:** 
```python
# DON'T mix Click argument capture with sys.argv
@cli.command()
def main():
    # Get args BEFORE Click processes them
    args = sys.argv[1:]
    parser = ShellMateCommandParser()
    try:
        parsed = parser.parse(args)
    except InvalidCommandFormat as e:
        display_error(e)
        return  # Don't sys.exit(), just return
```

### Task 1.3: Session Management
- [ ] Create `daemon/session.py` with `SessionManager` class
- [ ] Implement `create_session(pid, directory)` → creates ~/.shellmate/sessions/{pid}/
- [ ] **Add:** Write `session.json` with metadata (directory, start_time, pid)
- [ ] Implement `get_active_session()` → checks PID file AND validates process is running
- [ ] **Add:** Use `psutil.pid_exists(pid)` or Windows equivalent for validation
- [ ] Implement `cleanup_session(pid)` → removes session directory
- [ ] Add `cleanup_stale_sessions()` → removes dead PID sessions
- [ ] **Add:** Handle Windows path issues (use pathlib.Path throughout)
- [ ] **Add:** Set directory permissions (chmod 700 on Unix, ACL on Windows)

**Verify:** Session directory created/deleted correctly, stale cleanup works

**Windows Compatibility Note:**
```python
import platform
if platform.system() == "Windows":
    # Use psutil.pid_exists() or tasklist
else:
    # Use os.kill(pid, 0) to check process
```

---

## Phase 2: Watcher Agent

### Task 2.1: Agent Base Structure
- [ ] Create `agents/` directory with `__init__.py`
- [ ] Create `agents/base.py` with `Agent` abstract class
- [ ] Define `AgentRequest` and `AgentResponse` dataclasses for type safety
- [ ] Define message queue protocol (request/response format)
- [ ] **Add:** Create `agents/queues.py` for shared queue management
- [ ] **Add:** Define timeout handling and exception types (`AgentTimeout`, `AgentError`)

**Verify:** Base class importable, protocol documented

**Protocol Spec:**
```python
@dataclass
class AgentRequest:
    request_id: str
    action: str
    payload: Dict[str, Any]

@dataclass  
class AgentResponse:
    request_id: str
    success: bool
    data: Optional[Dict[str, Any]]
    error: Optional[str]
```

### Task 2.2: Environment Detection
- [ ] Create `agents/watcher.py` with `WatcherAgent` class
- [ ] Implement `detect_environment()` → OS, shell, terminal
- [ ] Reuse `environment/detector.py` where possible
- [ ] Add `EnvironmentContext` dataclass

**Verify:** Correctly detects Windows/bash/cmd from test environment

### Task 2.3: Tech Stack Scanner
- [ ] Implement `detect_tech_stack()` in `WatcherAgent`
- [ ] Scan root directory for package.json, requirements.txt, etc.
- [ ] Return list of `TechStackItem` objects
- [ ] Handle missing files gracefully

**Verify:** Detects Node.js from package.json, Python from requirements.txt

### Task 2.4: Git Integration
- [ ] Implement `detect_git()` in `WatcherAgent`
- [ ] **CRITICAL:** Check if git is installed first: `shutil.which("git")`
- [ ] Use subprocess with timeout: `subprocess.run(..., timeout=2)`
- [ ] **OPTIMIZATION:** Combine git calls to reduce overhead:
  ```bash
  git status --porcelain --branch && git log -1 --format=%s
  ```
- [ ] Parse combined output instead of 3 separate calls
- [ ] Return `GitContext` or None if not a repo or git not installed
- [ ] **Add:** Handle git errors gracefully (detached HEAD, empty repo, etc.)

**Verify:** Captures branch and uncommitted changes in test git repo

**Edge Cases to Handle:**
- Not a git repo: `fatal: not a git repository`
- Empty repo: No commits yet
- Detached HEAD state
- Git not installed

### Task 2.5: Agent Main Loop
- [ ] Implement `async run(startup_queue)` in `WatcherAgent`
- [ ] Run all detection on startup
- [ ] Send progress updates to `startup_queue` (use `queue.put_nowait()`)
- [ ] **CRITICAL:** Create response queue: `self.response_queue = asyncio.Queue()`
- [ ] Listen on `self.response_queue` for context requests (NOT global watcher_queue)
- [ ] **Add:** Implement proper queue listening loop:
  ```python
  while True:
      request = await self.response_queue.get()
      response = self._handle_request(request)
      # Put response in request-specific queue
  ```
- [ ] Respond with cached context based on command type
- [ ] **Add:** Handle shutdown signal to break loop gracefully

**Verify:** Agent starts, sends "watcher_ready" message, responds to context request

**Queue Architecture Fix:**
- Daemon has ONE queue per agent instance
- Agent reads from its own queue
- Responses go back through response_queues[request_id]

---

## Phase 3: Librarian Agent

### Task 3.1: Directory Scanner
- [ ] Create `agents/librarian.py` with `LibrarianAgent` class
- [ ] Implement `scan_directory()` → recursive file walk
- [ ] Filter by `CODE_EXTENSIONS` set
- [ ] Collect file metadata (path, size, mtime)

**Verify:** Scans test directory with 100 files in < 1 second

### Task 3.2: Index Builder
- [ ] Implement `build_index()` in `LibrarianAgent`
- [ ] **CRITICAL:** Use TWO data structures for efficient search:
  ```python
  self._files: Dict[str, FileEntry] = {}  # path -> metadata
  self._search_index: Dict[str, Set[str]] = {}  # keyword -> set of paths
  ```
- [ ] Build inverted index: tokenize file paths into keywords
- [ ] Generate markdown file for human readability (but search uses in-memory index)
- [ ] Write markdown to `~/.shellmate/sessions/{pid}/index.md`
- [ ] Send progress to `startup_queue` (file count updates)
- [ ] **Add:** Tokenization helper:
  ```python
  def tokenize_path(path: str) -> List[str]:
      # Split on /, -, _, . to get keywords
      # Example: "src/utils/config.py" -> ["src", "utils", "config", "py"]
      return re.split(r'[/\\_\-\.]', path.lower())
  ```

**Verify:** index.md created with correct format and file count

**Inverted Index Pattern (Vectorless RAG):**
```python
# Building index
for path in all_files:
    tokens = tokenize_path(path)
    for token in tokens:
        if token not in self._search_index:
            self._search_index[token] = set()
        self._search_index[token].add(path)

# Searching (O(1) lookup per keyword!)
def search(self, query: str) -> List[str]:
    keywords = query.lower().split()
    result_sets = [self._search_index.get(kw, set()) for kw in keywords]
    # Intersection: files that contain ALL keywords
    matches = set.intersection(*result_sets) if result_sets else set()
    return list(matches)[:10]
```

### Task 3.3: File Watcher
- [ ] Install `watchdog>=3.0.0` library (add to requirements.txt)
- [ ] Create `IndexUpdateHandler` class extending `FileSystemEventHandler`
- [ ] Implement `on_created`, `on_modified`, `on_deleted` to update in-memory index
- [ ] **CRITICAL:** Run observer in ThreadPoolExecutor to avoid blocking asyncio:
  ```python
  loop = asyncio.get_event_loop()
  observer = Observer()
  observer.schedule(handler, path, recursive=True)
  await loop.run_in_executor(None, observer.start)
  ```
- [ ] **Add:** Store observer reference for cleanup: `self.observer = observer`
- [ ] **Add:** Implement graceful observer stop in shutdown

**Verify:** Creating new file updates index, file count increments

**Critical Note:** Watchdog uses threads internally - must use executor pattern!

### Task 3.4: Search Implementation
- [ ] Implement `search(query)` in `LibrarianAgent`
- [ ] **OPTIMIZATION:** Use inverted index for O(1) keyword lookup
- [ ] Tokenize query into keywords: `query.lower().split()`
- [ ] For each keyword, get matching paths from `_search_index`
- [ ] **Add:** Support AND logic (files matching ALL keywords):
  ```python
  result_sets = [self._search_index.get(kw, set()) for kw in keywords]
  matches = set.intersection(*result_sets) if result_sets else set()
  ```
- [ ] **Add:** Fallback to substring search if no exact keyword matches
- [ ] Return list of `FileMatch` objects (path + snippet)
- [ ] Limit to top 10 results
- [ ] **Add:** Thread-safe access with asyncio.Lock

**Verify:** Search for "config" returns all config files in index

**Search Performance:**
- Inverted index: O(k) where k = number of keywords (typically 1-3)
- WITHOUT index: O(n) where n = number of files (could be 5000+)
- 1000x speedup for large projects!

**Fallback Pattern:**
```python
def search(self, query: str) -> List[FileMatch]:
    keywords = query.lower().split()
    
    # Try inverted index first (fast)
    matches = self._search_inverted_index(keywords)
    
    # If no results, try substring search (slower but more forgiving)
    if not matches:
        matches = self._search_substring(query.lower())
    
    return matches[:10]
```

### Task 3.5: Agent Main Loop
- [ ] Implement `async run(startup_queue)` in `LibrarianAgent`
- [ ] Call `build_index()` on startup (await it)
- [ ] Start file watcher using executor pattern
- [ ] **CRITICAL:** Create response queue: `self.response_queue = asyncio.Queue()`
- [ ] Listen on `self.response_queue` for search requests
- [ ] Respond with search results via response_queues[request_id]
- [ ] **Add:** Implement proper shutdown handling:
  ```python
  async def shutdown(self):
      if self.observer:
          await self.loop.run_in_executor(None, self.observer.stop)
          await self.loop.run_in_executor(None, self.observer.join)
  ```

**Verify:** Agent starts, indexes files, responds to search request in < 100ms

**Queue Pattern (same as Watcher):**
- Agent reads from self.response_queue
- Sends responses to response_queues[request_id]

### Task 3.6: Error Handling
- [ ] Handle file watching failure → log warning, disable updates
- [ ] Handle large directories → warn if > 5000 files
- [ ] Handle permission errors → skip unreadable files

**Verify:** Large directory shows warning, permission errors don't crash agent

---

## Phase 4: Daemon Integration

### Task 4.1: Agent Lifecycle
- [ ] Update `daemon/server.py` to launch agents as asyncio tasks
- [ ] **CRITICAL:** Create agent instances with their own queues:
  ```python
  watcher = WatcherAgent()
  librarian = LibrarianAgent()
  startup_queue = asyncio.Queue()
  ```
- [ ] Store agent queues: `self.agent_queues = {'watcher': watcher, 'librarian': librarian}`
- [ ] Create response queue dict: `self.response_queues = {}`
- [ ] Launch tasks: `asyncio.create_task(watcher.run(startup_queue))`
- [ ] Implement `wait_for_agents_ready(startup_queue)` helper with timeout
- [ ] **Add:** Store task references for cancellation: `self.agent_tasks = [...]`
- [ ] Update shutdown to cancel agent tasks AND call agent.shutdown()

**Verify:** `sm enable` starts both agents, `sm disable` stops them cleanly

**Shutdown Pattern:**
```python
async def shutdown(self):
    # Cancel tasks
    for task in self.agent_tasks:
        task.cancel()
    # Wait for cancellation
    await asyncio.gather(*self.agent_tasks, return_exceptions=True)
    # Cleanup agents
    await self.watcher.shutdown()
    await self.librarian.shutdown()
```

### Task 4.2: Startup Progress (IPC)
- [ ] **CRITICAL:** Startup progress must use TCP endpoint, not shared queue
- [ ] Add `/status` endpoint to TCP server:
  ```python
  if request.get("action") == "get_status":
      return {"stage": current_stage, "agents": {...}}
  ```
- [ ] **Add:** Create `daemon/startup_status.py` to track progress:
  ```python
  class StartupStatus:
      stage: str = "starting"
      watcher_ready: bool = False
      librarian_ready: bool = False
      file_count: int = 0
  ```
- [ ] Agents update shared StartupStatus object (not queue)
- [ ] CLI polls `/status` endpoint via TCP
- [ ] Display progress using Rich (see Phase 5)

Additional agent-related endpoints:
- [ ] Add `/context-gatherer` endpoint to TCP server for low-latency agent context queries (Watcher/Librarian). This endpoint must enforce per-request timeouts (default 500ms) and return immediately if agents do not respond.
- [ ] Add `/deep-research` endpoint for longer background or provider-backed research (no strict 500ms hard cutoff; used for optional deep analysis and documentation retrieval).

**Verify:** CLI shows progress stages until "ready"

**Why this change:** CLI is separate process - can't share in-memory asyncio.Queue!

### Task 4.3: Enhanced Pipeline
- [ ] Update `daemon/pipeline.py` to accept agent_queues dict
- [ ] Implement `should_query_watcher(parsed_command)` helper
- [ ] Implement `has_file_references(parsed_command)` helper
- [ ] **CRITICAL:** Implement `query_agent()` helper with proper request/response flow:
  ```python
  async def query_agent(agent, request_data, timeout=0.5):
      request_id = str(uuid.uuid4())
      response_queue = asyncio.Queue()
      response_queues[request_id] = response_queue
      
      request = AgentRequest(request_id, action, payload)
      await agent.response_queue.put(request)
      
      try:
          response = await asyncio.wait_for(
              response_queue.get(), timeout=timeout
          )
          return response.data
      except asyncio.TimeoutError:
          return None  # Graceful degradation
      finally:
          del response_queues[request_id]
  ```
- [ ] **OPTIMIZATION:** Query agents in parallel using asyncio.gather()
- [ ] Add agent query stage after parser, before AI analysis
- [ ] Handle timeouts gracefully (continue without context)

**Endpoints and flow:**
- The CLI/daemon IPC should expose `/context-gatherer` for synchronous, low-latency agent context queries (the pipeline will call this to fetch watcher/librarian context with a 500ms default per-request timeout).
- The `/deep-research` endpoint is for longer-running, optional lookups (e.g., documentation retrieval, provider-backed research). Pipeline may call this asynchronously (fire-and-forget) or via a separate UX flow.

**Verify:** Pipeline queries agents when appropriate, continues on timeout

### Task 4.4: Context Injection
- [ ] Update `providers/groq_provider.py` to accept `context` parameter
- [ ] Update `providers/openrouter_provider.py` to accept `context` parameter
- [ ] Enhance prompts to include watcher and librarian context
- [ ] Add `context_used` field to response

**Verify:** AI prompts include tech stack when querying Watcher, file info when querying Librarian

---

## Phase 5: Rich UI

### Task 5.1: Startup Progress UI
- [ ] Create `ui/` directory with `__init__.py`
- [ ] **CRITICAL:** Create `ui/display.py` with `show_startup_progress(ipc_client)`
- [ ] **NOT** `show_startup_progress(startup_queue)` - CLI uses IPC!
- [ ] Poll IPC `/status` endpoint every 200ms
- [ ] Use Rich `Progress` with `SpinnerColumn` and `TextColumn`
- [ ] Update task descriptions based on status response
- [ ] **Add:** Handle connection errors during startup (daemon not ready yet)
- [ ] **Add:** Timeout after 30 seconds if daemon never becomes ready

UI/CLI note: The UI should only poll `/status` for startup progress and summary information. It MUST NOT directly call `/context-gatherer` (that endpoint is intended for pipeline/daemon internal use). Long-running user-requested research can be exposed via a CLI subcommand that calls `/deep-research` and displays progress.

**Verify:** `sm enable` shows spinners for each stage until complete

**Implementation:**
```python
async def show_startup_progress(ipc_client):
    with Progress(...) as progress:
        while True:
            try:
                status = await ipc_client.get_status()
                update_progress_tasks(status)
                if status["stage"] == "ready":
                    break
            except ConnectionRefusedError:
                await asyncio.sleep(0.2)  # Daemon not ready yet
```

### Task 5.2: Greeting Banner
- [ ] Create `ui/banner.py` with `show_greeting(env_info, agent_status, providers)`
- [ ] Add ASCII art banner (ShellMate logo)
- [ ] Create system status panel with Rich `Table.grid()`
- [ ] Create usage panel with instructions
- [ ] **Add:** Handle missing data gracefully (e.g., no git repo)
- [ ] **Add:** Format tech stack list (max 3 items, then "and X more")
- [ ] **Add:** Color-code provider status (green=configured, red=missing)

**Verify:** Greeting displays after startup with correct info

**Formatting Note:**
```python
# Don't overflow panel with 20 tech items
if len(tech_stack) > 3:
    display = ", ".join(tech_stack[:3]) + f" and {len(tech_stack)-3} more"
```

### Task 5.3: Analysis Output
- [ ] Create `ui/analysis.py` with `display_analysis(result)`
- [ ] Use Rich `Panel` for risk level (with color mapping)
- [ ] **Add:** Handle "orange" color fallback (not all terminals support it):
  ```python
  RISK_COLORS = {
      "HIGH": "red" if not supports_truecolor() else "orange",
      ...
  }
  ```
- [ ] Display alternatives in separate panel (check if list is not empty)
- [ ] Display context info (files, git status) if present
- [ ] Show latency breakdown at bottom
- [ ] **Add:** Truncate very long messages (max 500 chars with "...")

**Verify:** `sm -a rm -rf /` shows colored HIGH risk panel with alternatives

**Edge Cases:**
- Empty alternatives list → don't show panel
- No context_used → don't show context panel
- Very long explanation → truncate with ellipsis

### Task 5.4: Status Command UI
- [ ] Create `ui/status.py` with `show_status(status_data)`
- [ ] Use Rich `Layout` for three-panel design
- [ ] Display daemon status (running/stopped, PID, directory)
- [ ] Display agent status table (Watcher, Librarian)
- [ ] Display provider status table (Groq, OpenRouter)

**Verify:** `sm status` shows three panels with correct data

### Task 5.5: Error Messages
- [ ] Update all error handlers to use Rich `Panel`
- [ ] Multi-session error with instructions
- [ ] Invalid format error with suggestion
- [ ] Daemon not running error

**Verify:** Errors display in formatted panels with clear messaging

---

## Phase 6: Testing

### Task 6.1: Unit Tests
- [ ] Test `cli/parser.py` with valid and invalid inputs
- [ ] **Add:** Test edge cases: empty args, only `-a`, command with flags
- [ ] Test `WatcherAgent` detection methods
- [ ] **Add:** Mock subprocess calls (don't require actual git)
- [ ] Test `LibrarianAgent` search functionality
- [ ] **Add:** Use temporary directory for test files
- [ ] Test `SessionManager` create/cleanup
- [ ] **Add:** Mock PID validation (don't require real processes)
- [ ] Run: `pytest tests/unit/ -v`

**Verify:** All unit tests pass

**Mocking Example:**
```python
@patch('subprocess.run')
def test_git_detection(mock_run):
    mock_run.return_value = Mock(stdout="main\n")
    # Test without requiring git installed
```

### Task 6.2: Integration Tests
- [ ] Test full startup flow: `sm enable` → agents start → greeting
- [ ] **Add:** Use test fixture that starts/stops daemon
- [ ] Test command analysis with agent context
- [ ] **Add:** Mock AI provider responses (don't use real API keys in tests)
- [ ] Test agent timeout handling
- [ ] **Add:** Simulate slow agent by adding artificial delay
- [ ] Test graceful shutdown: `sm disable` → cleanup
- [ ] **Add:** Verify session directory is actually deleted
- [ ] Run: `pytest tests/integration/ -v --timeout=30`

**Verify:** Integration tests pass, no crashes

**Test Fixture Pattern:**
```python
@pytest.fixture
async def daemon():
    # Start daemon
    proc = await start_test_daemon()
    yield proc
    # Cleanup
    await stop_test_daemon(proc)
```

### Task 6.3: E2E Tests
- [ ] Test user flow: install → configure → enable → analyze → disable
- [ ] Test multi-session detection (enable in two directories)
- [ ] Test large directory handling
- [ ] Test error scenarios (missing API keys, git not installed)

**Verify:** E2E scenarios complete successfully

---

## Phase 7: Documentation & Release

### Task 7.1: Update Documentation
- [ ] Update README.md with v2.0 CLI examples
- [ ] Create MIGRATION.md guide from v1.x to v2.0
- [ ] Update CHANGELOG.md with breaking changes
- [ ] Add architecture diagram to docs/

**Verify:** Documentation accurate and complete

### Task 7.2: Shell Adapter Update
- [ ] Update `adapters/bash_adapter.sh` to use `sm -a` format
- [ ] Update `adapters/powershell_adapter.ps1` to use `sm -a` format
- [ ] Update `adapters/zsh_adapter.zsh` to use `sm -a` format
- [ ] Test adapters in each shell

**Verify:** Shell hooks intercept commands and call `sm -a <cmd>`

### Task 7.3: Package & Release
- [ ] Update `pyproject.toml` version to 2.0.0
- [ ] Update dependencies (add Rich, watchdog)
- [ ] Build package: `python -m build`
- [ ] Test install in clean environment
- [ ] Tag release: `git tag v2.0.0`

**Verify:** Fresh install works end-to-end

---

## Done When

- [x] Requirements and design documented in `docs/shellmate-v2-requirements-design.md`
- [ ] All 7 phases completed
- [ ] All tests passing
- [ ] Documentation updated
- [ ] v2.0.0 tagged and ready for release

---

## Notes

**Dependencies to Add:**
- `rich>=13.0.0` (terminal UI)
- `watchdog>=3.0.0` (file monitoring)
- `psutil>=5.9.0` (cross-platform process management)
- `pytest>=7.0.0` (testing)
- `pytest-asyncio>=0.21.0` (async test support)
- `pytest-timeout>=2.1.0` (test timeouts)

**Breaking Changes:**
- CLI format: `shellmate analyze "cmd"` → `sm -a cmd`
- No backwards compatibility with v1.x

**Performance Targets:**
- Startup: < 10s for 1000 files
- Command analysis: < 3s with agent context
- Agent queries: < 500ms

**Key Files Modified:**
- `cli/main.py` (refactor - Click/argv conflict resolution)
- `daemon/server.py` (add agent lifecycle + status endpoint)
- `daemon/pipeline.py` (add parallel agent queries)
- `providers/groq_provider.py` (add context parameter)
- `providers/openrouter_provider.py` (add context parameter)

**New Files:**
- `cli/parser.py` (command parsing with error suggestions)
- `daemon/session.py` (session management + PID validation)
- `daemon/startup_status.py` (shared startup state for IPC)
- `agents/__init__.py` (agent package)
- `agents/base.py` (abstract agent + protocol)
- `agents/queues.py` (queue management utilities)
- `agents/watcher.py` (environment detection agent)
- `agents/librarian.py` (RAG agent with inverted index)
- `ui/__init__.py` (UI package)
- `ui/display.py` (startup progress via IPC)
- `ui/banner.py` (greeting banner)
- `ui/analysis.py` (command analysis output)
- `ui/status.py` (status command output)

**Critical Implementation Patterns:**

1. **Watchdog + Asyncio:**
```python
# MUST use executor to avoid blocking event loop
loop = asyncio.get_event_loop()
observer = Observer()
await loop.run_in_executor(None, observer.start)
```

2. **Agent Queue Pattern:**
```python
# Each agent has its own request queue
agent.response_queue = asyncio.Queue()
# Responses go to per-request queues
response_queues[request_id] = asyncio.Queue()
```

3. **Startup IPC (not shared memory):**
```python
# CLI polls TCP endpoint, NOT asyncio.Queue
status = await ipc_client.get_status()
```

4. **Inverted Index (Vectorless RAG):**
```python
# Build: keyword -> set of file paths
# Search: O(1) lookup per keyword
_search_index: Dict[str, Set[str]] = {}
```

---

**End of Plan**
