# ShellMate v2.0 Design Review - Findings & Fixes

**Review Date:** June 5, 2026  
**Reviewer:** Design Analysis  
**Status:** ✅ Issues Identified & Fixed

---

## Executive Summary

Found **10 issues** in initial design:
- **2 Critical** (blocking implementation)
- **3 High-impact** (performance bottlenecks)
- **5 Medium** (clarifications needed)

All critical issues have been **resolved** in the specification.

---

## Critical Issues (Fixed)

### 🔴 Issue #1: Asyncio/Threading Contradiction

**Problem:**
- FR-2.2 stated: "Run in background **thread**"
- Architecture shows: Librarian as **asyncio task**
- Decision Log chose single-process asyncio (no threads)
- Watchdog library internally uses threads → mixing with asyncio causes issues

**Impact:** Could cause deadlocks or event loop blocking

**Fix Applied:**
```markdown
FR-2.2 now specifies:
"Run watchdog Observer in ThreadPoolExecutor to avoid blocking asyncio event loop"
```

**Implementation Note:**
```python
# In LibrarianAgent.run()
loop = asyncio.get_event_loop()
observer = Observer()
observer.schedule(handler, self.directory, recursive=True)
await loop.run_in_executor(None, observer.start)
```

---

### 🔴 Issue #2: Startup Progress IPC Missing

**Problem:**
- Data Flow shows CLI "polls startup_queue"
- But startup_queue is `asyncio.Queue` (in-memory, single process)
- CLI runs in different process than daemon
- **No mechanism for CLI to access daemon's queue**

**Impact:** Startup progress UI feature is unimplementable as designed

**Fix Applied:**
