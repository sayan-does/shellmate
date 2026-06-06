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

logger = logging.getLogger("shellmate.daemon")

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
        try:
            data = await reader.read(65536)
            if not data:
                writer.close()
                return

            message = json.loads(data.decode("utf-8"))
            request_id = message.get("request_id", "unknown")
            command = message.get("command", "")

            logger.debug(f"Received command: {command} (id={request_id})")

            if command == "/status":
                result = self._handle_status()
            elif command == "shutdown":
                result = {"status": "ok", "message": "Shutting down"}
                asyncio.create_task(self._shutdown())
            elif command == "health":
                result = {"status": "ok", "healthy": True}
            else:
                logger.info(f"Processing command: {command[:50]}")
                try:
                    result = await run_pipeline_async(command)
                    logger.info(f"Pipeline completed for: {command[:50]}")
                except Exception as e:
                    logger.error(f"Pipeline error: {e}", exc_info=True)
                    raise

            response = {"status": "ok", "request_id": request_id, **result}

        except json.JSONDecodeError as e:
            response = {"status": "error", "request_id": request_id, "error": f"Invalid JSON: {e}"}
        except Exception as e:
            logger.error(f"Error processing request: {e}")
            response = {"status": "error", "request_id": request_id, "error": str(e)}

        writer.write(json.dumps(response).encode("utf-8"))
        await writer.drain()
        writer.close()

    def _handle_status(self):
        return {
            "status": "ok",
            "data": {
                "startup_stage": get_startup_stage(),
                "uptime_seconds": time.time() - _start_time,
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

    set_startup_stage("binding_ipc")

    daemon = ShellMateDaemon()

    async def main():
        set_startup_stage("watcher_starting")
        set_startup_stage("watcher_ready")

        # Preload embedding model in background
        preload_embedder_async()
        set_startup_stage("librarian_scanning")
        set_startup_stage("librarian_ready")
        set_startup_stage("providers_checked")
        set_startup_stage("ready")

        try:
            logger.info("Starting daemon server...")
            await daemon.start()
            logger.info("Daemon server stopped")
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
            await daemon.stop()
        except Exception as e:
            logger.error(f"Daemon error: {e}", exc_info=True)
            raise

    asyncio.run(main())