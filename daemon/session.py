import os
import json
import time
import platform
import tempfile
from pathlib import Path
from config.paths import get_session_dir


SESSION_FILE = get_session_dir() / "session.json"


def get_session_dir_path() -> Path:
    return get_session_dir()


def create_session(pid: int, cwd: str, ipc_address: str) -> dict:
    session_dir = get_session_dir()
    session_dir.mkdir(parents=True, exist_ok=True)

    if platform.system() != "Windows":
        try:
            session_dir.chmod(0o700)
        except OSError:
            pass

    session = {
        "pid": pid,
        "cwd": cwd,
        "created": time.time(),
        "owner": get_owner_identity(),
        "ipc_address": ipc_address,
        "version": "2.0.0",
    }

    write_session_atomic(session)
    return session


def get_owner_identity() -> str:
    if platform.system() == "Windows":
        return os.environ.get("USERNAME", "unknown")
    else:
        import pwd
        return pwd.getpwuid(os.getuid()).pw_name


def write_session_atomic(session: dict) -> None:
    temp_file = SESSION_FILE.with_suffix(".tmp")
    try:
        with open(temp_file, "w") as f:
            json.dump(session, f)
        if platform.system() != "Windows":
            os.chmod(temp_file, 0o600)
        temp_file.replace(SESSION_FILE)
    except Exception:
        if temp_file.exists():
            temp_file.unlink(missing_ok=True)
        raise


def read_session() -> dict:
    if not SESSION_FILE.exists():
        return None
    try:
        with open(SESSION_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def remove_session() -> bool:
    try:
        if SESSION_FILE.exists():
            SESSION_FILE.unlink()
        return True
    except OSError:
        return False


def is_session_stale(session: dict) -> bool:
    if not session:
        return True
    pid = session.get("pid")
    if not pid:
        return True
    return not is_process_alive(pid)


def is_process_alive(pid: int) -> bool:
    if platform.system() == "Windows":
        try:
            import subprocess
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


def cleanup_stale_sessions() -> int:
    session = read_session()
    if session and is_session_stale(session):
        remove_session()
        return 1
    return 0


def validate_session_ownership(session: dict) -> bool:
    if not session:
        return False
    current_owner = get_owner_identity()
    session_owner = session.get("owner")
    return current_owner == session_owner