import time
import threading
from contextlib import contextmanager
from rich.console import Console
from rich.status import Status
from rich.text import Text

STAGES = [
    (">  Routing command...", "dots12"),
    ("*  Gathering context...", "dots12"),
    ("*  Analyzing risk...", "dots12"),
    (">  Building usage guide...", "dots12"),
    ("*  Formatting result...", "dots12"),
]


@contextmanager
def analysis_progress(console: Console, interval: float = 0.4):
    stop = threading.Event()
    idx = [0]

    def cycle(status: Status):
        while not stop.is_set():
            text, spinner = STAGES[idx[0] % len(STAGES)]
            status.update(text, spinner=spinner)
            idx[0] += 1
            stop.wait(interval)

    with console.status(STAGES[0][0], spinner=STAGES[0][1]) as status:
        t = threading.Thread(target=cycle, args=(status,), daemon=True)
        t.start()
        try:
            yield
        finally:
            stop.set()
            t.join(timeout=1.0)
