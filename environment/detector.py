import os
import platform
import re

SHELL_MAPPING = {
    "bash": "bash",
    "zsh": "zsh",
    "fish": "fish",
    "powershell": "powershell",
    "pwsh": "powershell",
    "cmd": "cmd",
    "nu": "nushell",
}


def detect_os():
    system = platform.system().lower()
    if system == "linux":
        return "linux"
    elif system == "windows":
        return "windows"
    elif system == "darwin":
        return "macos"
    return system


def detect_shell():
    shell_env = os.environ.get("SHELL", "")
    if shell_env:
        shell_name = os.path.basename(shell_env).lower()
        for key, value in SHELL_MAPPING.items():
            if key in shell_name:
                return value

    if platform.system() == "Windows":
        comspec = os.environ.get("COMSPEC", "")
        if "cmd" in comspec.lower():
            return "cmd"
        ps_module_path = os.environ.get("PSModulePath", "")
        if ps_module_path:
            return "powershell"

    try:
        import psutil
        parent_pid = os.getppid()
        parent_proc = psutil.Process(parent_pid)
        parent_name = parent_proc.name().lower()
        for key, value in SHELL_MAPPING.items():
            if key in parent_name:
                return value
    except ImportError:
        pass

    return "unknown"


def detect_environment_type():
    if platform.system() == "Windows":
        wsl_distro = os.environ.get("WSL_DISTRO_NAME")
        if wsl_distro:
            return "wsl"
        return "native"

    if not platform.system() == "Linux":
        return "native"

    if os.environ.get("WSL_DISTRO_NAME"):
        return "wsl"

    try:
        with open("/proc/version", "r") as f:
            version = f.read().lower()
            if "microsoft" in version or "wsl" in version:
                return "wsl"
    except (FileNotFoundError, PermissionError):
        pass

    container_markers = [
        "/.dockerenv",
        "/run/.containerenv",
    ]
    for marker in container_markers:
        if os.path.exists(marker):
            return "container"

    try:
        with open("/proc/1/cgroup", "r") as f:
            content = f.read()
            if re.search(r"docker|kubepods|garden", content, re.IGNORECASE):
                return "container"
    except (FileNotFoundError, PermissionError):
        pass

    ssh_vars = ["SSH_CLIENT", "SSH_TTY", "SSH_CONNECTION"]
    for var in ssh_vars:
        if os.environ.get(var):
            return "ssh"

    return "native"


def detect_terminal():
    term_program = os.environ.get("TERM_PROGRAM", "")
    if term_program:
        return term_program

    term = os.environ.get("TERM", "")
    if term and term != "dumb":
        return term

    wt_session = os.environ.get("WT_SESSION", "")
    if wt_session:
        return "Windows Terminal"

    return "unknown"


def detect_environment():
    return {
        "os": detect_os(),
        "shell": detect_shell(),
        "environment": detect_environment_type(),
        "terminal": detect_terminal(),
    }
