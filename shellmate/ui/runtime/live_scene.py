"""One Live region per command: morph updates, then settle to a static frame."""

from __future__ import annotations

from typing import Any, Optional

from rich.console import Console, RenderableType
from rich.live import Live


class LiveScene:
    """Owns a single Rich Live (or static printer in plain mode).

    Guarantees: settle shows the final frame once; render failures fall back
    to static print and never raise to the caller by default.
    """

    def __init__(self, console: Console, *, plain: bool = False, refresh_per_second: int = 12):
        self.console = console
        self.plain = plain
        self.refresh_per_second = refresh_per_second
        self._live: Optional[Live] = None
        self._started = False
        self._settled = False
        self._fallback = False
        self._transient = False

    def start(self, initial: RenderableType) -> None:
        if self._started:
            return
        self._started = True
        if self.plain:
            return
        try:
            # transient=False so Windows/Cursor terminals keep painting mid-frames.
            # settle() updates in-place then stops without reprinting a duplicate.
            self._transient = False
            self._live = Live(
                initial,
                console=self.console,
                refresh_per_second=self.refresh_per_second,
                transient=self._transient,
                auto_refresh=True,
            )
            self._live.start()
            try:
                self._live.refresh()
            except Exception:
                pass
        except Exception:
            self._fallback = True
            self._live = None

    def update(self, renderable: RenderableType) -> None:
        if self.plain or self._fallback or self._settled:
            return
        if self._live is None:
            return
        try:
            self._live.update(renderable, refresh=True)
        except TypeError:
            try:
                self._live.update(renderable)
                self._live.refresh()
            except Exception:
                self._fallback = True
                self._stop_live_quiet()
        except Exception:
            self._fallback = True
            self._stop_live_quiet()

    def settle(self, final: RenderableType) -> None:
        """Show the final frame once (in-place if Live is active)."""
        if self._settled:
            return
        self._settled = True

        if self._live is not None and not self._fallback:
            try:
                try:
                    self._live.update(final, refresh=True)
                except TypeError:
                    self._live.update(final)
                    self._live.refresh()
                # Leave non-transient final frame on screen; do not reprint.
                self._stop_live_quiet()
                if self._transient:
                    self.console.print(final)
                return
            except Exception:
                self._stop_live_quiet()

        try:
            self.console.print(final)
        except Exception:
            try:
                with self.console.capture() as cap:
                    self.console.print(final)
                self.console.print(cap.get())
            except Exception:
                pass

    def _stop_live_quiet(self) -> None:
        if self._live is None:
            return
        try:
            self._live.stop()
        except Exception:
            pass
        self._live = None

    def __enter__(self) -> "LiveScene":
        return self

    def __exit__(self, *exc: Any) -> None:
        self._stop_live_quiet()
