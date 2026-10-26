"""Drive an interactive `pwsh` through a Windows pseudo-console (ConPTY).

PSReadLine disables its key handlers when stdin is a plain redirected pipe, so a
real pseudo-console is required to exercise the Enter/Tab handlers in
powershell_adapter.ps1. We spawn pwsh inside a ConPTY via pywinpty, inject
keystrokes, and feed the VT output stream into a `pyte` screen emulator so we can
assert on the *rendered* terminal (the adapter writes annotations below the
prompt with cursor save/restore, which only a screen emulator resolves).

This is inherently timing-sensitive; callers should use generous `wait_for`
timeouts and treat it as best-effort (tests are marked @conpty / opt-in).

Requires: pwsh 7.2+, pywinpty (`winpty`), and pyte. `available()` reports readiness.
"""

from __future__ import annotations

import threading
import time
from typing import Optional


def available() -> bool:
    try:
        import pyte  # noqa: F401
        import winpty  # noqa: F401
    except Exception:
        return False
    return True


class PwshConsole:
    """A live pwsh session in a ConPTY with a pyte screen mirror."""

    def __init__(
        self,
        adapter_path: str,
        *,
        cols: int = 120,
        rows: int = 40,
        cwd: Optional[str] = None,
        env: Optional[dict] = None,
        pwsh: str = "pwsh",
    ):
        import pyte
        from winpty import PtyProcess

        self._screen = pyte.Screen(cols, rows)
        self._stream = pyte.Stream(self._screen)
        self._lock = threading.Lock()
        self._alive = True

        # Start a plain interactive session. The adapter MUST be sourced after
        # PSReadLine is live (i.e. once the interactive prompt exists) or its
        # Set-PSReadLineKeyHandler calls no-op -- sourcing via -Command at spawn
        # runs before PSReadLine loads and the Enter/Tab handlers never register.
        cmdline = f'{pwsh} -NoProfile -NoLogo -NoExit'
        self._proc = PtyProcess.spawn(cmdline, dimensions=(rows, cols), cwd=cwd, env=env)

        self._reader = threading.Thread(target=self._pump, daemon=True)
        self._reader.start()

        # Wait for the first interactive prompt, then source the adapter by typing.
        if not self.wait_for("PS ", timeout=15.0):
            time.sleep(1.0)
        self._proc.write(f". '{adapter_path}'\r")
        # Give the handlers time to register. PSReadLine processes the dot-source
        # and registers the Enter/Tab handlers; racing the first command against
        # this causes intermittent misses, so settle generously.
        time.sleep(3.5)

    # -- output pump ------------------------------------------------------- #
    def _pump(self):
        while self._alive:
            try:
                data = self._proc.read(4096)
            except EOFError:
                break
            except Exception:
                break
            if not data:
                time.sleep(0.01)
                continue
            with self._lock:
                self._stream.feed(data)

    # -- input ------------------------------------------------------------- #
    def type(self, text: str):
        self._proc.write(text)

    def send_enter(self):
        self._proc.write("\r")

    def send_tab(self):
        self._proc.write("\t")

    def send_ctrl_c(self):
        self._proc.write("\x03")

    # -- screen inspection ------------------------------------------------- #
    def screen_text(self) -> str:
        with self._lock:
            return "\n".join(self._screen.display)

    def wait_for(self, needle: str, timeout: float = 5.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if needle in self.screen_text():
                return True
            time.sleep(0.05)
        return False

    def type_enter_expect(self, command: str, needle: str, *, timeout: float = 8.0, retries: int = 2) -> bool:
        """Type a command, press Enter, wait for `needle`; retry on miss.

        Between attempts the line is abandoned (Esc) so a racing/duplicate
        buffer does not pollute the next try. Robustness shim for ConPTY timing.
        """
        for attempt in range(retries + 1):
            self.type(command)
            time.sleep(0.4)
            self.send_enter()
            if self.wait_for(needle, timeout=timeout):
                return True
            # clear whatever is on the line and try again
            self._proc.write("\x1b")
            time.sleep(0.3)
            self.send_enter()
            time.sleep(0.5)
        return False

    def has_stray_escape(self) -> bool:
        """True if raw ESC bytes leaked onto the rendered screen (corruption)."""
        return "\x1b" in self.screen_text()

    # -- lifecycle --------------------------------------------------------- #
    def close(self):
        self._alive = False
        try:
            self._proc.write("\r")  # nudge out of any handler
            self._proc.close(force=True)
        except Exception:
            pass
