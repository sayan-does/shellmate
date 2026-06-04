import asyncio
import json
import logging
import logging.handlers
import os
from config.defaults import get_default_config, SHELLMATE_DIR
from daemon.pipeline import run_pipeline

logger = logging.getLogger("shellmate.daemon")


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

            result = run_pipeline(command)
            response = {"status": "ok", "request_id": request_id, **result}

        except json.JSONDecodeError as e:
            response = {"status": "error", "request_id": request_id, "error": f"Invalid JSON: {e}"}
        except Exception as e:
            logger.error(f"Error processing request: {e}")
            response = {"status": "error", "request_id": request_id, "error": str(e)}

        writer.write(json.dumps(response).encode("utf-8"))
        await writer.drain()
        writer.close()

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

    try:
        asyncio.run(daemon.start())
    except KeyboardInterrupt:
        asyncio.run(daemon.stop())
