import asyncio
import logging
import time
import warnings
from typing import Any, Dict, List, Optional

warnings.warn(
    "agents.context_gatherer is deprecated. Use orchestration.analysis_graph instead.",
    DeprecationWarning,
    stacklevel=2,
)

from shellmate.agents.base import AgentResponse, get_agent_manager
from shellmate.agents.watcher import get_watcher_agent
from shellmate.agents.librarian import get_librarian_agent
from shellmate.parser.command_parser import parse_command
from shellmate.config.secrets import redact_dict

logger = logging.getLogger("shellmate.context_gatherer")

CONTEXT_TIMEOUT = 0.5  # 500ms hard cutoff

FILE_REF_PATTERN = ["./", "../", "/", ".\\", "..\\"]
CATEGORY_NEEDS_LIBRARIAN = {
    "file_ops", "file", "fs", "rm", "mv", "cp", "cat", "less", "more",
    "head", "tail", "nano", "vim", "vi", "code", "explorer",
    "open", "xdg-open", "start",
}


class ContextGatherer:
    def __init__(self):
        self._agent_manager = get_agent_manager()

    async def gather(self, command: str) -> Dict[str, Any]:
        start = time.monotonic()
        result: Dict[str, Any] = {
            "watcher": {},
            "librarian": {"matches": []},
            "timed_out": [],
            "errors": {},
            "partial": False,
            "latency_ms": 0.0,
            "agent_latency": {},
        }

        needs_watcher = True
        needs_librarian = self._needs_librarian(command)

        tasks = {}
        if needs_watcher:
            tasks["watcher"] = asyncio.create_task(
                self._query_watcher(command)
            )
        if needs_librarian:
            tasks["librarian"] = asyncio.create_task(
                self._query_librarian(command)
            )

        if not tasks:
            result["latency_ms"] = 0.0
            return result

        remaining = CONTEXT_TIMEOUT - (time.monotonic() - start)
        if remaining <= 0:
            for name in tasks:
                result["timed_out"].append(name)
            result["partial"] = True
            result["latency_ms"] = (time.monotonic() - start) * 1000
            return result

        done, pending = await asyncio.wait(
            tasks.values(),
            timeout=max(remaining, 0.001),
            return_when=asyncio.ALL_COMPLETED,
        )

        for name, task in tasks.items():
            if task in pending:
                task.cancel()
                result["timed_out"].append(name)
                result["partial"] = True
                continue

            try:
                agent_result = await task
                if name == "watcher":
                    result["watcher"] = agent_result or {}
                    result["agent_latency"]["watcher"] = agent_result.get("_latency_ms", 0) if agent_result else 0
                elif name == "librarian":
                    result["librarian"] = agent_result or {"matches": []}
                    result["agent_latency"]["librarian"] = agent_result.get("_latency_ms", 0) if agent_result else 0
            except asyncio.CancelledError:
                result["timed_out"].append(name)
                result["partial"] = True
            except Exception as e:
                result["errors"][name] = str(e)
                result["partial"] = True
                logger.warning(f"Context gatherer error for {name}: {e}")

        result["latency_ms"] = round((time.monotonic() - start) * 1000, 1)
        return result

    async def _query_watcher(self, command: str) -> Dict[str, Any]:
        start = time.monotonic()
        try:
            watcher = get_watcher_agent()
            if watcher.status.value != "ready":
                return {}
            response = await watcher.send_request(
                "get_context",
                timeout=CONTEXT_TIMEOUT,
            )
            elapsed = (time.monotonic() - start) * 1000
            if response.status == "ok":
                result = redact_dict(response.data)
                result["_latency_ms"] = round(elapsed, 1)
                return result
            return {}
        except Exception as e:
            logger.debug(f"Watcher query failed: {e}")
            return {}

    async def _query_librarian(self, command: str) -> Dict[str, Any]:
        start = time.monotonic()
        try:
            librarian = get_librarian_agent()
            if not librarian.is_indexed:
                return {"matches": []}
            response = await librarian.send_request(
                "search",
                data={"query": command},
                timeout=CONTEXT_TIMEOUT,
            )
            elapsed = (time.monotonic() - start) * 1000
            if response.status == "ok":
                data = response.data
                data["_latency_ms"] = round(elapsed, 1)
                return data
            return {"matches": []}
        except Exception as e:
            logger.debug(f"Librarian query failed: {e}")
            return {"matches": []}

    def _needs_librarian(self, command: str) -> bool:
        tokens = command.split()
        if not tokens:
            return False

        cmd = tokens[0].lower()
        if cmd in CATEGORY_NEEDS_LIBRARIAN:
            return True

        for token in tokens:
            for prefix in FILE_REF_PATTERN:
                if token.startswith(prefix) and len(token) > len(prefix):
                    return True

        parsed = parse_command(command)
        if isinstance(parsed, dict):
            cmd_type = parsed.get("command_type", "")
            if cmd_type in ("file_ops", "file_access"):
                return True

        return False


_context_gatherer: Optional[ContextGatherer] = None


def get_context_gatherer() -> ContextGatherer:
    global _context_gatherer
    if _context_gatherer is None:
        _context_gatherer = ContextGatherer()
    return _context_gatherer
