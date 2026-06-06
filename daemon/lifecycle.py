import os
import signal
import subprocess
import sys
import time
from config.defaults import get_default_config
from daemon.session import (
    create_session, read_session, remove_session,
    cleanup_stale_sessions, validate_session_ownership,
    get_session_dir_path, is_process_alive
)


def start_daemon():
    cleanup_stale_sessions()

    session = read_session()
    if session and is_process_alive(session.get("pid", 0)):
        if validate_session_ownership(session):
            print("ShellMate daemon is already running.")
            return
        else:
            print("Stale session from different user, cleaning up.")
            remove_session()

    session_dir = get_session_dir_path()
    session_dir.mkdir(parents=True, exist_ok=True)

    config = get_default_config()
    host = config["daemon"]["host"]
    port = config["daemon"]["port"]
    ipc_address = f"{host}:{port}"

    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        process = subprocess.Popen(
            [sys.executable, "-c", "from daemon.server import run_daemon; run_daemon()"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            startupinfo=startupinfo,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    else:
        process = subprocess.Popen(
            [sys.executable, "-c", "from daemon.server import run_daemon; run_daemon()"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    cwd = os.getcwd()
    create_session(process.pid, cwd, ipc_address)

    time.sleep(0.5)
    print(f"ShellMate daemon started (PID: {process.pid})")


def stop_daemon():
    session = read_session()
    pid = session.get("pid") if session else None

    if not pid:
        print("ShellMate daemon is not running.")
        return

    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
        else:
            os.kill(pid, signal.SIGTERM)
            try:
                os.waitpid(pid, 0)
            except ChildProcessError:
                pass
    except (ProcessLookupError, PermissionError):
        pass

    remove_session()
    print("ShellMate daemon stopped.")


def check_daemon_status():
    session = read_session()
    if session and is_process_alive(session.get("pid", 0)):
        return {
            "status": "running",
            "pid": session.get("pid"),
            "cwd": session.get("cwd"),
            "created": session.get("created"),
            "ipc_address": session.get("ipc_address"),
            "owner": session.get("owner"),
        }
    return {
        "status": "stopped",
        "pid": None,
    }


def tail_logs():
    from config.defaults import get_default_config
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