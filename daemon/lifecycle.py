import os
import signal
import subprocess
import sys
import time
import json
from config.defaults import get_default_config, SHELLMATE_DIR

PID_FILE = os.path.join(SHELLMATE_DIR, "shellmate.pid")


def start_daemon():
    if os.path.exists(PID_FILE):
        pid = read_pid()
        if pid and is_process_running(pid):
            print("ShellMate daemon is already running.")
            return

    os.makedirs(SHELLMATE_DIR, exist_ok=True)

    daemon_script = os.path.join(os.path.dirname(__file__), "server.py")

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

    with open(PID_FILE, "w") as f:
        f.write(str(process.pid))

    time.sleep(0.5)
    print(f"ShellMate daemon started (PID: {process.pid})")


def stop_daemon():
    pid = read_pid()
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

    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)

    print("ShellMate daemon stopped.")


def check_daemon_status():
    pid = read_pid()
    if pid and is_process_running(pid):
        return {
            "status": "running",
            "pid": pid,
        }
    return {
        "status": "stopped",
        "pid": None,
    }


def read_pid():
    if not os.path.exists(PID_FILE):
        return None
    try:
        with open(PID_FILE) as f:
            return int(f.read().strip())
    except (ValueError, OSError):
        return None


def is_process_running(pid):
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True, text=True, timeout=5
            )
            return str(pid) in result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def tail_logs():
    log_dir = os.path.join(SHELLMATE_DIR, "logs")
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
