import os
import json
import time
import platform
import tempfile
from pathlib import Path
from shellmate.config.paths import get_session_dir
from shellmate.cli.version import VERSION


def _session_file() -> Path:
    """Resolve session.json path at call time (honors LOCALAPPDATA/XDG overrides)."""
    return get_session_dir() / "session.json"


# Kept for callers that import SESSION_FILE; prefer _session_file() for correctness.
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
        "version": VERSION,
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
    session_file = _session_file()
    temp_file = session_file.with_suffix(".tmp")
    try:
        with open(temp_file, "w") as f:
            json.dump(session, f)
        if platform.system() != "Windows":
            os.chmod(temp_file, 0o600)
        temp_file.replace(session_file)
    except Exception:
        if temp_file.exists():
            temp_file.unlink(missing_ok=True)
        raise


def read_session() -> dict:
    session_file = _session_file()
    if not session_file.exists():
        return None
    try:
        with open(session_file, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def remove_session() -> bool:
    """Remove session directory and all v3 files."""
    try:
        session_dir = get_session_dir()
        if session_dir.exists():
            for file in session_dir.glob("*"):
                file.unlink(missing_ok=True)
            session_dir.rmdir()
        return True
    except OSError:
        return False


def get_command_history_file() -> Path:
    """Get path to command history JSONL file."""
    session_dir = get_session_dir()
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir / "command_history.jsonl"


def get_environment_cache_file() -> Path:
    """Get path to environment detection cache."""
    session_dir = get_session_dir()
    session_dir.mkdir(parents=True, exist_ok=True)
    cache_file = session_dir / "environment_cache.json"
    if platform.system() != "Windows":
        try:
            if cache_file.exists():
                cache_file.chmod(0o600)
        except OSError:
            pass
    return cache_file


def get_query_cache_file() -> Path:
    """Get path to query response cache."""
    session_dir = get_session_dir()
    session_dir.mkdir(parents=True, exist_ok=True)
    cache_file = session_dir / "query_cache.json"
    if platform.system() != "Windows":
        try:
            if cache_file.exists():
                cache_file.chmod(0o600)
        except OSError:
            pass
    return cache_file


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