from daemon.lifecycle import start_daemon
from daemon.startup_ui import run_startup_ui


def enable():
    if start_daemon():
        run_startup_ui()