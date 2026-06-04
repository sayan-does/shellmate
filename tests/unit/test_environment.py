import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from environment.detector import detect_os, detect_shell, detect_environment_type, detect_terminal, detect_environment


class TestEnvironment:
    def test_detect_os(self):
        o = detect_os()
        assert o in ("linux", "windows", "macos")

    def test_detect_shell(self):
        shell = detect_shell()
        assert shell in ("bash", "zsh", "fish", "powershell", "cmd", "unknown")

    def test_detect_environment_type(self):
        env_type = detect_environment_type()
        assert env_type in ("native", "wsl", "container", "ssh")

    def test_detect_terminal(self):
        terminal = detect_terminal()
        assert isinstance(terminal, str)

    def test_detect_environment_full(self):
        env = detect_environment()
        assert "os" in env
        assert "shell" in env
        assert "environment" in env
        assert "terminal" in env
        assert isinstance(env, dict)
        assert len(env) == 4
