import io
import sys
import os
from pathlib import Path
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from cli.version import VERSION
from rich.console import Console


class TestAnalysisUI:
    def test_render_analysis_safe_command(self):
        from ui.analysis import render_analysis
        capture = io.StringIO()
        test_console = Console(file=capture, force_terminal=False)
        import ui.analysis
        orig_console = ui.analysis.console
        ui.analysis.console = test_console
        try:
            render_analysis({
                "risk": "SAFE",
                "confidence": 0.95,
                "message": "This command is safe",
                "explanation": "No dangerous patterns detected",
                "alternatives": [],
                "context_used": {},
                "latency": {},
                "total_ms": 150,
            })
            output = capture.getvalue()
            assert "SAFE" in output
            assert "95%" in output or "95" in output
        finally:
            ui.analysis.console = orig_console

    def test_render_analysis_critical(self):
        from ui.analysis import render_analysis
        capture = io.StringIO()
        test_console = Console(file=capture, force_terminal=False)
        import ui.analysis
        orig_console = ui.analysis.console
        ui.analysis.console = test_console
        try:
            render_analysis({
                "risk": "CRITICAL",
                "confidence": 0.99,
                "message": "This command is extremely dangerous",
                "alternatives": ["Use rm with caution", "Use trash-cli instead"],
            })
            output = capture.getvalue()
            assert "CRITICAL" in output
            assert "extremely dangerous" in output
            assert "trash-cli" in output
        finally:
            ui.analysis.console = orig_console

    def test_render_analysis_with_context(self):
        from ui.analysis import render_analysis
        capture = io.StringIO()
        test_console = Console(file=capture, force_terminal=False)
        import ui.analysis
        orig_console = ui.analysis.console
        ui.analysis.console = test_console
        try:
            render_analysis({
                "risk": "MEDIUM",
                "confidence": 0.7,
                "message": "Check file paths",
                "context_used": {"watcher": True, "librarian": True},
            })
            output = capture.getvalue()
            assert "MEDIUM" in output
            assert "Context:" in output
            assert "watcher" in output
            assert "librarian" in output
        finally:
            ui.analysis.console = orig_console

    def test_render_analysis_truncates_long_message(self):
        from ui.analysis import render_analysis
        capture = io.StringIO()
        test_console = Console(file=capture, force_terminal=False)
        import ui.analysis
        orig_console = ui.analysis.console
        ui.analysis.console = test_console
        try:
            long_msg = "A" * 1000
            render_analysis({
                "risk": "LOW",
                "confidence": 0.5,
                "message": long_msg,
            })
            output = capture.getvalue()
            assert "A" in output
            assert "..." in output
            assert len(output) < 2000
        finally:
            ui.analysis.console = orig_console

    def test_render_analysis_cached(self):
        from ui.analysis import render_analysis
        capture = io.StringIO()
        test_console = Console(file=capture, force_terminal=False)
        import ui.analysis
        orig_console = ui.analysis.console
        ui.analysis.console = test_console
        try:
            render_analysis({
                "risk": "SAFE",
                "cached": True,
            })
            output = capture.getvalue()
            assert "cached" in output
        finally:
            ui.analysis.console = orig_console

    def test_render_analysis_early_exit(self):
        from ui.analysis import render_analysis
        capture = io.StringIO()
        test_console = Console(file=capture, force_terminal=False)
        import ui.analysis
        orig_console = ui.analysis.console
        ui.analysis.console = test_console
        try:
            render_analysis({
                "risk": "LOW",
                "early_exit": "rule_engine",
            })
            output = capture.getvalue()
            assert "Early exit" in output
            assert "deterministic rule" in output
        finally:
            ui.analysis.console = orig_console

    def test_render_analysis_command_guide(self):
        from ui.analysis import render_analysis
        capture = io.StringIO()
        test_console = Console(file=capture, force_terminal=False)
        import ui.analysis
        orig_console = ui.analysis.console
        ui.analysis.console = test_console
        try:
            render_analysis({
                "risk": "SAFE",
                "command_guide": {
                    "intent_guess": "Maybe you're trying to list files in the current directory",
                    "when_to_use": "When you need to list files",
                    "parameters": ["-l: long format", "-a: show hidden"],
                    "suggested_command": "ls -la",
                    "example_command": "ls -la",
                },
            })
            output = capture.getvalue()
            assert "Command guide" in output
            assert "Maybe you're trying" in output
            assert "When to use" in output
            assert "Use:" in output
            assert "ls -la" in output
        finally:
            ui.analysis.console = orig_console

    def test_render_analysis_supervisor_warning(self):
        from ui.analysis import render_analysis
        capture = io.StringIO()
        test_console = Console(file=capture, force_terminal=False)
        import ui.analysis
        orig_console = ui.analysis.console
        ui.analysis.console = test_console
        try:
            render_analysis({
                "risk": "SAFE",
                "supervisor_warning": "supervisor unavailable",
            })
            output = capture.getvalue()
            assert "supervisor unavailable" in output
        finally:
            ui.analysis.console = orig_console

    def test_render_analysis_no_guide_when_absent(self):
        from ui.analysis import render_analysis
        capture = io.StringIO()
        test_console = Console(file=capture, force_terminal=False)
        import ui.analysis
        orig_console = ui.analysis.console
        ui.analysis.console = test_console
        try:
            render_analysis({"risk": "SAFE"})
            output = capture.getvalue()
            assert "Command guide" not in output
        finally:
            ui.analysis.console = orig_console

    def test_render_analysis_limits_alternatives(self):
        from ui.analysis import render_analysis
        capture = io.StringIO()
        test_console = Console(file=capture, force_terminal=False)
        import ui.analysis
        orig_console = ui.analysis.console
        ui.analysis.console = test_console
        try:
            alternatives = [f"alt_{i}" for i in range(10)]
            render_analysis({
                "risk": "MEDIUM",
                "alternatives": alternatives,
            })
            output = capture.getvalue()
            assert "alt_0" in output
            assert "alt_4" in output
            assert "alt_5" not in output
        finally:
            ui.analysis.console = orig_console


class TestStatusUI:
    def test_render_status_running(self):
        from ui.status import render_status
        capture = io.StringIO()
        test_console = Console(file=capture, force_terminal=True, width=120)
        import ui.status
        orig_console = ui.status.console
        ui.status.console = test_console
        try:
            render_status(
                daemon_status={"status": "running", "pid": 12345, "cwd": "/test", "uptime_seconds": 60},
                provider_status={"groq": {"configured": True, "status": "ok"}},
                credential_status={"GROQ_API_KEY": {"configured": True, "label": "Groq"}},
                agent_status={"watcher": "ready", "librarian": "ready"},
            )
            output = capture.getvalue()
            assert "PID:" in output
            assert "watcher" in output
            assert "librarian" in output
            assert "groq" in output
        finally:
            ui.status.console = orig_console

    def test_render_status_stopped(self):
        from ui.status import render_status
        capture = io.StringIO()
        test_console = Console(file=capture, force_terminal=True, width=120)
        import ui.status
        orig_console = ui.status.console
        ui.status.console = test_console
        try:
            render_status(
                daemon_status={"status": "stopped"},
                provider_status={},
                credential_status={},
            )
            output = capture.getvalue()
            assert "Stopped" in output
        finally:
            ui.status.console = orig_console


class TestErrorPanel:
    """UI-01: Error panel with actionable next steps."""

    def test_error_panel_with_next_steps(self):
        from cli.main import print_error_panel
        capture = io.StringIO()
        test_console = Console(file=capture, force_terminal=False)
        print_error_panel("Something went wrong",
                          suggestion="Try again",
                          next_steps=["Step 1", "Step 2", "Step 3"],
                          _console=test_console)
        output = capture.getvalue()
        assert "Error:" in output
        assert "Something went wrong" in output
        assert "Next steps:" in output
        assert "1. Step 1" in output
        assert "2. Step 2" in output
        assert "3. Step 3" in output

    def test_error_panel_without_next_steps(self):
        from cli.main import print_error_panel
        capture = io.StringIO()
        test_console = Console(file=capture, force_terminal=False)
        print_error_panel("Simple error", _console=test_console)
        output = capture.getvalue()
        assert "Error:" in output
        assert "Next steps:" not in output


class TestHealthCheckInStatus:
    """UI-02: last_health_check exposed in /status + rendered."""

    def test_status_response_includes_last_health_check(self):
        from daemon.server import ShellMateDaemon
        daemon = ShellMateDaemon()
        result = daemon._handle_status()
        assert "last_health_check" in result.get("data", {})

    def test_render_status_displays_last_health_check(self):
        from ui.status import render_status
        capture = io.StringIO()
        test_console = Console(file=capture, force_terminal=True, width=120)
        import ui.status
        orig_console = ui.status.console
        ui.status.console = test_console
        try:
            render_status(
                daemon_status={
                    "status": "running", "pid": 123, "cwd": "/test",
                    "uptime_seconds": 60, "last_health_check": 42,
                },
                provider_status={},
                credential_status={},
            )
            output = capture.getvalue()
            assert "42" in output or "Health:" in output
        finally:
            ui.status.console = orig_console


class TestAnalysisProgress:
    def test_analysis_progress_context_manager(self):
        from ui.progress import analysis_progress
        capture = io.StringIO()
        test_console = Console(file=capture, force_terminal=True)
        with analysis_progress(test_console, interval=0.01):
            pass
        output = capture.getvalue()
        assert "Routing" in output


class TestNoColorMode:
    """UI-03: --no-color plain-text output mode."""

    def test_get_console_returns_plain_when_no_color(self):
        from cli.main import _get_console, _plain_console, console
        class FakeParsed:
            no_color = True
        result = _get_console(FakeParsed())
        assert result.no_color is True
        assert result is _plain_console

    def test_get_console_returns_color_by_default(self):
        from cli.main import _get_console, console
        class FakeParsed:
            no_color = False
        result = _get_console(FakeParsed())
        assert result is console

    def test_get_console_returns_color_when_no_parsed(self):
        from cli.main import _get_console, console
        result = _get_console(None)
        assert result is console


class TestBannerUI:
    def test_print_banner(self):
        from ui.banner import print_banner
        capture = io.StringIO()
        test_console = Console(file=capture, force_terminal=False)
        import ui.banner
        orig_console = ui.banner.console
        ui.banner.console = test_console
        try:
            print_banner()
            output = capture.getvalue()
            assert "\u250c" in output
            assert "\u2518" in output
        finally:
            ui.banner.console = orig_console

    def test_print_usage(self):
        from ui.banner import print_usage
        capture = io.StringIO()
        test_console = Console(file=capture, force_terminal=False)
        import ui.banner
        orig_console = ui.banner.console
        ui.banner.console = test_console
        try:
            print_usage()
            output = capture.getvalue()
            assert "Usage:" in output
            assert "sm -a" in output
            assert "sm enable" in output
            assert "Examples:" in output
        finally:
            ui.banner.console = orig_console

    def test_render_enable_panel(self):
        from ui.banner import render_enable_panel
        from rich.panel import Panel
        panel = render_enable_panel([("Watcher ready", True), ("Librarian ready", False)])
        assert isinstance(panel, Panel)
        text = panel.renderable
        assert "ShellMate" in str(text) or "ShellMate" in panel.title


class TestStartupUI:
    def test_startup_ui_imports_enable_panel(self):
        from daemon.startup_ui import STAGE_LABELS, render_enable_panel as _rep
        assert len(STAGE_LABELS) == 7
        assert STAGE_LABELS[0] == ("binding_ipc", "Binding IPC")
        assert STAGE_LABELS[-1] == ("ready", "Ready")
