"""Series G - PSReadLine predictor subsystem (pwsh 7.2+).

On PowerShell 7.2+ the adapter dot-sources powershell_predictor.ps1, which
registers a `ShellMatePredictor` ICommandPredictor and flips PSReadLine to
plugin prediction. These tests confirm real subsystem registration and that the
predictor's data source (`ps_client --complete`) returns suggestions from pwsh.

Deterministic (no pseudo-console) - the reliable floor for the completion surface.
Skips unless pwsh 7.2+ is on PATH.
"""

from __future__ import annotations

import subprocess

import pytest

from tests.windows_e2e.conftest import pwsh_path

pytestmark = [
    pytest.mark.windows,
    pytest.mark.pwsh,
    # Collection-time guard: skip before the session wheel build when pwsh absent.
    pytest.mark.skipif(not pwsh_path(), reason="PowerShell 7.2+ (pwsh) not found on PATH"),
]


def _run_pwsh(script: str, env: dict, timeout: float = 45) -> subprocess.CompletedProcess:
    return subprocess.run(
        [pwsh_path(), "-NoProfile", "-NoLogo", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
    )


def test_predictor_registers_as_subsystem(adapter_path, pwsh_env):
    # PSReadLine must be loaded before sourcing so the adapter's $canPredict gate
    # opens and the predictor registers. The $ShellMatePredictorRegistered flag is
    # unreliable non-interactively (Set-PSReadLineOption no-ops), so assert on the
    # real subsystem registry instead.
    script = f"""
Import-Module PSReadLine
. '{adapter_path}'
$kind = [System.Management.Automation.Subsystem.SubsystemKind]::CommandPredictor
$info = [System.Management.Automation.Subsystem.SubsystemManager]::GetSubsystemInfo($kind)
if ($info.Implementations.Name -contains 'ShellMate') {{ Write-Output 'SUBSYSTEM_OK' }}
else {{ Write-Output ('NAMES=' + ($info.Implementations.Name -join ',')) }}
"""
    result = _run_pwsh(script, pwsh_env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "SUBSYSTEM_OK" in result.stdout, result.stdout + result.stderr


def test_predictor_file_defines_icommandpredictor(predictor_path, pwsh_env):
    script = f"""
$errors = $null; $tokens = $null
[System.Management.Automation.Language.Parser]::ParseFile(
  '{predictor_path}', [ref]$tokens, [ref]$errors) | Out-Null
if ($errors) {{ $errors | ForEach-Object {{ $_.ToString() }}; exit 1 }}
$text = Get-Content -Raw '{predictor_path}'
if ($text -match 'ICommandPredictor' -and $text -match '--complete') {{ Write-Output 'PREDICTOR_OK' }}
"""
    result = _run_pwsh(script, pwsh_env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PREDICTOR_OK" in result.stdout


def test_predictor_data_source_returns_push(adapter_path, pwsh_env):
    """The predictor calls `python ps_client.py --complete <input>`; from pwsh
    that must yield a completion containing 'push' for 'git pu'."""
    script = f"""
. '{adapter_path}'
$comps = Invoke-ShellMateComplete -Prefix 'git pu'
$comps -join "`n"
"""
    result = _run_pwsh(script, pwsh_env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "push" in result.stdout.lower(), result.stdout + result.stderr
