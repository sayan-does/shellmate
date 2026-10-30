import asyncio
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from collections import Counter

from shellmate.agents.base import Agent, AgentRequest, AgentResponse
from shellmate.agents.repomix_backend import get_repomix_backend
from shellmate.config.secrets import redact_secrets

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent, FileDeletedEvent, FileMovedEvent

    _HAS_WATCHDOG = True
except ImportError:
    _HAS_WATCHDOG = False

WATCHDOG_POLL_INTERVAL = 2.0
WATCHDOG_DEBOUNCE = 1.0

logger = logging.getLogger("shellmate.agents.librarian")

ELIGIBLE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".rs", ".go", ".java", ".rb",
    ".php", ".c", ".cpp", ".h", ".hpp", ".cs", ".swift", ".kt", ".scala",
    ".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".md", ".rst", ".txt", ".html", ".css", ".scss", ".less",
    ".xml", ".svg", ".dockerfile",
    ".env", ".env.example",
    ".gitignore", ".gitattributes",
    ".editorconfig", ".prettierrc", ".eslintrc",
    "Makefile", "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
}

EXCLUDE_DIRS = {
    ".git", "__pycache__", "node_modules", "venv", ".venv", "env",
    ".env", "virtualenv", ".virtualenv", ".tox", ".nox",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "target", "build", "dist", ".next", ".nuxt",
    ".cache", ".npm", ".yarn", ".pnpm-store",
    "vendor", ".bundle", "deps", "third_party",
    ".idea", ".vscode", ".vs",
    ".gitlab", ".github",
}

EXCLUDE_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    ".DS_Store", "Thumbs.db",
}

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",
    ".woff", ".woff2", ".ttf", ".eot",
    ".zip", ".tar", ".gz", ".bz2", ".xz",
    ".exe", ".dll", ".so", ".dylib", ".bin",
    ".o", ".a", ".lib", ".obj",
    ".pyc", ".pyo",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".mp3", ".mp4", ".avi", ".mov",
    ".db", ".sqlite", ".sqlite3",
}

MAX_FILES = 5000
MAX_MATCHES = 10
MAX_SNIPPET_LENGTH = 200


class _LibrarianFileHandler(FileSystemEventHandler):
    def __init__(self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
        self._queue = queue
        self._loop = loop

    def _put(self, item):
        try:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, item)
        except RuntimeError:
            pass

    def on_modified(self, event):
        if not event.is_directory:
            self._put(("modified", event.src_path))

    def on_created(self, event):
        if not event.is_directory:
            self._put(("created", event.src_path))

    def on_deleted(self, event):
        if not event.is_directory:
            self._put(("deleted", event.src_path))

    def on_moved(self, event):
        if not event.is_directory:
            self._put(("deleted", event.src_path))
            self._put(("created", event.dest_path))


class LibrarianAgent(Agent):
    def __init__(self):
        super().__init__("librarian")
        self._project_root: Optional[Path] = None
        self._files: List[Dict[str, Any]] = []
        self._index: Dict[str, List[int]] = {}
        self._ready = False
        self._scan_task: Optional[asyncio.Task] = None
        self._watchdog_queue: asyncio.Queue = asyncio.Queue()
        self._watchdog_task: Optional[asyncio.Task] = None
        self._repomix_task: Optional[asyncio.Task] = None
        self._observer: Optional[Observer] = None
        self._index_ready = asyncio.Event()

    async def initialize(self) -> None:
        self._project_root = Path.cwd()
        logger.info(f"Librarian initializing for project: {self._project_root}")
        self._scan_task = asyncio.create_task(self._scan_project())
        self._watchdog_task = asyncio.create_task(self._watchdog_worker())
        self._repomix_task = asyncio.create_task(self._init_repomix())

    async def _init_repomix(self) -> None:
        try:
            backend = get_repomix_backend()
            await backend.initialize()
        except Exception as e:
            logger.warning(f"Repomix initialization failed: {e}")

    async def shutdown(self) -> None:
        self._ready = False
        self._index_ready.clear()
        if self._observer:
            self._observer.stop()
            self._observer = None
        if self._watchdog_task:
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass
        if self._scan_task:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
        if self._repomix_task:
            self._repomix_task.cancel()
            try:
                await self._repomix_task
            except asyncio.CancelledError:
                pass
        self._files.clear()
        self._index.clear()
        try:
            backend = get_repomix_backend()
            await backend.cleanup()
        except Exception:
            pass

    async def process(self, request: AgentRequest) -> AgentResponse:
        if not self._ready:
            return AgentResponse(
                request_id=request.request_id,
                agent_name=self.name,
                status="not_ready",
                data={"matches": [], "partial": True},
                error="Librarian not yet initialized",
            )

        query = request.data.get("query", "")
        if not query:
            return AgentResponse(
                request_id=request.request_id,
                agent_name=self.name,
                status="ok",
                data={"matches": []},
            )

        start = time.monotonic()
        matches = self._search(query)
        latency = (time.monotonic() - start) * 1000

        return AgentResponse(
            request_id=request.request_id,
            agent_name=self.name,
            status="ok",
            data={"matches": matches},
            latency_ms=latency,
        )

    async def _scan_project(self) -> None:
        try:
            await self._scan_project_inner()
        except Exception as e:
            logger.error(f"Librarian scan failed: {e}", exc_info=True)
            self._ready = True
            self._index_ready.set()

    async def _scan_project_inner(self) -> None:
        if not self._project_root or not self._project_root.exists():
            logger.warning(f"Project root does not exist: {self._project_root}")
            self._ready = True
            self._index_ready.set()
            return

        eligible = 0
        skipped = {"binary": 0, "excluded_dir": 0, "excluded_file": 0, "other": 0}
        self._files = []

        for root, dirs, files in os.walk(self._project_root, topdown=True):
            rel_root = Path(root).relative_to(self._project_root)
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

            for f in files:
                if eligible >= MAX_FILES:
                    logger.warning(
                        f"Reached {MAX_FILES} file cap. Skipping remaining files."
                    )
                    break

                file_path = Path(root) / f
                rel_path = file_path.relative_to(self._project_root)

                if f in EXCLUDE_FILES:
                    skipped["excluded_file"] += 1
                    continue

                ext = file_path.suffix.lower()
                if ext in BINARY_EXTENSIONS:
                    skipped["binary"] += 1
                    continue

                if not self._is_eligible(file_path):
                    skipped["other"] += 1
                    continue

                file_record = self._index_file(file_path, rel_path)
                if file_record:
                    self._files.append(file_record)
                    eligible += 1

            if eligible >= MAX_FILES:
                break

        self._build_index()
        self._write_debug_index()

        total_skipped = sum(skipped.values())
        logger.info(
            f"Indexed {eligible} files"
            + (f", skipped {total_skipped} files" if total_skipped else "")
        )
        self._ready = True
        self._index_ready.set()

    def _is_eligible(self, file_path: Path) -> bool:
        ext = file_path.suffix.lower()
        if ext in ELIGIBLE_EXTENSIONS:
            return True
        name = file_path.name.lower()
        if name in ("makefile", "dockerfile", "procfile"):
            return True
        if name.startswith(".") and ext:
            return True
        return False

    def _index_file(self, file_path: Path, rel_path: Path) -> Optional[Dict[str, Any]]:
        try:
            size = file_path.stat().st_size
            if size > 1024 * 1024:
                return None

            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
            except (OSError, UnicodeDecodeError):
                return None

            snippet = self._make_snippet(content)

            return {
                "path": str(rel_path).replace("\\", "/"),
                "size": size,
                "ext": file_path.suffix.lower(),
                "snippet": snippet,
            }
        except OSError as e:
            logger.debug(f"Permission error reading {file_path}: {e}")
            return None

    def _make_snippet(self, content: str) -> str:
        lines = content.split("\n")
        if not lines:
            return ""
        non_empty = [l for l in lines if l.strip()]
        if not non_empty:
            return ""

        combined = "\n".join(lines[:20])
        if len(combined) > MAX_SNIPPET_LENGTH:
            combined = combined[: MAX_SNIPPET_LENGTH - 3] + "..."
        return combined

    def _build_index(self) -> None:
        self._index = {}
        for idx, file_record in enumerate(self._files):
            path = file_record["path"]
            tokens = self._tokenize(path)
            stem = Path(path).stem
            tokens.extend(self._tokenize(stem))
            tokens = list(set(tokens))

            for token in tokens:
                if token not in self._index:
                    self._index[token] = []
                self._index[token].append(idx)

    def _tokenize(self, text: str) -> List[str]:
        parts = re.split(r"[/\\\.\-_ ]", text.lower())
        result = []
        for part in parts:
            if len(part) >= 2:
                result.append(part)
            sub_parts = re.findall(r"[a-z]+|[A-Z][a-z]*|\d+", part)
            for sp in sub_parts:
                sp_lower = sp.lower()
                if len(sp_lower) >= 2 and sp_lower != part:
                    result.append(sp_lower)
        return result

    def _search(self, query: str) -> List[Dict[str, Any]]:
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        path_token = query.lower().replace("\\", "/")
        doc_scores = Counter()

        for idx, file_record in enumerate(self._files):
            file_path = file_record["path"].lower()
            score = 0

            if path_token in file_path:
                score += 10
            if file_path == path_token:
                score += 20

            file_stem = Path(file_record["path"]).stem.lower()
            if file_stem == path_token:
                score += 5

            if score > 0:
                doc_scores[idx] += score

        for token in query_tokens:
            if token in self._index:
                for idx in self._index[token]:
                    doc_scores[idx] += 1

            for idx, file_record in enumerate(self._files):
                if token in file_record["snippet"].lower():
                    doc_scores[idx] += 0.5

        ranked = sorted(doc_scores.items(), key=lambda x: (-x[1], self._files[x[0]]["path"]))
        matches = []
        for idx, score in ranked[:MAX_MATCHES]:
            file_record = self._files[idx]
            matches.append({
                "path": file_record["path"],
                "score": round(score, 1),
                "snippet": redact_secrets(file_record["snippet"]),
                "size": file_record["size"],
            })

        return matches

    def _start_file_watcher(self) -> None:
        if not self._project_root:
            return
        if _HAS_WATCHDOG:
            try:
                handler = _LibrarianFileHandler(self._watchdog_queue, asyncio.get_running_loop())
                self._observer = Observer()
                self._observer.schedule(handler, str(self._project_root), recursive=True)
                self._observer.start()
                logger.info("Watchdog file watcher started")
            except Exception as e:
                logger.warning(f"Failed to start watchdog: {e}. Falling back to polling.")
                self._observer = None
        if not self._observer:
            logger.info("Polling-based file watcher not implemented; index refresh on demand only")

    async def _watchdog_worker(self) -> None:
        try:
            await self._scan_task
        except asyncio.CancelledError:
            return
        self._start_file_watcher()
        pending: Dict[str, str] = {}
        while True:
            try:
                event_type, path = await asyncio.wait_for(
                    self._watchdog_queue.get(), timeout=WATCHDOG_DEBOUNCE
                )
            except asyncio.TimeoutError:
                if pending:
                    await self._process_watchdog_batch(pending)
                    pending.clear()
                continue
            except asyncio.CancelledError:
                if pending:
                    await self._process_watchdog_batch(pending)
                break

            if not self._project_root:
                continue
            try:
                rel_path = Path(path).relative_to(self._project_root)
            except ValueError:
                continue

            if any(part in EXCLUDE_DIRS for part in rel_path.parts):
                continue
            file_path = Path(path)
            if file_path.name in EXCLUDE_FILES:
                continue
            ext = file_path.suffix.lower()
            if ext in BINARY_EXTENSIONS:
                continue
            if not self._is_eligible(file_path):
                continue

            rel_str = str(rel_path).replace("\\", "/")
            pending[rel_str] = event_type

    def _remove_file(self, rel_path: str) -> None:
        for idx, record in enumerate(self._files):
            if record["path"] == rel_path:
                self._files.pop(idx)
                return

    def _rebuild_index(self) -> None:
        self._build_index()

    async def _process_watchdog_batch(self, pending: Dict[str, str]) -> None:
        for rel_str, event_type in pending.items():
            if event_type == "deleted":
                self._remove_file(rel_str)
                logger.debug(f"Watchdog removed: {rel_str}")
            else:
                file_path = self._project_root / rel_str
                rel_path = Path(rel_str)
                record = self._index_file(file_path, rel_path)
                if record:
                    self._remove_file(rel_str)
                    self._files.append(record)
                    logger.debug(f"Watchdog updated: {rel_str}")
        self._rebuild_index()
        logger.debug(f"Watchdog batch processed {len(pending)} changes")

    def _write_debug_index(self) -> None:
        from shellmate.daemon.session import get_session_dir_path
        session_dir = get_session_dir_path()
        try:
            session_dir.mkdir(parents=True, exist_ok=True)
            index_path = session_dir / "index.md"
            with open(index_path, "w", encoding="utf-8") as f:
                f.write(f"# ShellMate Librarian Index\n")
                f.write(f"Project: {self._project_root}\n")
                f.write(f"Files: {len(self._files)}\n")
                f.write(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                for file_record in sorted(self._files, key=lambda x: x["path"]):
                    f.write(f"- {file_record['path']} ({file_record['size']} bytes)\n")
            logger.debug(f"Debug index written to {index_path}")
        except OSError as e:
            logger.warning(f"Failed to write debug index: {e}")

    @property
    def file_count(self) -> int:
        return len(self._files)

    @property
    def is_indexed(self) -> bool:
        return self._ready


_librarian_agent: Optional[LibrarianAgent] = None


def get_librarian_agent() -> LibrarianAgent:
    global _librarian_agent
    if _librarian_agent is None:
        _librarian_agent = LibrarianAgent()
    return _librarian_agent
