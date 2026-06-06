import os
import sys
from pathlib import Path


def get_config_dir() -> Path:
    """Get platform-specific config directory following XDG/AppData conventions."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / "ShellMate"
        return Path.home() / "AppData" / "Roaming" / "ShellMate"
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        if xdg:
            return Path(xdg) / "shellmate"
        return Path.home() / ".config" / "shellmate"


def get_state_dir() -> Path:
    """Get platform-specific state/data directory following XDG/AppData conventions."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "ShellMate"
        return Path.home() / "AppData" / "Local" / "ShellMate"
    else:
        xdg = os.environ.get("XDG_STATE_HOME")
        if xdg:
            return Path(xdg) / "shellmate"
        return Path.home() / ".local" / "state" / "shellmate"


def get_cache_dir() -> Path:
    """Get platform-specific cache directory following XDG/AppData conventions."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "ShellMate" / "cache"
        return Path.home() / "AppData" / "Local" / "ShellMate" / "cache"
    else:
        xdg = os.environ.get("XDG_CACHE_HOME")
        if xdg:
            return Path(xdg) / "shellmate"
        return Path.home() / ".cache" / "shellmate"


def get_log_dir() -> Path:
    """Get platform-specific log directory."""
    return get_state_dir() / "logs"


def get_session_dir() -> Path:
    """Get platform-specific session directory."""
    return get_state_dir() / "sessions"


def ensure_dirs():
    """Create all necessary directories with appropriate permissions."""
    dirs = [
        get_config_dir(),
        get_state_dir(),
        get_cache_dir(),
        get_log_dir(),
        get_session_dir(),
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        if sys.platform != "win32":
            try:
                d.chmod(0o700)
            except OSError:
                pass


CONFIG_FILE = get_config_dir() / "config.yaml"
CREDENTIALS_FILE = get_config_dir() / ".env"