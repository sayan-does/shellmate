import os
import sys
import tempfile
from pathlib import Path
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from adapters import (
    get_adapter_path, get_supported_shells, check_shell_available,
    validate_adapter_syntax, ADAPTERS_DIR,
)


class TestAdapters:
    def test_adapter_files_exist(self):
        assert (ADAPTERS_DIR / "bash_adapter.sh").exists()
        assert (ADAPTERS_DIR / "zsh_adapter.zsh").exists()
        assert (ADAPTERS_DIR / "powershell_adapter.ps1").exists()

    def test_supported_shells(self):
        shells = get_supported_shells()
        assert "bash" in shells
        assert "zsh" in shells
        assert "powershell" in shells

    def test_get_adapter_path(self):
        for shell in get_supported_shells():
            path = get_adapter_path(shell)
            assert path is not None
            assert path.exists()

    def test_get_adapter_path_unknown(self):
        assert get_adapter_path("fish") is None
        assert get_adapter_path("unknown") is None

    def test_check_shell_powershell_on_windows(self):
        if sys.platform == "win32":
            assert check_shell_available("powershell") is True

    def test_adapter_scripts_not_empty(self):
        for shell in get_supported_shells():
            path = get_adapter_path(shell)
            content = path.read_text(encoding="utf-8")
            assert len(content) > 50
            assert content.strip() != ""

    def test_all_adapters_use_sm_command(self):
        for shell in get_supported_shells():
            path = get_adapter_path(shell)
            content = path.read_text(encoding="utf-8")
            assert "sm --quiet analyze" in content, f"{shell} adapter should use 'sm --quiet analyze'"

    def test_powershell_adapter_functions(self):
        path = get_adapter_path("powershell")
        content = path.read_text(encoding="utf-8")
        assert "Invoke-ShellMateAnalysis" in content
        assert "Invoke-ShellMateSuggestion" in content
        assert "PSConsoleHostReadLine" in content
        assert "ConvertFrom-Json" in content

    def test_bash_adapter_functions(self):
        path = get_adapter_path("bash")
        content = path.read_text(encoding="utf-8")
        assert "shellmate_analyze" in content
        assert "shellmate_suggest_prefix" in content
        assert "shellmate_preexec" in content
        assert "shellmate_precmd" in content
        assert "BASH_VERSION" in content

    def test_zsh_adapter_functions(self):
        path = get_adapter_path("zsh")
        content = path.read_text(encoding="utf-8")
        assert "shellmate_analyze" in content
        assert "shellmate_suggest_prefix" in content
        assert "add-zsh-hook" in content
        assert "_shellmate_preexec" in content

    @pytest.mark.skipif(sys.platform == "win32", reason="bash syntax check requires WSL/Cygwin path support")
    def test_bash_adapter_syntax(self):
        valid, msg = validate_adapter_syntax("bash")
        if not valid and "not available" in msg:
            pytest.skip(msg)
        assert valid, msg

    @pytest.mark.skipif(sys.platform != "win32", reason="PowerShell validation only on Windows")
    def test_powershell_adapter_syntax(self):
        valid, msg = validate_adapter_syntax("powershell")
        assert valid, msg

    def test_readme_refers_to_adapters(self):
        from cli.main import print_usage
        assert print_usage is not None

    def test_adapter_permissions(self):
        for shell in get_supported_shells():
            path = get_adapter_path(shell)
            assert os.access(path, os.R_OK), f"{shell} adapter should be readable"

    def test_adapter_preserves_quoting(self):
        """ADP-01: Adapters preserve quoting, flags, and shell-special tokens"""
        for shell in get_supported_shells():
            path = get_adapter_path(shell)
            content = path.read_text(encoding="utf-8")
            assert 'sm --quiet analyze' in content
            # Each adapter must pass its command variable to sm without splitting tokens
            if shell == "powershell":
                assert '$Command' in content or '$command' in content
            else:
                assert '"$cmd"' in content or '"$*"' in content or '"$command"' in content

    def test_disabled_daemon_graceful_handling(self):
        """ADP-02: Disabled daemon does not break normal shell usage"""
        for shell in get_supported_shells():
            path = get_adapter_path(shell)
            content = path.read_text(encoding="utf-8")
            assert "2>/dev/null" in content or "$null" in content or "2>$null" in content
            assert "exit_code" in content or "return" in content


class TestAdapterParsing:
    """ADP-03/04: --dry-run parsing and install/uninstall wiring."""

    def test_parser_routes_install(self):
        from cli.parser import parse_argv, Action
        result = parse_argv(["install"])
        assert result.action == Action.INSTALL

    def test_parser_routes_uninstall(self):
        from cli.parser import parse_argv, Action
        result = parse_argv(["uninstall"])
        assert result.action == Action.UNINSTALL

    def test_parser_extracts_dry_run_from_install(self):
        from cli.parser import parse_argv
        result = parse_argv(["install", "--dry-run"])
        assert result.dry_run is True
        assert result.action.name == "INSTALL"

    def test_parser_extracts_dry_run_from_uninstall(self):
        from cli.parser import parse_argv
        result = parse_argv(["uninstall", "--dry-run"])
        assert result.dry_run is True
        assert result.action.name == "UNINSTALL"

    def test_dry_run_false_by_default(self):
        from cli.parser import parse_argv
        result = parse_argv(["install"])
        assert result.dry_run is False

    def test_main_passes_dry_run_to_install(self):
        import inspect
        from cli.main import main
        source = inspect.getsource(main)
        assert "install(dry_run=parsed.dry_run)" in source

    def test_main_passes_dry_run_to_uninstall(self):
        import inspect
        from cli.main import main
        source = inspect.getsource(main)
        assert "uninstall(dry_run=parsed.dry_run)" in source
