import asyncio
import json
import uuid
from config.defaults import get_default_config


class ShellMateClient:
    def __init__(self):
        self.config = get_default_config()

    async def send_command(self, command, timeout=10.0):
        cfg = self.config["daemon"]
        host = cfg["host"]
        port = cfg["port"]

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=5.0,
            )

            request_id = str(uuid.uuid4())
            message = json.dumps({
                "command": command,
                "request_id": request_id,
            })

            writer.write(message.encode("utf-8"))
            await writer.drain()

            data = await asyncio.wait_for(
                reader.read(65536),
                timeout=timeout,
            )

            writer.close()
            return json.loads(data.decode("utf-8"))

        except asyncio.TimeoutError:
            return {"status": "error", "error": "Connection timed out. Is the daemon running?"}
        except ConnectionRefusedError:
            return {"status": "error", "error": "Connection refused. Run 'sm enable' first."}
        except Exception as e:
            return {"status": "error", "error": str(e)}


def analyze_command(command):
    client = ShellMateClient()
    try:
        result = asyncio.run(client.send_command(command))
        return result
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(client.send_command(command))
            return result
        finally:
            loop.close()


def send_status():
    client = ShellMateClient()
    try:
        result = asyncio.run(client.send_command("/status"))
        return result
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(client.send_command("/status"))
            return result
        finally:
            loop.close()