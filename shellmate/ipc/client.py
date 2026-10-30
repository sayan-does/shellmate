import asyncio
import json
import uuid
import threading
from shellmate.config.defaults import get_default_config


class DebouncedClient:
    """Debounced API caller for autocomplete mode (300ms delay)"""
    
    def __init__(self, delay_ms=300):
        self.delay = delay_ms / 1000.0
        self.timer = None
        self.callback = None
    
    def debounce(self, callback, *args, **kwargs):
        """Reset timer on each call, execute only after delay"""
        if self.timer:
            self.timer.cancel()
        
        self.timer = threading.Timer(
            self.delay,
            lambda: callback(*args, **kwargs)
        )
        self.timer.start()
    
    def cancel(self):
        """Cancel pending debounced call"""
        if self.timer:
            self.timer.cancel()

# Global instance for ble.sh plugin to use
_debounced_client = DebouncedClient(delay_ms=300)


class ShellMateClient:
    def __init__(self):
        self.config = get_default_config()

    async def send_command(self, command, user_queries=None, overrides=None, directives=None, timeout=60.0):
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
                "user_queries": user_queries or [],
                "overrides": overrides or {},
                "directives": directives or [],
            })

            writer.write(message.encode("utf-8"))
            await writer.drain()

            data = await asyncio.wait_for(
                reader.read(1024 * 1024),
                timeout=timeout,
            )

            writer.close()
            await writer.wait_closed()
            return json.loads(data.decode("utf-8"))

        except asyncio.TimeoutError:
            return {"status": "error", "error": "Connection timed out. Is the daemon running?"}
        except ConnectionRefusedError:
            return {"status": "error", "error": "Connection refused. Run 'sm enable' first."}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def send_command_partial(self, partial, timeout=5.0):
        """Fast partial analysis for autocomplete"""
        cfg = self.config["daemon"]
        host, port = cfg["host"], cfg["port"]
        
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=2.0
            )
            
            message = json.dumps({
                "command": "/analyze-partial",
                "request_id": str(uuid.uuid4()),
                "partial": partial
            })
            
            writer.write(message.encode("utf-8"))
            await writer.drain()
            
            data = await asyncio.wait_for(reader.read(1024*1024), timeout=timeout)
            writer.close()
            await writer.wait_closed()
            return json.loads(data.decode("utf-8"))
        except Exception as e:
            return {"status": "error", "error": str(e)}


def analyze_command(command, user_queries=None, overrides=None, directives=None):
    client = ShellMateClient()
    try:
        result = asyncio.run(client.send_command(command, user_queries=user_queries, overrides=overrides, directives=directives))
        return result
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(client.send_command(command, user_queries=user_queries, overrides=overrides, directives=directives))
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



def analyze_partial_debounced(partial_command, callback):
    """
    Analyze partial command with 300ms debounce.
    callback(result) is called when API responds.
    """
    def _do_analyze():
        try:
            client = ShellMateClient()
            result = asyncio.run(client.send_command_partial(partial_command))
            if result.get("status") == "error":
                # Silent fallback: no annotation shown
                callback({"annotation": "", "severity": "SAFE"})
            else:
                callback(result)
        except (ConnectionRefusedError, asyncio.TimeoutError):
            # Daemon down: silent fallback (instant tier still works)
            callback({"annotation": "", "severity": "SAFE"})
        except Exception as e:
            # Any other error: silent fallback
            callback({"annotation": "", "severity": "SAFE"})
    
    _debounced_client.debounce(_do_analyze)
