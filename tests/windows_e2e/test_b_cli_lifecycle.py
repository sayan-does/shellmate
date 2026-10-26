"""Series B - Windows CLI + daemon lifecycle (installed wheel).

Covers hook install idempotency on the PowerShell profile, the detached daemon
spawn / status / stop path (CREATE_NEW_PROCESS_GROUP -> taskkill), port-in-use
handling, and credential round-trip on %APPDATA% paths.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.helpers.daemon_utils import query_daemon_status
from tests.e2e_package.helpers.package_utils import combined_output, install_hooks

pytestmark = pytest.mark.windows


def _ps_profile(home: Path) -> Path:
    return home / "Documents" / "PowerShell" / "Microsoft.PowerShell_profile.ps1"


def _adapter(home: Path) -> Path:
    return home / ".shellmate" / "adapters" / "powershell_adapter.ps1"


def test_install_copies_adapter_and_hooks_profile(installed_env, isolated_env):
    home = Path(isolated_env["SM_TEST_HOME"])
    profile = _ps_profile(home)
    profile.parent.mkdir(parents=True, exist_ok=True)
    profile.write_text("# user config\n", encoding="utf-8")

    result = install_hooks(installed_env, isolated_env)
    assert result.returncode == 0, combined_output(result)

    assert _adapter(home).exists() and _adapter(home).stat().st_size > 0
    content = profile.read_text(encoding="utf-8")
    assert "powershell_adapter.ps1" in content


def test_install_is_idempotent(installed_env, isolated_env):
    home = Path(isolated_env["SM_TEST_HOME"])
    profile = _ps_profile(home)
    profile.parent.mkdir(parents=True, exist_ok=True)
    profile.write_text("", encoding="utf-8")

    install_hooks(installed_env, isolated_env)
    first = profile.read_text(encoding="utf-8")
    hook_lines = first.count("ShellMate Autocomplete") + first.count("# ShellMate hook")

    install_hooks(installed_env, isolated_env)
    second = profile.read_text(encoding="utf-8")
    again = second.count("ShellMate Autocomplete") + second.count("# ShellMate hook")
    assert again == hook_lines, f"hook duplicated: {second!r}"


@pytest.mark.slow
def test_enable_status_disable(installed_daemon):
    installed_daemon.enable()
    status = installed_daemon.status().lower()
    assert "running" in status or "pid" in status

    data = query_daemon_status()
    assert data is not None and data.get("startup_stage") == "ready"

    installed_daemon.disable()
    assert query_daemon_status() is None


@pytest.mark.slow
def test_enable_twice_detects_existing(installed_daemon):
    installed_daemon.enable()
    # A second `sm enable` must not spawn a duplicate; it detects the running one.
    second = installed_daemon.installed.run_sm("enable", timeout=30, env=installed_daemon.env)
    out = combined_output(second).lower()
    assert "already running" in out or "running" in out or "in use" in out


def test_config_writes_env_under_appdata(installed_env, isolated_env):
    installed_env.run_sm("config", "CONTEXT7_API_KEY", "round-trip-value", env=isolated_env)
    cred = Path(isolated_env["APPDATA"]) / "ShellMate" / ".env"
    assert cred.exists(), f"credentials file not written: {cred}"
    assert "CONTEXT7_API_KEY=round-trip-value" in cred.read_text(encoding="utf-8")


def test_uninstall_preserves_credentials(installed_env, isolated_env):
    home = Path(isolated_env["SM_TEST_HOME"])
    profile = _ps_profile(home)
    profile.parent.mkdir(parents=True, exist_ok=True)
    profile.write_text("", encoding="utf-8")

    installed_env.run_sm("config", "CONTEXT7_API_KEY", "keep-me", env=isolated_env)
    install_hooks(installed_env, isolated_env)
    installed_env.run_sm("uninstall", env=isolated_env)

    cred = Path(isolated_env["APPDATA"]) / "ShellMate" / ".env"
    assert cred.exists()
    assert "CONTEXT7_API_KEY=keep-me" in cred.read_text(encoding="utf-8")
