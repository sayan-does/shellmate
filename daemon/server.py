import asyncio
import json
import logging
import logging.handlers
import os
import time
from config.defaults import get_default_config, SHELLMATE_DIR
from daemon.pipeline import run_pipeline
from cache.semantic_cache import preload_embedder_async
from daemon.pipeline import run_pipeline_async
from daemon.session import read_session, is_session_stale, validate_session_ownership

logger = logging.getLogger("shellmate.daemon")

MAX_REQUEST_SIZE = 1024 * 1024
READ_TIMEOUT = 30.0
WRITE_TIMEOUT = 30.0

STARTUP_STAGES = [
    "binding_ipc",
    "watcher_starting",
    "watcher_ready",
    "librarian_scanning",
    "librarian_ready",
    "providers_checked",
    "ready",
]

_startup_stage = "binding_ipc"
_start_time = time.time()
_last_health_check = None


def get_startup_stage():
    global _startup_stage
    return _startup_stage


def set_startup_stage(stage: str):
    global _startup_stage
    if stage in STARTUP_STAGES:
        _startup_stage = stage
        logger.info(f"Startup stage: {stage}")


class ShellMateDaemon:
    def __init__(self):
        self.config = get_default_config()
        self.server = None
        self._running = False

    async def handle_client(self, reader, writer):
        request_id = None
        client_addr = writer.get_extra_info('peername')
        try:
            data = await asyncio.wait_for(reader.read(MAX_REQUEST_SIZE), timeout=READ_TIMEOUT)
            if not data:
                writer.close()
                return

            if len(data) > MAX_REQUEST_SIZE:
                response = {"status": "error", "request_id": "unknown", "error": "Request too large"}
                writer.write(json.dumps(response).encode("utf-8"))
                await writer.drain()
                writer.close()
                return

            try:
                message = json.loads(data.decode("utf-8"))
            except json.JSONDecodeError as e:
                response = {"status": "error", "request_id": "unknown", "error": f"Invalid JSON: {e}"}
                writer.write(json.dumps(response).encode("utf-8"))
                await writer.drain()
                writer.close()
                return

            request_id = message.get("request_id", "unknown")
            command = message.get("command", "")

            logger.debug(f"Received command from {client_addr}: {command[:50]} (id={request_id})")

            is_valid, error_msg = self._validate_ipc_request(command)
            if not is_valid:
                response = {"status": "error", "request_id": request_id, "error": error_msg}
                writer.write(json.dumps(response).encode("utf-8"))
                await writer.drain()
                writer.close()
                return

            if command == "/status":
                result = self._handle_status()
            elif command == "/context-gatherer":
                result = await self._handle_context_gatherer(message)
            elif command == "shutdown":
                result = {"status": "ok", "message": "Shutting down"}
                asyncio.create_task(self._shutdown())
            elif command == "health":
                result = {"status": "ok", "healthy": True}
            else:
                logger.info(f"Processing command from {client_addr}: {command[:50]}")
                try:
                    from orchestration.analysis_graph import get_analysis_graph
                    graph = get_analysis_graph()
                    result = await graph.analyze_command(command)
                    logger.info(f"Graph analysis completed for: {command[:50]}")
                except ImportError:
                    result = await run_pipeline_async(command)
                    logger.info(f"Pipeline completed for: {command[:50]}")
                except Exception as e:
                    logger.error(f"Pipeline error: {e}", exc_info=True)
                    raise

            response = {"status": "ok", "request_id": request_id, **result}

        except json.JSONDecodeError as e:
            response = {"status": "error", "request_id": request_id, "error": f"Invalid JSON: {e}"}
        except Exception as e:
            logger.error(f"Error processing request from {client_addr}: {e}")
            response = {"status": "error", "request_id": request_id, "error": str(e)}

        try:
            writer.write(json.dumps(response).encode("utf-8"))
            await asyncio.wait_for(writer.drain(), timeout=WRITE_TIMEOUT)
        except Exception as e:
            logger.error(f"Error writing response: {e}")
        finally:
            writer.close()
            await writer.wait_closed()

    async def _handle_context_gatherer(self, message):
        command = message.get("command", "") or message.get("data", {}).get("command", "")
        request_id = message.get("request_id", "unknown")

        if not command:
            return {
                "watcher": {},
                "librarian": {"matches": []},
                "timed_out": [],
                "errors": {},
                "partial": False,
                "latency_ms": 0,
                "agent_latency_ms": {"watcher": 0, "librarian": 0},
            }

        try:
            from orchestration.analysis_graph import get_analysis_graph
            graph = get_analysis_graph()
            result = await graph.gather_context(command)
            return result
        except ImportError:
            from agents.context_gatherer import get_context_gatherer
            gatherer = get_context_gatherer()
            result = await gatherer.gather(command)
            result["agent_latency_ms"] = {
                "watcher": result.get("agent_latency", {}).get("watcher", 0),
                "librarian": result.get("agent_latency", {}).get("librarian", 0),
            }
            return result

    def _validate_ipc_request(self, command: str) -> tuple:
        exempt_commands = ("/status", "health")
        if command in exempt_commands:
            return True, ""
        session = read_session()
        if not session:
            return False, "No active session. Run 'sm enable' first."
        if is_session_stale(session):
            return False, "Session is stale (daemon process not running). Run 'sm enable' again."
        if not validate_session_ownership(session):
            return False, "Session owner mismatch. Run 'sm disable' and 'sm enable' again."
        return True, ""

    def _handle_status(self):
        global _last_health_check
        now = time.time()
        _last_health_check = now
        return {
            "status": "ok",
            "data": {
                "startup_stage": get_startup_stage(),
                "uptime_seconds": now - _start_time,
                "last_health_check": now,
                "daemon_pid": os.getpid(),
            }
        }

    async def start(self):
        cfg = self.config["daemon"]
        host = cfg["host"]
        port = cfg["port"]

        self.server = await asyncio.start_server(
            self.handle_client, host, port
        )

        addr = self.server.sockets[0].getsockname()
        logger.info(f"Daemon listening on {addr[0]}:{addr[1]}")
        self._running = True

    async def serve(self):
        async with self.server:
            await self.server.serve_forever()

    async def stop(self):
        self._running = False
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        logger.info("Daemon stopped")

    async def _shutdown(self):
        await self.stop()

    @property
    def is_running(self):
        return self._running


def run_daemon():
    log_dir = os.path.join(SHELLMATE_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, "daemon.log")
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=10485760, backupCount=5
    )
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[file_handler, logging.StreamHandler()],
    )

    daemon = ShellMateDaemon()

    async def main():
        from agents.base import get_agent_manager, AgentManager
        from agents.watcher import WatcherAgent
        from agents.librarian import LibrarianAgent

        agent_mgr = get_agent_manager()
        watcher = WatcherAgent()
        librarian = LibrarianAgent()

        agent_mgr.register(watcher)
        agent_mgr.register(librarian)

        set_startup_stage("binding_ipc")
        await daemon.start()

        set_startup_stage("watcher_starting")
        set_startup_stage("librarian_scanning")

        async def _start_watcher():
            await watcher.start()
            set_startup_stage("watcher_ready")

        async def _start_librarian():
            preload_embedder_async()
            await librarian.start()
            await librarian.wait_until_indexed()
            set_startup_stage("librarian_ready")

        await asyncio.gather(_start_watcher(), _start_librarian())

        set_startup_stage("providers_checked")
        set_startup_stage("ready")

        try:
            await daemon.serve()
            logger.info("Daemon server stopped")
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
            await agent_mgr.stop_all()
            await daemon.stop()
        except Exception as e:
            logger.error(f"Daemon error: {e}", exc_info=True)
            await agent_mgr.stop_all()
            await daemon.stop()
            raise

    asyncio.run(main())
