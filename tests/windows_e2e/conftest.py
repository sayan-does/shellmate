"""Fixtures for the Windows pip-package test series.

Self-contained (does not depend on tests/e2e_package/conftest.py being importable):
it reuses the wheel/venv/daemon *helpers* from package_utils and defines its own
fixtures, adding live-key forwarding and pwsh/ConPTY availability guards.

Target host: Windows 11 native, PowerShell 7.2+ (pwsh). Series F/G skip when pwsh
or the ConPTY toolchain is absent; Series A-D run on any Windows Python.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

from tests.e2e.helpers.daemon_utils import kill_stale_daemons
from tests.e2e_package.helpers.package_utils import (
    PackageDaemonController,
    build_wheel,
    create_installed_env,
    home_env,
    seed_enable_prerequisites,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

# API keys that enable the live AI tier. Values read from the real environment
# (the user sets them with `$env:GROQ_API_KEY = "..."` before running).
LIVE_KEY_NAMES = ("GROQ_API_KEY", "OPENROUTER_API_KEY", "XAI_API_KEY")


# --------------------------------------------------------------------------- #
# markers + platform / capability skips
# --------------------------------------------------------------------------- #
def pytest_configure(config):
    config.addinivalue_line("markers", "windows: Windows-only tests")
    config.addinivalue_line("markers", "requires_api: needs a real AI API key")
    config.addinivalue_line("markers", "slow: >10s runtime")
    config.addinivalue_line("markers", "conpty: drives pwsh through a pseudo-console (flaky, opt-in)")
    config.addinivalue_line("markers", "pwsh: requires PowerShell 7.2+ (pwsh) on PATH")


def pytest_runtest_setup(item):
    if item.get_closest_marker("windows") and sys.platform != "win32":
        pytest.skip("Windows-only test")
    if item.get_closest_marker("pwsh") and not pwsh_path():
        pytest.skip("PowerShell 7.2+ (pwsh) not found on PATH")
    if item.get_closest_marker("conpty") and not conpty_available():
        pytest.skip("ConPTY toolchain unavailable (needs pwsh + pywinpty + pyte)")


# --------------------------------------------------------------------------- #
# capability helpers (also importable by tests)
# --------------------------------------------------------------------------- #
def pwsh_path() -> str | None:
    """Path to PowerShell 7+ (`pwsh`), or None. Windows PowerShell 5.1 does not count."""
    return shutil.which("pwsh")


def conpty_available() -> bool:
    if not pwsh_path():
        return False
    try:
        import pyte  # noqa: F401
        import winpty  # noqa: F401  (pywinpty)
    except Exception:
        return False
    return True


# --------------------------------------------------------------------------- #
# installed-wheel + isolation fixtures (mirror e2e_package, self-contained)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session", autouse=True)
def _win_e2e_session_cleanup():
    kill_stale_daemons()
    yield
    kill_stale_daemons()


@pytest.fixture(scope="session")
def installed_env(tmp_path_factory):
    """Build the wheel once and install it into a session-scoped venv."""
    base = tmp_path_factory.mktemp("shellmate_win_e2e")
    wheel = build_wheel(REPO_ROOT)
    return create_installed_env(base, wheel_path=wheel)


@pytest.fixture(scope="function")
def isolated_session(tmp_path):
    """Point AppData/XDG dirs at a throwaway location for this test."""
    saved = {}
    overrides = {
        "LOCALAPPDATA": str(tmp_path / "local"),
        "APPDATA": str(tmp_path / "roaming"),
        "XDG_STATE_HOME": str(tmp_path / "state"),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
    }
    for key, value in overrides.items():
        saved[key] = os.environ.get(key)
        os.environ[key] = value
        Path(value).mkdir(parents=True, exist_ok=True)
    yield tmp_path
    for key, old in saved.items():
        if old is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = old


@pytest.fixture(scope="function")
def isolated_env(isolated_session, tmp_path):
    """Env dict for subprocess calls with isolated AppData/HOME. No live keys."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {
        "LOCALAPPDATA": os.environ.get("LOCALAPPDATA", ""),
        "APPDATA": os.environ.get("APPDATA", ""),
        "XDG_STATE_HOME": os.environ.get("XDG_STATE_HOME", ""),
        "XDG_CONFIG_HOME": os.environ.get("XDG_CONFIG_HOME", ""),
        "XDG_CACHE_HOME": os.environ.get("XDG_CACHE_HOME", ""),
        "SM_NONINTERACTIVE": "1",
    }
    env.update(home_env(home))
    env["SM_TEST_HOME"] = str(home)
    return env


@pytest.fixture(scope="function")
def installed_daemon(installed_env, isolated_session, isolated_env):
    """Daemon controller backed by the installed `sm` binary (offline env)."""
    seed_enable_prerequisites(Path(isolated_env["SM_TEST_HOME"]))
    controller = PackageDaemonController(installed_env, isolated_session, env=isolated_env)
    try:
        yield controller
    finally:
        try:
            controller.disable()
        except Exception:
            pass
        kill_stale_daemons()


# --------------------------------------------------------------------------- #
# live-AI fixtures
# --------------------------------------------------------------------------- #
def _present_live_keys() -> dict:
    return {k: os.environ[k] for k in LIVE_KEY_NAMES if os.environ.get(k)}


@pytest.fixture(scope="session")
def live_keys():
    """Per-provider live keys from the environment. Skip if none present.

    Unlike the stricter e2e_package `api_keys` fixture (which needs Groq AND
    OpenRouter), this skips only when NO provider key is available, so a single
    Groq key is enough to exercise the risk-analysis path.
    """
    keys = _present_live_keys()
    if not keys:
        pytest.skip(
            "No AI key set. Export at least GROQ_API_KEY "
            "(optionally OPENROUTER_API_KEY / XAI_API_KEY) to run the live tier."
        )
    return keys


@pytest.fixture(scope="function")
def live_env(isolated_env, live_keys):
    """Isolated env with the user's real AI keys forwarded in.

    If GROQ_MODEL is set, also drop a config.yaml pointing the risk analyzer at
    that model (the shipped default llama id 404s for some Groq accounts, and
    the daemon reads the model from config, not the GROQ_MODEL env var).
    """
    env = dict(isolated_env)
    env.update(live_keys)
    model = os.environ.get("GROQ_MODEL")
    if model and env.get("APPDATA"):
        import yaml

        cfg_dir = Path(env["APPDATA"]) / "ShellMate"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        (cfg_dir / "config.yaml").write_text(
            yaml.safe_dump({"providers": {"risk_analysis": {"primary": "groq", "model": model}}}),
            encoding="utf-8",
        )
        env["GROQ_MODEL"] = model
    return env


@pytest.fixture(scope="function")
def pwsh_env(installed_env, isolated_env):
    """Env for a pwsh session where `python` resolves to the venv interpreter
    that has shellmate installed, with isolated config/state dirs."""
    env = dict(os.environ)
    env["PATH"] = str(installed_env.python.parent) + os.pathsep + env.get("PATH", "")
    for k in ("APPDATA", "LOCALAPPDATA", "USERPROFILE", "HOME"):
        if isolated_env.get(k):
            env[k] = isolated_env[k]
    return env


def _installed_resource(installed_env, isolated_env, rel: str) -> str:
    code = (
        "from importlib.resources import files\n"
        f"print(files('shellmate').joinpath({rel!r}))"
    )
    result = installed_env.run_python(code, env=isolated_env)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


@pytest.fixture(scope="function")
def adapter_path(installed_env, isolated_env) -> str:
    return _installed_resource(installed_env, isolated_env, "adapters/powershell_adapter.ps1")


@pytest.fixture(scope="function")
def predictor_path(installed_env, isolated_env) -> str:
    return _installed_resource(installed_env, isolated_env, "adapters/powershell_predictor.ps1")


@pytest.fixture(scope="function")
def live_daemon(installed_env, isolated_session, live_env):
    """Daemon started with live AI keys forwarded into its environment."""
    seed_enable_prerequisites(Path(live_env["SM_TEST_HOME"]))
    controller = PackageDaemonController(installed_env, isolated_session, env=live_env)
    try:
        yield controller
    finally:
        try:
            controller.disable()
        except Exception:
            pass
        kill_stale_daemons()
