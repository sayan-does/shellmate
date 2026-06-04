# ShellMate v2.0 - Requirements & Design Specification

**Version:** 2.0.0  
**Date:** June 5, 2026  
**Status:** Design Phase  
**Authors:** Development Team

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Understanding Summary](#understanding-summary)
3. [Requirements](#requirements)
4. [Architecture Design](#architecture-design)
5. [Component Specifications](#component-specifications)
6. [Data Flow](#data-flow)
7. [UI/UX Specifications](#uiux-specifications)
8. [Error Handling & Graceful Degradation](#error-handling--graceful-degradation)
9. [Performance Requirements](#performance-requirements)
10. [Security Considerations](#security-considerations)
11. [Decision Log](#decision-log)
12. [Implementation Plan](#implementation-plan)

---

## Executive Summary

ShellMate v2.0 is a major architectural upgrade transforming the linear command analysis pipeline into a multi-agent orchestrated system with:

- **Simplified CLI**: `sm -a <command>` format (no quotes needed)
- **Contextual Intelligence**: Session-based RAG for file awareness
- **Environment Awareness**: Automatic tech stack and git state detection
- **Rich User Experience**: Modern TUI with loading animations and formatted output
- **Multi-Agent Architecture**: Librarian (RAG), Watcher (environment), Main (orchestration)

**Breaking Changes:** Complete CLI redesign, no backwards compatibility with v1.x

---

## Understanding Summary

### What is Being Built

- Multi-agent command safety system with parallel execution
- Session-based directory indexing (RAG without embeddings)
- Environment detection and caching (OS, shell, tech stack, git)
- Rich terminal UI with progressive loading and formatted output
- Simplified CLI interface with intelligent error suggestions

### Why It Exists

- **Current Limitations:**
  - Clunky CLI requiring quotes and verbose commands
  - No awareness of project context (files, tech stack)
  - No visual feedback during operations
  - Single-pass analysis missing project-specific intelligence
  
- **Value Proposition:**
  - Faster, more intuitive command analysis
  - Context-aware suggestions based on actual project files
  - Git-aware risk assessment
  - Modern, informative user experience

### Who It's For

- Developers working in multi-language projects
- Teams needing git-aware command safety
- Users who want fast, contextual command analysis
- DevOps engineers managing complex environments

### Key Constraints

- Python 3.8+ with asyncio
- Cross-platform (Windows, Linux, macOS)
- Multi-shell support (bash, zsh, powershell, cmd)
- Session-based (no persistent state across enable/disable cycles)
- Graceful degradation when components fail
- Single daemon instance per user (no multi-session support)

### Explicit Non-Goals

- ❌ Backwards compatibility with v1.x CLI
- ❌ Vector embeddings or ML-based RAG
- ❌ Persistent dashboard/TUI (daemon runs in background)
- ❌ Multi-session support (one active directory at a time)
- ❌ Unlimited directory indexing (will filter by file type and warn on large dirs)
- ❌ Real-time git monitoring (snapshot at startup only)

---

## Requirements

### Functional Requirements

#### FR-1: Simplified CLI Interface

**FR-1.1** - Command format must be `sm -a <command>` where everything after `-a` is treated as the command to analyze (no quotes required)

**FR-1.2** - Supported commands:
- `sm -a <command>` - Analyze command
- `sm enable` - Start daemon with rich loading
- `sm disable` - Stop daemon gracefully
- `sm status` - Show daemon and agent status
- `sm config` - Configure API keys and settings

**FR-1.3** - Invalid command formats must:
- Show error message with correct format
- Provide "Did you mean" suggestion
- NOT exit (allow user to try again)

**FR-1.4** - Multi-session detection:
- If daemon already running in another directory, show error
- Provide clear instructions to disable first

#### FR-2: Vectorless RAG (Librarian Agent)

**FR-2.1** - Directory Indexing:
- Recursively scan current directory at startup
- Filter by code/config file extensions (`.py`, `.js`, `.yaml`, `.md`, `.json`, `.toml`, `.txt`, `.sh`, `.rs`, `.go`, `.c`, `.cpp`, `.java`, `.rb`, `.php`, `.tsx`, `.jsx`, `.vue`, `.sql`, `.env.example`)
- Build markdown-formatted index with filenames and paths

**FR-2.2** - File Watching:
- Monitor directory for file changes using `watchdog` library
- Update index when files created/modified/deleted
- Run watchdog Observer in ThreadPoolExecutor to avoid blocking asyncio event loop

**FR-2.3** - Search Interface:
- Keyword/grep-based search (no fuzzy matching)
- Return matching files and relevant content snippets
- Respond to search requests via asyncio queue

**FR-2.4** - Session Management:
- Store index in `~/.shellmate/sessions/{pid}/index.md`
- Delete session directory on graceful shutdown
- Warn and disable RAG if file watching fails

**FR-2.5** - Size Limits:
- Only index known code/config file types
- Skip binary files automatically
- No hard file count limit (trust type filtering)

#### FR-3: Environment Watcher Agent

**FR-3.1** - Detection Scope (root directory only):
- Operating system (Windows/Linux/macOS)
- Shell type (bash/zsh/powershell/cmd/fish)
- Terminal emulator (if detectable)
- Environment type (WSL/native/container/SSH)

**FR-3.2** - Tech Stack Detection:
- Package managers: `package.json`, `requirements.txt`, `Cargo.toml`, `go.mod`, `pom.xml`, `build.gradle`, `composer.json`, `Gemfile`, `mix.exs`
- Build tools: `Makefile`, `webpack.config.js`, `vite.config.js`, `tsconfig.json`
- Runtime indicators: `.python-version`, `.nvmrc`, `.ruby-version`, `Dockerfile`, `docker-compose.yml`
- Framework detection: Scan package.json for React/Vue/Angular, Python imports for Django/Flask

**FR-3.3** - Git Integration:
- Detect if directory is a git repository
- Capture: current branch, uncommitted changes count (staged/unstaged), last commit message
- Gracefully handle non-git directories (skip git context)

**FR-3.4** - Caching Strategy:
- Run detection once at startup
- Cache results in memory
- Respond to context requests via asyncio queue
- No background monitoring (startup snapshot only)

**FR-3.5** - Failure Handling:
- Start daemon even if detection fails
- Cache whatever data was successfully detected
- Show warning to user about partial environment data

#### FR-4: Rich Terminal UI

**FR-4.1** - Startup Sequence:
- Show stage-by-stage progress with spinners using Rich library
- Stages: Daemon start → Watcher init → Environment detection → Librarian init → Indexing → Providers connect → Ready
- Display ASCII art banner on completion
- Show greeting panel with system info (OS, shell, tech stack, git branch, file count, provider status)
- Display usage instructions in formatted panel

**FR-4.2** - Command Analysis Output:
- Risk level displayed in colored panel (SAFE=green, LOW=blue, MEDIUM=yellow, HIGH=orange, CRITICAL=bold red)
- Message and explanation in main panel
- Alternatives in separate cyan panel
- Context information (files used, git status) in dim panel
- Performance metrics at bottom (latency breakdown)

**FR-4.3** - Status Command:
- Three-panel layout: Daemon status, Agent status, Provider status
- Tables with colored status indicators (✓/✗)
- Include PID, directory, file counts, model names

**FR-4.4** - Error Messages:
- Formatted error panels with clear descriptions
- Suggestions for resolution
- Context-appropriate styling

#### FR-5: Multi-Agent Orchestration

**FR-5.1** - Pipeline Integration:
    - Main pipeline queries Watcher agent when command relates to detected tech stack
    - Main pipeline queries Librarian agent when command references file paths
    - Queries happen via asyncio message queues **in parallel** (both agents queried simultaneously)
    - Per-agent hard timeout: 500ms. Agents should aim for much lower typical response times (tens of ms for cached/in-memory operations).
    - Total agent query phase target: complete within 500ms (this is the hard user-facing cutoff). Individual agents may have shorter soft targets but will be forcibly skipped after the 500ms hard timeout.

**FR-5.2** - Context Injection Logic:
- **Watcher context triggered by:**
  - Git commands (git push, git commit, etc.) → include git status
  - Package manager commands (npm, pip, cargo, etc.) → include tech stack
  - Build commands (make, webpack, etc.) → include build tools detected
  
- **Librarian context triggered by:**
  - File paths detected in command arguments
  - Commands that manipulate files (rm, mv, cp, chmod, etc.)
  - Returns: matching files, file metadata, content snippets

**FR-5.3** - AI Provider Integration:
- Enhanced prompts include contextual data from agents
- Risk analysis prompt includes: command + watcher context (if relevant)
- Remediation prompt includes: command + risk + watcher context + librarian results (if relevant)

#### FR-6: Daemon Lifecycle

**FR-6.1** - Enable Command:
- Check if already running (show error if in different directory)
- Create session directory with unique PID
    - Spawn a background daemon process (platform-appropriate: fork/daemonize on Unix-like systems; spawn background process on Windows)
- Parent process connects via TCP to poll startup status endpoint
- Display Rich progress UI based on status updates
- Show banner and greeting when complete
- Return control to terminal (daemon continues in background)

**FR-6.2** - Disable Command:
- Send shutdown signal to daemon
- Daemon gracefully cancels agent tasks
- Clean up session directory
- Display "ShellMate disabled" message with Rich formatting
- Shell adapter continues to intercept commands but shows "disabled" message

**FR-6.3** - Crash Recovery:
- PID file must be validated (check if process actually exists)
- Stale PID files cleaned up automatically
- Session directory cleanup on abnormal termination (best effort)

---

### Non-Functional Requirements

#### NFR-1: Performance

**NFR-1.1** - Startup time: Complete initialization in < 10 seconds for typical projects (< 1000 files)

**NFR-1.2** - Command analysis latency:
- Cache hit: < 200ms
- Rule match: < 50ms
- Full AI analysis: < 5000ms
- Agent query overhead: < 500ms per agent

**NFR-1.3** - File indexing:
- Process files concurrently where possible
- Show progress for directories > 500 files
- Background updates must not block command analysis

**NFR-1.4** - Memory footprint:
- Daemon base: < 100MB
- Index storage: ~1KB per file
- Agent overhead: < 50MB total

#### NFR-2: Reliability

**NFR-2.1** - Graceful Degradation:
- Librarian failure → Continue without RAG context
- Watcher failure → Start with empty/partial environment data
- File watching failure → Disable RAG, show warning
- Provider failure → Use fallback deterministic responses

**NFR-2.2** - Error Isolation:
- Agent exceptions must not crash daemon
- TCP handler errors must not affect other connections
- Queue timeouts prevent deadlocks

**NFR-2.3** - Data Integrity:
- Session directory atomic creation
- PID file written after process confirmed running
- Clean shutdown removes all temporary files

#### NFR-3: Usability

**NFR-3.1** - Clear feedback at every stage
**NFR-3.2** - Errors include actionable suggestions
**NFR-3.3** - Status command provides comprehensive diagnostics
**NFR-3.4** - Rich formatting enhances readability without clutter

#### NFR-4: Maintainability

**NFR-4.1** - Modular agent architecture (easy to add new agents)
**NFR-4.2** - Message queue abstraction for inter-agent communication
**NFR-4.3** - Comprehensive logging with structured data
**NFR-4.4** - Type hints throughout codebase

#### NFR-5: Security

**NFR-5.1** - Session directories readable only by user (chmod 700)
**NFR-5.2** - API keys never logged or displayed in output
**NFR-5.3** - File content from RAG sanitized before sending to AI
**NFR-5.4** - Commands logged for audit trail

---

## Architecture Design

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     User Terminal                           │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  sm -a <command>  │  sm enable  │  sm disable  │ ...   │ │
│  └────────────────────────────────────────────────────────┘ │
└────────────────────────┬────────────────────────────────────┘
                         │ TCP Socket (127.0.0.1:9823)
                         ▼
┌─────────────────────────────────────────────────────────────┐
│             ShellMate Daemon Process (asyncio)              │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │           Main Thread (TCP Server)                   │   │
│  │  - Handle IPC requests                               │   │
│  │  - Run command pipeline                              │   │
│  │  - Coordinate agents via queues                      │   │
│  └─────────────────────────────────────────────────────┘   │
│                         │                                    │
│          ┌──────────────┼──────────────┐                    │
│          ▼              ▼              ▼                    │
│  ┌──────────────┐ ┌─────────────┐ ┌─────────────┐         │
│  │   Watcher    │ │  Librarian  │ │  Response   │         │
│  │   Agent      │ │   Agent     │ │   Queues    │         │
│  │  (asyncio    │ │  (asyncio   │ │  (per req)  │         │
│  │   task)      │ │   task)     │ │             │         │
│  └──────────────┘ └─────────────┘ └─────────────┘         │
│       │                  │                                   │
│       │ Environment      │ File Index                        │
│       │ Cache           │ + Watchdog                        │
│       ▼                  ▼                                   │
│  ┌──────────────────────────────────────────────┐          │
│  │   ~/.shellmate/sessions/{pid}/               │          │
│  │   - index.md (file list + metadata)          │          │
│  │   - env_cache.json (watcher data)            │          │
│  └──────────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

#### CLI Module (`cli/main.py`)
- Parse command-line arguments
- Handle `sm -a`, `sm enable`, `sm disable`, `sm status`, `sm config`
- Display Rich UI for startup/status
- Communicate with daemon via IPC client

#### Daemon Server (`daemon/server.py`)
- AsyncIO TCP server
- Launch and manage agent tasks
- Route requests to pipeline
- Coordinate agent communication via queues
- Handle graceful shutdown

#### Watcher Agent (`agents/watcher.py` - new file)
- Detect OS, shell, terminal, environment type
- Scan for tech stack indicators (package files, configs)
- Detect git repository and capture state
- Cache results in memory and `env_cache.json`
- Listen on `context_queue` for requests
- Run once at startup

#### Librarian Agent (`agents/librarian.py` - new file)
- Scan directory recursively at startup
- Build markdown index of files
- Start file watcher (watchdog)
- Update index on file changes
- Listen on `search_queue` for search requests
- Perform keyword/grep search and return results

#### Pipeline Module (`daemon/pipeline.py`)
- Enhanced with agent query logic
- Determine when to query Watcher (based on command type)
- Determine when to query Librarian (based on file references)
- Inject context into provider prompts
- Maintain existing stages: sanitizer, parser, rule engine, cache, risk, remediation

#### UI Module (`ui/` - new directory)
- `display.py`: Startup progress with Rich
- `banner.py`: ASCII art and greeting panels
- `analysis.py`: Command analysis output formatting
- `status.py`: Status command output formatting

#### Session Manager (`daemon/session.py` - new file)
- Create/destroy session directories
- Validate PID files
- Clean up stale sessions
- Track active directory

---

## Component Specifications

### 1. CLI Argument Parser

**File:** `cli/parser.py` (new)

**Interface:**
```python
class ShellMateCommandParser:
    def parse(self, args: List[str]) -> ParsedCommand:
        """
        Parse command line arguments.
        
        Args:
            args: sys.argv[1:]
            
        Returns:
            ParsedCommand with action and parameters
            
        Raises:
            InvalidCommandFormat with suggestion
        """
```

**Logic:**
- If `args[0] == "-a"`: Join `args[1:]` as command string
- If `args[0]` in `["enable", "disable", "status", "config"]`: Return subcommand
- Else: Raise `InvalidCommandFormat` with suggestion

**Error Handling:**
- Old format `analyze "cmd"` → Suggest `sm -a cmd`
- Missing `-a`: `sm git push` → Suggest `sm -a git push`
- Empty: Show usage with examples

### 2. Watcher Agent

**File:** `agents/watcher.py` (new)

**Interface:**
```python
class WatcherAgent:
    async def run(self, startup_queue: asyncio.Queue):
        """Main agent loop"""
        
    async def detect_environment(self) -> EnvironmentContext:
        """Detect OS, shell, terminal, tech stack, git"""
        
    def get_context(self, command: str) -> Optional[Dict]:
        """Return relevant context for command"""
```

**Data Structure:**
```python
@dataclass
class EnvironmentContext:
    os: str
    shell: str
    terminal: str
    env_type: str  # wsl, native, container, ssh
    tech_stack: List[TechStackItem]
    git: Optional[GitContext]

@dataclass
class TechStackItem:
    type: str  # package_manager, build_tool, runtime, framework
    name: str  # npm, webpack, Python, Django
    version: Optional[str]
    file_path: str

@dataclass
class GitContext:
    is_repo: bool
    branch: str
    uncommitted_changes: int
    staged_changes: int
    last_commit: str
```

**Detection Logic:**
- OS: `platform.system()`
- Shell: Parse `$SHELL`, check parent process
- Tech stack: Scan root dir for known file patterns
- Git: Run `git branch`, `git status --porcelain`, `git log -1`

**Context Relevance:**
```python
COMMAND_TO_CONTEXT = {
    "git": ["git"],
    "npm": ["tech_stack.npm"],
    "pip": ["tech_stack.pip"],
    "docker": ["tech_stack.docker"],
    "make": ["tech_stack.build_tools"],
    # ... more mappings
}
```

### 3. Librarian Agent

**File:** `agents/librarian.py` (new)

**Interface:**
```python
class LibrarianAgent:
    async def run(self, startup_queue: asyncio.Queue):
        """Main agent loop"""
        
    async def build_index(self):
        """Scan directory and build markdown index"""
        
    async def handle_file_event(self, event):
        """Update index on file changes (watchdog handler)"""
        
    def search(self, query: str) -> List[FileMatch]:
        """Keyword search in index"""
```

**Index Format (Markdown):**
```markdown
# ShellMate File Index

Generated: 2026-06-05 10:23:45
Total Files: 254

## Files

### /home/user/project/src/main.py
- Type: Python
- Size: 1.2KB
- Modified: 2026-06-05 09:15:30

### /home/user/project/package.json
- Type: JSON (npm)
- Size: 0.5KB
- Modified: 2026-06-04 16:20:11
- Content Preview: {...dependencies...}

...
```

**File Type Filter:**
```python
CODE_EXTENSIONS = {
    '.py', '.js', '.ts', '.jsx', '.tsx', '.rs', '.go', 
    '.java', '.c', '.cpp', '.h', '.rb', '.php', '.sh',
    '.bash', '.zsh', '.ps1', '.sql', '.md', '.txt',
    '.yaml', '.yml', '.json', '.toml', '.xml', '.env.example'
}
```

**Search Logic:**
- Simple case-insensitive keyword matching
- Search in: file paths, file names, content previews
- Return top 10 matches with context

Implementation note: index.md is a human-readable artifact for debugging and persistence, but the Librarian should maintain a structured in-memory index for fast queries (avoid disk I/O during search requests).

**Watchdog Integration:**
```python
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class IndexUpdateHandler(FileSystemEventHandler):
    def on_created(self, event):
        # Add to index
    def on_modified(self, event):
        # Update in index
    def on_deleted(self, event):
        # Remove from index
```

Note: watchdog runs in thread callbacks while searches and other pipeline code run in asyncio. Implementations MUST serialize index mutations (for example via a thread-safe queue processed by the Librarian's async loop, or an asyncio-compatible lock) to avoid race conditions between updates and queries.

### 4. Enhanced Pipeline

**File:** `daemon/pipeline.py` (modified)

**New Stages:**
```python
async def run_pipeline_v2(command: str, agent_queues: Dict) -> Dict:
    # Existing stages (sanitizer, parser, rule engine, cache)
    ...
    
    # NEW: Agent Context Gathering (Parallel Queries)
    context_start = time.time()
    
    # Determine which agents to query
    need_watcher = should_query_watcher(parsed_command)
    need_librarian = has_file_references(parsed_command)
    
    # Query both agents in parallel with explicit per-task timeouts
    tasks = []
    if need_watcher:
        tasks.append(asyncio.create_task(
            asyncio.wait_for(
                query_agent(
                    agent_queues['watcher'], 
                    {'action': 'get_context', 'command': command},
                ),
                timeout=0.5
            )
        ))
    if need_librarian:
        file_paths = extract_file_paths(parsed_command)
        tasks.append(asyncio.create_task(
            asyncio.wait_for(
                query_agent(
                    agent_queues['librarian'],
                    {'action': 'search', 'query': ' '.join(file_paths)},
                ),
                timeout=0.5
            )
        ))

    # Gather results (runs in parallel); tasks that exceed 500ms raise asyncio.TimeoutError and will be handled
    agent_results = await asyncio.gather(*tasks, return_exceptions=True) if tasks else []
    
    # Extract results
    watcher_context = agent_results[0] if need_watcher and len(agent_results) > 0 else None
    librarian_results = agent_results[-1] if need_librarian and len(agent_results) > 0 else None
    
    stages['agent_context'] = time.time() - context_start
    
    # Enhanced AI Analysis with context
    risk_result = analyze_risk(
        command=sanitized_command,
        watcher_context=watcher_context,
        librarian_results=librarian_results
    )
    
    # Enhanced Remediation with context
    remediation_result = generate_remediation(
        command=sanitized_command,
        risk=risk_result,
        watcher_context=watcher_context,
        librarian_results=librarian_results
    )
    
    return build_response(...)
```

**Helper Functions:**
```python
def should_query_watcher(parsed_cmd: Dict) -> bool:
    """Check if command relates to detected tech stack"""
    program = parsed_cmd.get('program')
    return program in CONTEXT_AWARE_COMMANDS

def has_file_references(parsed_cmd: Dict) -> bool:
    """Check if command mentions file paths"""
    program = parsed_cmd.get('program')
    args = parsed_cmd.get('arguments', [])
    
    # File manipulation commands
    if program in ['rm', 'mv', 'cp', 'chmod', 'chown', 'cat', 'less', 'nano', 'vim']:
        return True
    
    # Check arguments for paths (contain / or . prefix)
    return any('/' in arg or arg.startswith('.') for arg in args)
```

### 5. Message Queue Protocol

**Queues:**
```python
# Global queues in daemon
startup_progress_queue: asyncio.Queue  # Agents → CLI (during startup)
watcher_queue: asyncio.Queue           # Main → Watcher
librarian_queue: asyncio.Queue         # Main → Librarian
response_queues: Dict[str, asyncio.Queue]  # Agent → Main (per request_id)
```

**Message Format:**
```python
# Startup messages
{
    "stage": "watcher_ready" | "librarian_indexing" | "librarian_ready" | "ready",
    "data": {...}  # Optional metadata
}

# Context request (Main → Watcher)
{
    "request_id": "uuid",
    "action": "get_context",
    "command": "npm install express"
}

# Context response (Watcher → Main)
{
    "request_id": "uuid",
    "context": {
        "tech_stack": [...],
        "git": {...}
    }
}

# Search request (Main → Librarian)
{
    "request_id": "uuid",
    "action": "search",
    "query": "config.json"
}

# Search response (Librarian → Main)
{
    "request_id": "uuid",
    "results": [
        {"path": "...", "match_type": "filename", "snippet": "..."},
        ...
    ]
}
```

### 6. Session Management

**File:** `daemon/session.py` (new)

**Interface:**
```python
class SessionManager:
    @staticmethod
    def create_session(pid: int, directory: str) -> Path:
        """Create session directory for this daemon instance"""
        
    @staticmethod
    def cleanup_session(pid: int):
        """Remove session directory"""
        
    @staticmethod
    def get_active_session() -> Optional[Dict]:
        """Check if daemon is already running, return session info"""
        
    @staticmethod
    def cleanup_stale_sessions():
        """Remove sessions for dead processes"""
```

**Session Directory Structure:**
```
~/.shellmate/sessions/{pid}/
├── index.md              # Librarian's file index
├── env_cache.json        # Watcher's environment snapshot
└── session.json          # Metadata (directory, start_time)
```

### 7. Rich UI Components

**File:** `ui/display.py` (new)

See UI/UX Specifications section for detailed component designs.

---

## Data Flow

### Startup Flow (sm enable)

```
1. User: sm enable
   ↓
2. CLI checks for existing daemon
   ↓
3. Create session dir ~/.shellmate/sessions/{new_pid}/
   ↓
4. Fork daemon process
   ↓
5. Daemon: Launch Watcher + Librarian as asyncio tasks
   ↓
6. Watcher: Detect environment → Send progress to startup_queue
   ↓
7. Librarian: Build index → Send progress to startup_queue
   ↓
8. Both agents: Signal "ready" to startup_queue
   ↓
9. Daemon: Start TCP server
   ↓
10. CLI: Poll startup_queue, display Rich progress
   ↓
11. CLI: Show banner + greeting panel
   ↓
12. CLI: Exit, return control to terminal
```

### Command Analysis Flow (sm -a <cmd>)

```
1. User: sm -a rm -rf /tmp/cache
   ↓
2. CLI: Parse command, send to daemon via TCP
   ↓
3. Daemon: Receive request, run pipeline
   ↓
4. Pipeline: Sanitize → Parse → Rule Check → Cache Lookup
   ↓
5. Pipeline: Detect file reference "rm ... /tmp/cache"
   ↓
6. Pipeline: Query Librarian via queue
   {request_id: "123", action: "search", query: "/tmp/cache"}
   ↓
7. Librarian: Search index, return results
   {request_id: "123", results: [{path: "/tmp/cache", type: "dir"}]}
   ↓
8. Pipeline: Query Watcher (not relevant for rm, skip)
   ↓
9. Pipeline: Call AI Risk Analysis with librarian context
   ↓
10. Pipeline: Call AI Remediation with context
   ↓
11. Pipeline: Build response with risk + alternatives + context
   ↓
12. Daemon: Send response to CLI via TCP
   ↓
13. CLI: Parse response, display with Rich formatting
```

### File Change Flow (Background)

```
1. User: Creates new file project.config.json
   ↓
2. Watchdog: Detects file creation event
   ↓
3. Librarian: Check if file type is indexed
   ↓
4. Librarian: Read file metadata
   ↓
5. Librarian: Append to index.md
   ↓
6. Continue monitoring (no blocking)
```

### Shutdown Flow (sm disable)

```
1. User: sm disable
   ↓
2. CLI: Send shutdown signal to daemon (TCP or signal)
   ↓
3. Daemon: Cancel all agent tasks (Watcher, Librarian)
   ↓
4. Watcher: Stop immediately (no cleanup needed, in-memory only)
   ↓
5. Librarian: Stop watchdog observer, flush index
   ↓
6. Daemon: Close TCP server
   ↓
7. Daemon: Call SessionManager.cleanup_session()
   ↓
8. SessionManager: Delete ~/.shellmate/sessions/{pid}/
   ↓
9. CLI: Display "ShellMate disabled" with Rich formatting
```

---

## UI/UX Specifications

### Startup Progress Screen

**Layout:**
```
⠋ Starting ShellMate daemon...
⠙ Initializing Watcher Agent...
  └─ Detecting OS, shell, terminal...
  └─ Scanning for tech stack...
  └─ Checking git repository...
⠹ Starting Librarian Agent...
  └─ Scanning directory recursively...
  └─ Found 254 files to index...
⠸ Building file index...
⠴ Connecting to AI providers...
✓ All systems ready!
```

**Implementation:**
- Use `rich.progress.Progress` with `SpinnerColumn` and `TextColumn`
- Update tasks as messages arrive from `startup_progress_queue`
- Nested progress for sub-stages (using `add_task` with parent parameter)

### Greeting Banner

**ASCII Art:**
```
   _____ __         ____  __  ___      __       
  / ___// /_  ___  / / / /  |/  /___ _/ /____   
  \__ \/ __ \/ _ \/ / / / /|_/ / __ `/ __/ _ \  
 ___/ / / / /  __/ / / / /  / / /_/ / /_/  __/  
/____/_/ /_/\___/_/_/ /_/  /_/\__,_/\__/\___/   

Your Intelligent Command Safety Layer
```

**System Status Panel:**
```
╭─────────── System Status ───────────╮
│ OS            Linux                 │
│ Shell         bash                  │
│ Tech Stack    Node.js, Python       │
│ Git Branch    feature/v2-agents     │
│ Files Indexed 254                   │
╰─────────────────────────────────────╯
```

**Usage Panel:**
```
╭─────────── Usage ───────────────────╮
│ 📖 Usage:                            │
│   sm -a <command>  Analyze command  │
│   sm status        Check status     │
│   sm disable       Stop ShellMate   │
╰─────────────────────────────────────╯
```

### Command Analysis Output

**Example for HIGH risk:**
```
╭───────── Risk Level: HIGH ─────────╮
│ This command will recursively      │
│ delete files with force flag.      │
│                                     │
│ The directory /tmp/cache contains  │
│ tracked files with uncommitted     │
│ changes in your git repository.    │
╰────────────────────────────────────╯

╭──── Suggested Alternatives ────────╮
│  • First check contents:           │
│    ls -la /tmp/cache               │
│                                     │
│  • Create backup before delete:    │
│    tar -czf cache-backup.tar.gz ..│
│                                     │
│  • Use interactive mode:           │
│    rm -ri /tmp/cache               │
╰────────────────────────────────────╯

╭──────── Context Analysis ──────────╮
│ 📁 Related Files: /tmp/cache/      │
│ 🔧 Git Status: 3 uncommitted       │
╰────────────────────────────────────╯


⏱  sanitizer: 2ms • parser: 3ms • agents: 45ms • risk: 450ms • total: 500ms
```

**Color Scheme:**
- SAFE: Green border and title
- LOW: Blue border and title
- MEDIUM: Yellow border and title
- HIGH: Orange border and title (if supported, else red)
- CRITICAL: Bold red border, title, and text

### Status Command Output

**Three-Panel Layout:**
```
╭─────────── Daemon Status ──────────╮
│ Status: 🟢 Running                 │
│ PID: 12345                         │
│ Directory: /home/user/project      │
│ Uptime: 2h 15m                     │
╰────────────────────────────────────╯

╭─────────── Agent Status ───────────╮
│ Agent        Status      Details   │
│ ──────────────────────────────────│
│ Watcher      ✓ running   Cached   │
│ Librarian    ✓ running   254 files│
╰────────────────────────────────────╯

╭───────── AI Providers ─────────────╮
│ Provider     Status      Model     │
│ ──────────────────────────────────│
│ Groq         ✓ Configured llama-.. │
│ OpenRouter   ✓ Configured gpt-4o..│
╰────────────────────────────────────╯
```

### Error Message Examples

**Multi-session error:**
```
╭──────────── Error ─────────────────╮
│ ShellMate is already running in:   │
│ /home/user/other-project           │
│                                     │
│ To start here, first run:          │
│   cd /home/user/other-project      │
│   sm disable                        │
╰────────────────────────────────────╯
```

**Invalid format error:**
```
╭──────────── Error ─────────────────╮
│ Invalid command format.            │
│                                     │
│ Did you mean?                      │
│   sm -a git push origin main       │
│                                     │
│ Usage: sm -a <command>             │
╰────────────────────────────────────╯
```

---

## Error Handling & Graceful Degradation


### Agent Failure Scenarios

#### Librarian Agent Failures

**Scenario 1: File watching fails (inotify limits, permissions)**
- **Action:** Log error, disable background updates
- **User Impact:** RAG still works but doesn't reflect new files until restart
- **Message:** Warning in startup: "File watching disabled. Index will not update automatically."

**Scenario 2: Directory too large (>10K files)**
- **Action:** Index first 5K files, warn user
- **User Impact:** Partial RAG coverage
- **Message:** "Directory large, indexed 5000 files. Remaining files skipped."

**Scenario 3: Permission denied on files**
- **Action:** Skip unreadable files, continue indexing
- **User Impact:** Incomplete index
- **Message:** Warning: "Skipped X files due to permissions."

**Scenario 4: Index corruption**
- **Action:** Rebuild index from scratch
- **User Impact:** Startup delay
- **Fallback:** If rebuild fails, continue without RAG

#### Watcher Agent Failures

**Scenario 1: Git command fails (not in repo)**
- **Action:** Set `git: null` in context
- **User Impact:** No git-aware suggestions
- **No warning:** Common scenario

**Scenario 2: Tech stack detection fails**
- **Action:** Set `tech_stack: []`
- **User Impact:** No tech-specific context injection
- **Message:** Warning: "Could not detect tech stack."

**Scenario 3: Shell/OS detection fails**
- **Action:** Use defaults (shell=unknown, os=linux)
- **User Impact:** Generic environment context
- **Fallback:** System still functional

#### Pipeline Integration Failures

**Scenario 1: Agent query timeout (> 500ms)**
- **Action:** Continue analysis without agent context
- **User Impact:** Less contextual suggestions
- **Log:** "Agent timeout: watcher"

**Scenario 2: Queue communication error**
- **Action:** Retry once, then skip
- **User Impact:** Degraded to v1.0 behavior
- **Log:** "Failed to query agent"

### Daemon Failures

**Scenario 1: Crash during startup**
- **Action:** CLI displays error, cleans up PID file
- **User Impact:** Must retry enable
- **Message:** "Daemon failed to start. Check logs: sm logs"

**Scenario 2: Crash during operation**
- **Action:** Next command attempt fails, CLI detects stale PID
- **User Impact:** Must re-enable
- **Message:** "Daemon not responding. Run: sm enable"

**Scenario 3: Port already in use**
- **Action:** Try alternative port or fail gracefully
- **User Impact:** Cannot start daemon
- **Message:** "Port 9823 in use. Check for existing daemon."

### Recovery Mechanisms

**Stale Session Cleanup:**
```python
def cleanup_stale_sessions():
    for session_dir in sessions_path.iterdir():
        pid = int(session_dir.name)
        if not is_process_running(pid):
            shutil.rmtree(session_dir)
```

**Health Checks:**
- CLI validates PID before sending commands
- Daemon validates agent task status before routing
- Agents send heartbeat to startup queue every 30s (optional)

---

## Performance Requirements

### Latency Targets

| Operation | Target | Max Acceptable |
|-----------|--------|----------------|
| Startup (< 1000 files) | 5s | 10s |
| Startup (> 1000 files) | 10s | 20s |
| Command analysis (cache hit) | 50ms | 200ms |
| Command analysis (rule match) | 100ms | 300ms |
| Command analysis (AI, no agents) | 2s | 5s |
| Command analysis (AI + agents) | 2.5s | 6s |
| Agent query (Watcher) | 10ms (typical) | 500ms (hard cutoff) |
| Agent query (Librarian) | 50ms (typical) | 500ms (hard cutoff) |
| File indexing | 100 files/s | 50 files/s |

Note: These targets assume a modern development environment (SSD, >=4 CPU cores, Python 3.8+, reasonable I/O). Performance on HDDs, network mounts, or very large repositories (>5000 files) may be significantly slower; the system will warn the user and degrade gracefully.

### Resource Limits

**Memory:**
- Daemon base: 50-100MB
- Index (per 1000 files): ~10MB
- Agent tasks: ~20MB each
- Total target: < 150MB for typical project

**CPU:**
- Idle: < 1% CPU
- During indexing: < 50% CPU
- During command analysis: Burst to 100% acceptable

**Disk:**
- Session directory: ~10KB + (file_count * 1KB)
- Logs: Max 50MB (5 files × 10MB with rotation)

### Optimization Strategies

**Indexing:**
- Parallel file reading (asyncio.gather for batch reads)
- Skip binary detection (check magic bytes before full read)
- Incremental updates (only changed files)

**Agent Queries:**
- Timeout quickly (500ms) to prevent blocking
- Cache Watcher results (no need to recompute)
- Librarian uses in-memory index (no disk I/O per query)

**TCP Communication:**
- Connection pooling in CLI (reuse connection for multiple commands)
- JSON streaming for large responses (future optimization)

---

## Security Considerations

### Threat Model

**In Scope:**
- Accidental exposure of API keys in logs/output
- Unauthorized access to session data
- Command injection via malformed commands
- Path traversal in RAG file access

**Out of Scope:**
- Root/admin privilege escalation
- Network-based attacks (daemon only listens on localhost)
- Physical access to filesystem

### Security Measures

**1. API Key Protection**
- Store in `~/.shellmate/.env` with chmod 600
- Never log key values (only masked display)
- Never include in responses or errors
- Load from env file, inject into os.environ only

**2. Session Data Protection**
- Session directories: chmod 700 (user-only access)
- PID files: chmod 600
- Clean up on shutdown (no lingering sensitive data)

**3. Command Sanitization**
- All commands logged to audit trail
- No arbitrary code execution (commands analyzed, not executed)
- File paths validated before RAG access (must be within indexed directory)

**4. IPC Security**
- TCP socket on localhost only (127.0.0.1, not 0.0.0.0)
- No authentication (assumes single-user system)
- Consider Unix domain sockets for future (better isolation)

**5. AI Provider Communication**
- API calls over HTTPS only
- No PII in prompts (sanitize file paths, usernames)
- Rate limiting on provider errors (prevent key exhaustion)

### Audit Trail

**Log Format:**
```json
{
    "timestamp": "2026-06-05T10:23:45Z",
    "session_id": "12345",
    "command": "rm -rf /tmp/cache",
    "risk": "HIGH",
    "user_action": "executed" | "cancelled",
    "agents_used": ["librarian", "watcher"],
    "latency_ms": 523
}
```

**Log Location:** `~/.shellmate/logs/commands.log`

**Rotation:** 10MB per file, 5 files kept

---

## Decision Log

### Decision 1: Asyncio Over Multi-Process

**Decided:** Use asyncio tasks within single daemon process

**Alternatives:**
- Multi-process with IPC (separate process per agent)
- Threading (avoid GIL issues)

**Rationale:**
- IO-bound workload (file reading, network calls) benefits less from true parallelism
- Simpler debugging and error handling
- Lower memory overhead
- Native Python async patterns (no serialization for IPC)

**Trade-offs Accepted:**
- GIL may limit CPU-bound tasks (not a concern for this workload)
- Agent crash can kill daemon (mitigated with exception handling)

---

### Decision 2: Markdown Index Over Database

**Decided:** Use plain markdown file for RAG index

**Alternatives:**
- SQLite database
- JSON file
- In-memory only (no persistence)

**Rationale:**
- Human-readable for debugging
- Simple grep-based search sufficient
- No query complexity needed
- Fast file I/O for small-to-medium projects
- Session-based (deleted on disable, no long-term storage needed)

**Trade-offs Accepted:**
- Slower search for very large projects (>5000 files)
- Less structured than database (but adequate for keyword matching)
 - Mitigation: implementations should keep an in-memory structured index for fast queries and use index.md primarily for debugging/persistence.

---

### Decision 3: Single Daemon Instance

**Decided:** Only one daemon per user, regardless of directory

**Alternatives:**
- Multiple daemons (one per directory)
- Single daemon tracking multiple sessions

**Rationale:**
- Simpler lifecycle management (one PID file, one port)
- Prevents resource exhaustion (multiple daemons = multiple agents = high memory)
- Clear user mental model (enable/disable in one directory at a time)
- Most users work in one project at a time

**Trade-offs Accepted:**
- Cannot analyze commands in multiple projects simultaneously
- Must disable/enable to switch directories (acceptable for MVP)

---

### Decision 4: No Backwards Compatibility

**Decided:** Hard break from v1.x CLI, no migration path

**Alternatives:**
- Support both `shellmate analyze "cmd"` and `sm -a cmd` for 6 months
- Auto-migrate config files

**Rationale:**
- V1.x was MVP with limited adoption (assumed)
- Clean break allows simpler codebase
- New CLI is significantly different (not just renaming)
- Clear version signal (v2.0) indicates breaking changes

**Trade-offs Accepted:**
- Existing users must learn new commands
- Cannot run v1 and v2 side-by-side

---

### Decision 5: Rich Library for UI

**Decided:** Use Rich for all terminal output formatting

**Alternatives:**
- Plain ANSI escape codes
- Textual (full TUI framework)
- Click's built-in formatting

**Rationale:**
- Rich provides panels, tables, progress bars out-of-box
- Works cross-platform (Windows/Linux/macOS)
- Good balance of features vs complexity
- Active maintenance and documentation
- Already popular in Python ecosystem (familiar to users)

**Trade-offs Accepted:**
- Additional dependency (~2MB)
- Slightly slower than raw ANSI (negligible for this use case)

---

### Decision 6: Grep-Based Search (No Fuzzy Matching)

**Decided:** Simple keyword search, case-insensitive

**Alternatives:**
- Fuzzy matching (fzf-like)
- Full-text search with ranking
- Regex support

**Rationale:**
- YAGNI: Keyword search sufficient for file path matching
- Faster implementation and execution
- Predictable results (no ranking confusion)
- Can upgrade later if users request fuzzy matching

**Trade-offs Accepted:**
- Less forgiving of typos (user must type exact words)
- No "smart" ranking of results

---

### Decision 7: Session-Based RAG (No Persistence)

**Decided:** Delete index on `sm disable`, rebuild on `sm enable`

**Alternatives:**
- Persist index across sessions, track directory changes
- Hybrid: Cache index, validate on enable

**Rationale:**
- Avoids stale data (user switches branches, pulls changes)
- Simpler invalidation logic (no need to track file mtimes)
- Fresh index guarantees accuracy
- Startup cost (5-10s) acceptable for typical workflows

**Trade-offs Accepted:**
- Rebuild cost on every enable (mitigated by fast indexing)
- No instant-on for large projects

---

### Decision 8: 500ms Timeout for Agent Queries

**Decided:** Hard timeout at 500ms for agent responses

**Alternatives:**
- No timeout (wait indefinitely)
- Configurable timeout
- Adaptive timeout based on directory size

**Rationale:**
- User expects fast command analysis (< 6s total)
- Agent queries are "nice to have" not "must have"
- Prevents deadlock or hung agents from blocking pipeline
- 500ms sufficient for in-memory operations (Watcher cache, Librarian index search)

**Implementation note:** Agent timeouts should be enforced in the pipeline with per-task timeouts (for example `asyncio.wait_for`) and made configurable in future iterations. Tests should include a simulated slow agent to verify timeouts work as expected.

**Trade-offs Accepted:**
- May miss context on slow systems (very large directories)
- No user control over timeout

---

## Implementation Plan

### Phase 1: Foundation (Week 1-2)

**Goal:** Refactor CLI and establish agent framework

**Tasks:**
1. Create `cli/parser.py` with new argument parsing logic
2. Update `cli/main.py` to use new parser
3. Implement error suggestions (InvalidCommandFormat exception)
4. Create `agents/` directory structure
5. Define agent base class and message queue protocol
6. Create `daemon/session.py` for session management
7. Update `daemon/lifecycle.py` for new startup flow

**Verification:**
- `sm -a echo test` works and sends to daemon
- `sm enable` creates session directory
- `sm disable` cleans up session
- Invalid formats show suggestions

### Phase 2: Watcher Agent (Week 2-3)

**Goal:** Build environment detection and caching

**Tasks:**
1. Implement `agents/watcher.py`
2. OS/shell/terminal detection (reuse `environment/detector.py`)
3. Tech stack scanner (package.json, requirements.txt, etc.)
4. Git status integration (`subprocess` calls to git)
5. Context relevance logic (command-to-context mapping)
6. Queue handler for context requests
7. Unit tests for detection logic

**Verification:**
- Watcher detects Node.js project (package.json present)
- Watcher captures git branch and uncommitted changes
- `sm status` shows Watcher agent as "running"
- Context cache saved to `env_cache.json`

### Phase 3: Librarian Agent (Week 3-4)

**Goal:** Build file indexing and search

**Tasks:**
1. Implement `agents/librarian.py`
2. Directory scanner with file type filtering
3. Markdown index builder
4. Integrate `watchdog` for file monitoring
5. Keyword search implementation
6. Queue handler for search requests
7. Handle large directories (warn, limit)

**Verification:**
- Librarian indexes 500+ files in < 5s
- `index.md` contains correct file list
- File creation updates index automatically
- Search for "config.json" returns matching files

### Phase 4: Pipeline Integration (Week 4-5)

**Goal:** Connect agents to command analysis pipeline

**Tasks:**
1. Update `daemon/pipeline.py` with agent query logic
2. Implement `should_query_watcher()` and `has_file_references()`
3. Add agent context to provider prompts
4. Update `providers/groq_provider.py` to accept context
5. Update `providers/openrouter_provider.py` for remediation context
6. Add timeout handling for agent queries
7. Enhanced response format with context_used field

**Verification:**
- `sm -a npm install express` includes tech stack context
- `sm -a rm project.config` includes file from index
- Agent queries complete in < 500ms
- Analysis shows "Context Analysis" panel when context used

### Phase 5: Rich UI (Week 5-6)

**Goal:** Implement modern terminal interface

**Tasks:**
1. Create `ui/display.py` for startup progress
2. Create `ui/banner.py` for ASCII art and greeting
3. Create `ui/analysis.py` for command output
4. Create `ui/status.py` for status command
5. Integrate Rich Progress into `sm enable`
6. Update all CLI commands to use Rich formatting
7. Add color schemes for risk levels

**Verification:**
- `sm enable` shows stage-by-stage progress
- Greeting displays ASCII art + system info panel
- `sm -a rm -rf /` shows colored risk panel
- `sm status` displays three-panel layout

### Phase 6: Testing & Polish (Week 6-7)

**Goal:** Integration tests and edge case handling

**Tasks:**
1. Write integration tests for multi-agent flow
2. Test error scenarios (agent failures, timeouts)
3. Test large directory handling (5000+ files)
4. Test multi-session detection
5. Test graceful shutdown and cleanup
6. Update documentation (README, user guide)
7. Performance profiling and optimization

**Verification:**
- All unit tests pass
- Integration tests cover happy path + error cases
- Startup < 10s for 1000-file project
- Clean shutdown confirmed (session dir deleted)

### Phase 7: Release (Week 7)

**Goal:** Package and deploy v2.0

**Tasks:**
1. Update `pyproject.toml` version to 2.0.0
2. Generate changelog (breaking changes, new features)
3. Update shell adapters for new CLI format
4. Create migration guide from v1.x
5. Tag release in git
6. Publish to PyPI
7. Announce release with demo GIF/video

**Verification:**
- `pip install shellmate==2.0.0` works
- Fresh install: `sm install` → `sm enable` → `sm -a ls` works
- Documentation complete and accurate

---

## Assumptions

1. **Python 3.8+ Environment:** Users have modern Python with asyncio support
2. **Single-User Systems:** No multi-tenancy, daemon runs as user
3. **Git CLI Installed:** For git status detection (gracefully handles absence)
4. **Reasonable Project Sizes:** Most projects < 5000 files
5. **Fast Disk I/O:** SSD or equivalent for file indexing performance
6. **API Keys Configured:** Users will set up Groq/OpenRouter keys
7. **Shell Hook Installed:** Users will run `sm install` to set up shell integration
8. **Terminal Supports Color:** Modern terminals with ANSI support (fallback to plain text)
9. **Network Access:** For AI provider API calls (gracefully degrades on failure)
10. **User Understands Breaking Changes:** v2.0 clearly signals incompatibility

---

## Open Questions & Future Enhancements

### Open Questions

1. **Adaptive Timeouts:** Should agent timeouts scale with directory size?
2. **Cache Persistence:** Would users prefer persistent index across sessions?
3. **Multi-Session:** Demand for analyzing commands in multiple directories simultaneously?
4. **Plugin System:** Should v2.0 expose agent API for user-written agents?

### Future Enhancements (Post-MVP)

**V2.1 - Performance:**
- Persistent index with smart invalidation
- Parallel agent queries (both agents in parallel)
- Index compression for large projects

**V2.2 - Intelligence:**
- Learning mode (remember user preferences)
- Command history analysis (suggest based on past patterns)
- Fuzzy file search (fzf-like matching)
- Semantic code search (embeddings for related files)

**V2.3 - Integrations:**
- CI/CD detection (Jenkins, GitHub Actions files)
- Cloud provider context (AWS CLI, kubectl config)
- Container detection (detect if running inside Docker)
- IDE integration (VS Code extension)

**V2.4 - Collaboration:**
- Team rules (shared rule packs)
- Audit export (CSV/JSON reports)
- Slack/Discord notifications for CRITICAL commands
- Multi-user daemon (shared analysis for teams)

---

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Asyncio complexity causes bugs | High | Medium | Extensive testing, structured logging |
| Large directories slow startup | Medium | High | File type filtering, progress feedback |
| Agent deadlocks block pipeline | High | Low | Hard timeouts, circuit breakers |
| Users resist CLI change | Medium | Medium | Clear migration guide, demos |
| File watching fails on some systems | Low | Medium | Graceful degradation, clear warning |
| Memory usage too high | Medium | Low | Profile early, optimize index format |
| Git command slowness | Low | Low | Timeout git calls, cache results |

---

## Success Metrics

### Quantitative

- Startup time: < 10s for 95% of projects
- Command analysis latency: < 3s for 90% of commands
- Memory usage: < 150MB for typical project
- Crash rate: < 0.1% of commands
- User adoption: 80% of v1.x users migrate to v2.0 within 3 months

### Qualitative

- Users report CLI is "faster" and "easier to use"
- Context-aware suggestions rated as "helpful"
- Rich UI improves perceived professionalism
- No complaints about agent overhead or complexity

---

## Appendix A: File Type Extensions

**Indexed Types:**
```python
CODE_EXTENSIONS = {
    # Languages
    '.py', '.js', '.ts', '.jsx', '.tsx', '.rs', '.go',
    '.java', '.c', '.cpp', '.h', '.hpp', '.rb', '.php',
    '.swift', '.kt', '.scala', '.r', '.m', '.cs',
    
    # Web
    '.html', '.css', '.scss', '.sass', '.less', '.vue',
    '.svelte', '.astro',
    
    # Shell
    '.sh', '.bash', '.zsh', '.fish', '.ps1', '.bat', '.cmd',
    
    # Config
    '.json', '.yaml', '.yml', '.toml', '.ini', '.conf',
    '.env.example', '.env.template',
    
    # Data
    '.sql', '.graphql', '.proto', '.avro',
    
    # Docs
    '.md', '.rst', '.txt', '.adoc',
    
    # Build
    'Makefile', 'Dockerfile', 'docker-compose.yml',
    '.gitignore', '.dockerignore',
}
```

---

## Appendix B: Command-to-Context Mapping

**Watcher Context Triggers:**
```python
CONTEXT_TRIGGERS = {
    # Package managers
    'npm': ['tech_stack.npm', 'tech_stack.node'],
    'yarn': ['tech_stack.npm', 'tech_stack.node'],
    'pnpm': ['tech_stack.npm', 'tech_stack.node'],
    'pip': ['tech_stack.python'],
    'poetry': ['tech_stack.python'],
    'cargo': ['tech_stack.rust'],
    'go': ['tech_stack.go'],
    'bundle': ['tech_stack.ruby'],
    'composer': ['tech_stack.php'],
    
    # Build tools
    'make': ['tech_stack.build_tools'],
    'webpack': ['tech_stack.build_tools'],
    'vite': ['tech_stack.build_tools'],
    'gradle': ['tech_stack.build_tools'],
    'maven': ['tech_stack.build_tools'],
    
    # Git
    'git': ['git'],
    
    # Docker
    'docker': ['tech_stack.docker'],
    'docker-compose': ['tech_stack.docker'],
    
    # Cloud
    'kubectl': ['tech_stack.kubernetes'],
    'aws': ['tech_stack.aws'],
    'gcloud': ['tech_stack.gcp'],
}
```

---

## Appendix C: Example Prompts (Enhanced)

**Risk Analysis Prompt (with context):**
```
Analyze the safety of this command:

Command: npm install express

Environment Context:
- OS: Linux
- Shell: bash
- Project Type: Node.js (detected package.json)
- Tech Stack: React, TypeScript, Express
- Git: On branch 'feature/api', 2 uncommitted changes

Provide risk level (SAFE/LOW/MEDIUM/HIGH/CRITICAL) and reasoning.
```

**Remediation Prompt (with context):**
```
Command: rm -rf ./build

Risk: MEDIUM
Reason: Deleting directory recursively

File Context:
- ./build/ exists in project
- Contains 45 files (detected by RAG)
- No git tracking (build artifacts)

Tech Stack: Node.js project with webpack

Suggest safer alternatives or confirmation steps.
```

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-06-05 | Dev Team | Initial design specification |
| 1.1 | 2026-06-05 | Dev Team | Fixed contradictions and bottlenecks |

---

## Design Review - Issues Fixed

### Critical Fixes

**1. Asyncio/Thread Contradiction (CRITICAL)**
- **Issue:** FR-2.2 mentioned "background thread" but architecture uses asyncio tasks
- **Fix:** Specified watchdog Observer must run in ThreadPoolExecutor
- **Impact:** Prevents blocking asyncio event loop

**2. Startup Progress IPC Missing (CRITICAL)**
- **Issue:** CLI in different process cannot access in-memory startup_queue
- **Fix:** Changed to TCP-based status endpoint that CLI polls
- **Impact:** Makes startup progress actually implementable

### Performance Fixes

**3. Sequential Agent Queries (HIGH IMPACT)**
- **Issue:** Querying agents sequentially added up to 1000ms overhead
- **Fix:** Use `asyncio.gather()` to query both agents in parallel
- **Impact:** Reduces agent overhead from 1000ms to 500ms (50% improvement)

**4. Git Subprocess Overhead (MEDIUM IMPACT)**
- **Issue:** 3 separate git subprocess calls = 150-300ms on Windows
- **Recommendation:** Use pygit2 library or combine git commands
- **Impact:** Reduces git detection from 200ms to ~20ms

**5. Markdown Index Performance**
- **Issue:** Unclear if index is in-memory or disk-scanned per search
- **Clarification:** Index must be kept in-memory dictionary for fast lookup
- **Impact:** Ensures < 50ms search time even with 5000 files

### Specification Clarifications

**6. Watcher Agent Lifecycle**
- Clarified: Runs detection once, but keeps task alive to answer queue requests
- Does not re-detect, just returns cached results

**7. File Type Extensions**
- Consolidated FR-2.1 and Appendix A (Appendix A is authoritative)

**8. TCP Connection Strategy**
- Recommendation added for connection pooling (10-20ms saving per command)

### Still To Address in Implementation

**9. Watchdog Integration Pattern**
```python
# Must use executor to avoid blocking
loop = asyncio.get_event_loop()
observer = Observer()
await loop.run_in_executor(None, observer.start)
```

**10. Agent Query Retry Logic**
- Add single retry on timeout (transient failures)
- First timeout: 500ms, retry: 1000ms

---

**End of Specification**
