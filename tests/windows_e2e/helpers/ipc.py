"""Invoke the Windows adapter's Python backends through the *installed* venv.

These mirror exactly what powershell_adapter.ps1 shells out to:
  - instant tier  -> PSReadLineSyncClient.instant_check_sync (local, no daemon)
  - pipeline tier -> PSReadLineSyncClient.send_command_partial_sync -> /analyze-partial
  - completions   -> PSReadLineSyncClient.complete_sync / ps_client --complete
Running them via `installed_env.run_python` proves the packaged wheel works, not the dev tree.
"""

from __future__ import annotations

import json
import socket
from typing import Optional


def daemon_command(payload: dict, *, host: str = "127.0.0.1", port: int = 9823, timeout: float = 5.0) -> Optional[dict]:
    """Send a raw newline-JSON command to the daemon over TCP; return parsed dict."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((host, port))
        s.sendall(json.dumps(payload).encode("utf-8"))
        data = s.recv(1024 * 1024)
        s.close()
        return json.loads(data.decode("utf-8"))
    except Exception:
        return None


def _run_json(installed_env, code: str, *, env: Optional[dict], timeout: float) -> dict:
    result = installed_env.run_python(code, env=env, timeout=timeout)
    if result.returncode != 0:
        raise AssertionError(
            f"backend call failed: rc={result.returncode} "
            f"stderr={result.stderr!r} stdout={result.stdout!r}"
        )
    out = (result.stdout or "").strip()
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"non-JSON backend output: {out!r}") from exc


def instant_check(installed_env, command: str, *, env: Optional[dict] = None, timeout: float = 30) -> dict:
    code = (
        "import json\n"
        "from shellmate.ipc.ps_client import PSReadLineSyncClient\n"
        f"print(json.dumps(PSReadLineSyncClient().instant_check_sync({command!r})))"
    )
    return _run_json(installed_env, code, env=env, timeout=timeout)


def analyze_partial(installed_env, command: str, *, env: Optional[dict] = None, timeout: float = 45) -> dict:
    code = (
        "import json\n"
        "from shellmate.ipc.ps_client import PSReadLineSyncClient\n"
        f"print(json.dumps(PSReadLineSyncClient().send_command_partial_sync({command!r}, timeout=30.0)))"
    )
    return _run_json(installed_env, code, env=env, timeout=timeout)


def complete(installed_env, command: str, *, env: Optional[dict] = None, timeout: float = 30) -> dict:
    code = (
        "import json\n"
        "from shellmate.ipc.ps_client import PSReadLineSyncClient\n"
        f"print(json.dumps(PSReadLineSyncClient().complete_sync({command!r})))"
    )
    return _run_json(installed_env, code, env=env, timeout=timeout)
