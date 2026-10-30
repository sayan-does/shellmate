import os
import signal
import socket
import subprocess
import sys
import time
import json
from shellmate.config.defaults import get_default_config
from shellmate.daemon.session import (
    create_session, read_session, remove_session,
    cleanup_stale_sessions, validate_session_ownership,
    get_session_dir_path, is_process_alive
)


def _check_port_in_use(host: str, port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex((host, port))
            return result == 0
    except Exception:
        return False


def _query_daemon_status(host, port):
    """Synchronously query daemon /status, return data dict or None."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect((host, port))
        message = json.dumps({"command": "/status", "request_id": "lifecycle"})
        s.sendall(message.encode("utf-8"))
        data = s.recv(4096)
        s.close()
        result = json.loads(data.decode("utf-8"))
        if isinstance(result, dict) and result.get("status") == "ok":
            return result.get("data", {})
    except Exception:
        pass
    return None


def _is_shellmate_status(status_data):
    return bool(status_data and "startup_stage" in status_data)


def _find_pid_listening_on_port(host: str, port: int):
    try:
        import psutil

        for conn in psutil.net_connections(kind="tcp"):
            if not conn.laddr or conn.laddr.port != port:
                continue
            if conn.status != psutil.CONN_LISTEN:
                continue
            if host in ("0.0.0.0", "127.0.0.1", "::1", "::"):
                if conn.laddr.ip in ("0.0.0.0", "127.0.0.1", "::", "::1", host):
                    return conn.pid
            elif conn.laddr.ip == host:
                return conn.pid
    except Exception:
        pass

    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            for line in result.stdout.splitlines():
                if f"{host}:{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    if parts:
                        return int(parts[-1])
        except Exception:
            pass
    return None


def _resolve_daemon_pid(host: str, port: int, status_data):
    if status_data and status_data.get("daemon_pid"):
        return status_data["daemon_pid"]
    return _find_pid_listening_on_port(host, port)


def _send_daemon_shutdown(host, port):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect((host, port))
        message = json.dumps({"command": "shutdown", "request_id": "lifecycle"})
        s.sendall(message.encode("utf-8"))
        s.recv(1024)
        s.close()
        return True
    except Exception:
        return False


def _check_daemon_status(host, port):
    status_data = _query_daemon_status(host, port)
    if status_data:
        return status_data.get("startup_stage") == "ready"
    return False


def _wait_for_daemon_ready(pid: int, host: str, port: int, timeout: float = 15.0) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        if not is_process_alive(pid):
            return False
        if _check_port_in_use(host, port) and _check_daemon_status(host, port):
            return True
        time.sleep(0.3)
    return is_process_alive(pid) and _check_port_in_use(host, port)


def print_provider_warnings():
    """Relay the daemon's startup provider warnings to the console.

    For callers that start the daemon with wait_ready=False (the `sm enable`
    Live-scene path), which bypasses the print inside start_daemon. Safe to call
    once the daemon has reached ready — the check runs before the ready stage.
    """
    config = get_default_config()
    _print_provider_warnings(config["daemon"]["host"], config["daemon"]["port"])


def _print_provider_warnings(host, port):
    """Print any non-fatal provider warnings the daemon raised at startup.

    The daemon runs with its stdout discarded, so the warning is relayed to the
    user here (the stage that sets it runs before `ready`, so status already
    carries it by the time we land here).
    """
    status_data = _query_daemon_status(host, port)
    for warning in (status_data or {}).get("provider_warnings", []) or []:
        message = warning.get("message") if isinstance(warning, dict) else str(warning)
        if message:
            # Plain ASCII marker: this prints to the user's console, which may be
            # cp1252 (classic Windows), where a unicode glyph would raise.
            print(f"WARNING: {message}")


def start_daemon(*, wait_ready: bool = True):
    """Spawn the ShellMate daemon.

    Args:
        wait_ready: If True (default), block until startup_stage == ready.
            If False, return as soon as the process is spawned so the caller
            (startup UI) can animate live stage progress.
    """
    config = get_default_config()
    host = config["daemon"]["host"]
    port = config["daemon"]["port"]

    cleanup_stale_sessions()

    session = read_session()
    if session and is_process_alive(session.get("pid", 0)):
        if validate_session_ownership(session):
            print("ShellMate daemon is already running.")
            return False
        else:
            print("Stale session from different user, cleaning up.")
            remove_session()

    if _check_port_in_use(host, port):
        status_data = _query_daemon_status(host, port)
        if _is_shellmate_status(status_data):
            daemon_pid = _resolve_daemon_pid(host, port, status_data)
            if daemon_pid:
                cwd = os.getcwd()
                ipc_address = f"{host}:{port}"
                create_session(daemon_pid, cwd, ipc_address)
                print(f"ShellMate daemon already running (PID: {daemon_pid})")
                return True
        print(f"Port {port} is already in use. Is another ShellMate daemon running?")
        print("Run 'sm disable' first or kill the process holding the port.")
        return False

    session_dir = get_session_dir_path()
    session_dir.mkdir(parents=True, exist_ok=True)

    ipc_address = f"{host}:{port}"

    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        process = subprocess.Popen(
            [sys.executable, "-c", "from shellmate.daemon.server import run_daemon; run_daemon()"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            startupinfo=startupinfo,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    else:
        process = subprocess.Popen(
            [sys.executable, "-c", "from shellmate.daemon.server import run_daemon; run_daemon()"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    cwd = os.getcwd()
    create_session(process.pid, cwd, ipc_address)

    if not wait_ready:
        # UI owns the wait + stage animation
        print(f"ShellMate daemon starting (PID: {process.pid})")
        return True

    ready = _wait_for_daemon_ready(process.pid, host, port, timeout=15.0)

    if ready:
        print(f"ShellMate daemon started (PID: {process.pid})")
        _print_provider_warnings(host, port)
    else:
        print(f"ShellMate daemon process started (PID: {process.pid}) but not yet ready.")
        print("Run 'sm status' to check the daemon state.")

    return True


def stop_daemon():
    config = get_default_config()
    host = config["daemon"]["host"]
    port = config["daemon"]["port"]

    session = read_session()
    pid = session.get("pid") if session else None

    if not pid and _check_port_in_use(host, port):
        status_data = _query_daemon_status(host, port)
        if _is_shellmate_status(status_data):
            pid = _resolve_daemon_pid(host, port, status_data)

    if not pid:
        print("ShellMate daemon is not running.")
        return

    try:
        if _check_port_in_use(host, port):
            _send_daemon_shutdown(host, port)

        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=5)
        else:
            try:
                os.kill(pid, signal.SIGTERM)
                try:
                    os.waitpid(pid, 0)
                except ChildProcessError:
                    pass
            except (ProcessLookupError, PermissionError):
                pass

            for _ in range(10):
                if not is_process_alive(pid):
                    break
                time.sleep(0.2)
            if is_process_alive(pid):
                try:
                    os.kill(pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
    except Exception as e:
        print(f"Warning: {e}")

    remove_session()
    print("ShellMate daemon stopped.")


def check_daemon_status():
    session = read_session()
    if session and is_process_alive(session.get("pid", 0)):
        result = {
            "status": "running",
            "pid": session.get("pid"),
            "cwd": session.get("cwd"),
            "created": session.get("created"),
            "ipc_address": session.get("ipc_address"),
            "owner": session.get("owner"),
        }
        # Merge live daemon state so `sm status` can distinguish a warming
        # agent (normal, degraded-at-first) from a crashed one (bug) and can
        # surface provider warnings on every invocation, not just at enable.
        try:
            config = get_default_config()
            live = _query_daemon_status(config["daemon"]["host"], config["daemon"]["port"])
        except Exception:
            live = None
        if live:
            result["startup_stage"] = live.get("startup_stage")
            result["uptime_seconds"] = live.get("uptime_seconds")
            result["last_health_check"] = live.get("last_health_check")
            result["agents"] = live.get("agents")
            result["provider_warnings"] = live.get("provider_warnings", []) or []
        return result
    return {
        "status": "stopped",
        "pid": None,
    }


def tail_logs():
    from shellmate.config.defaults import get_default_config
    config = get_default_config()
    log_dir = config["logging"]["directory"]
    log_file = os.path.join(log_dir, "daemon.log")
    if not os.path.exists(log_file):
        print("No logs found.")
        return
    try:
        with open(log_file, "r") as f:
            lines = f.readlines()
            for line in lines[-50:]:
                print(line.rstrip())
    except OSError as e:
        print(f"Error reading logs: {e}")
