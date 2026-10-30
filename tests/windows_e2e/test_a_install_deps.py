"""Series A - Windows install & dependency integrity (installed wheel).

Proves the `shellmate-cli` wheel installs on Windows, exposes both console
scripts, imports every runtime dependency, and ships the PowerShell adapters +
rule data as package-data.
"""

from __future__ import annotations

import pytest

from tests.e2e_package.helpers.package_utils import combined_output

pytestmark = pytest.mark.windows

# Runtime deps from pyproject [project.dependencies]; import names where they differ.
_RUNTIME_IMPORTS = [
    "click",
    "yaml",          # pyyaml
    "aiohttp",
    "groq",
    "openai",
    "langgraph",
    "langchain_core",
    "rich",
    "psutil",
    "watchdog",
]


def test_entry_points_resolve(installed_env, isolated_env):
    for exe in (installed_env.sm, installed_env.shellmate):
        assert exe.exists(), f"missing entry point: {exe}"
    out = combined_output(installed_env.run_sm("--version", env=isolated_env))
    assert "3" in out  # version string present (3.x)


def test_all_runtime_deps_import(installed_env, isolated_env):
    code = (
        "import importlib, sys\n"
        f"mods = {_RUNTIME_IMPORTS!r}\n"
        "bad = []\n"
        "for m in mods:\n"
        "    try:\n"
        "        importlib.import_module(m)\n"
        "    except Exception as e:\n"
        "        bad.append(f'{m}: {e}')\n"
        "print('OK' if not bad else 'FAIL ' + '; '.join(bad))\n"
    )
    result = installed_env.run_python(code, env=isolated_env)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OK", result.stdout


def test_bundled_adapters_and_rules_present(installed_env, isolated_env):
    """Package-data from pyproject must land inside the installed wheel."""
    code = (
        "from importlib.resources import files\n"
        "root = files('shellmate')\n"
        "need = ['adapters/powershell_adapter.ps1', 'adapters/powershell_predictor.ps1']\n"
        "missing = [p for p in need if not root.joinpath(p).is_file()]\n"
        "rules_dir = root.joinpath('rules')\n"
        "has_rules = rules_dir.is_dir() and any(str(p).endswith('.yaml') for p in rules_dir.iterdir())\n"
        "print('OK' if not missing and has_rules else f'MISS {missing} rules={has_rules}')\n"
    )
    result = installed_env.run_python(code, env=isolated_env)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OK", result.stdout


def test_catastrophic_matcher_importable_from_wheel(installed_env, isolated_env):
    code = (
        "import json\n"
        "from shellmate.rules.catastrophic_matcher import match_catastrophic\n"
        "print(json.dumps(match_catastrophic('rm -rf /')))"
    )
    result = installed_env.run_python(code, env=isolated_env)
    assert result.returncode == 0, result.stderr
    assert '"matched": true' in result.stdout.lower().replace(" ", " ")


def test_install_dry_run_reports_powershell(installed_env, isolated_env):
    result = installed_env.run_sm("install", "--dry-run", env=isolated_env)
    assert result.returncode == 0, combined_output(result)
    out = combined_output(result).lower()
    assert "powershell" in out
    assert "powershell_adapter.ps1" in out or "adapter" in out
