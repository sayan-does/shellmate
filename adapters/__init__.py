import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

ADAPTERS_DIR = Path(__file__).parent


def get_adapter_path(shell: str) -> Optional[Path]:
    mapping = {
        "bash": ADAPTERS_DIR / "bash_adapter.sh",
        "zsh": ADAPTERS_DIR / "zsh_adapter.zsh",
        "powershell": ADAPTERS_DIR / "powershell_adapter.ps1",
    }
    path = mapping.get(shell)
    return path if path and path.exists() else None


def get_supported_shells() -> list[str]:
    return ["bash", "zsh", "powershell"]


def check_shell_available(shell: str) -> bool:
    if shell == "powershell":
        return sys.platform == "win32"
    return shutil.which(shell) is not None


def validate_adapter_syntax(shell: str) -> tuple[bool, str]:
    path = get_adapter_path(shell)
    if not path:
        return False, f"Adapter not found for {shell}"

    content = path.read_text(encoding="utf-8")

    if shell == "powershell":
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"$errors = $null; [System.Management.Automation.PSParser]::Tokenize((Get-Content -Raw '{path}'), [ref]$null, [ref]$errors); if ($errors) {{ $errors | ForEach-Object {{ $_.Message }} }} else {{ 'OK' }}"],
                capture_output=True, text=True, timeout=15
            )
            output = result.stdout.strip()
            if output == "OK":
                return True, "Syntax OK"
            return False, f"Syntax errors: {output}"
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            return False, f"Cannot validate: {e}"

    if shell in ("bash", "zsh"):
        interpreter = shutil.which(shell)
        if not interpreter:
            return False, f"{shell} not available on this system"

        try:
            result = subprocess.run(
                [interpreter, "-n", str(path)],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0:
                return True, "Syntax OK"
            return False, f"Syntax errors: {result.stderr.strip()}"
        except (subprocess.TimeoutExpired, OSError) as e:
            return False, f"Cannot validate: {e}"

    return False, f"Unsupported shell: {shell}"
