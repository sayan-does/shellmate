"""ShellMate end-to-end walkthrough - every feature, one by one, as a user sees it.

Boots the live daemon, opens a REAL PowerShell 7 session in a pseudo-console
(ConPTY), sources the adapter, and narrates each feature with the rendered
terminal and live AI output.

Usage (PowerShell):
    $env:GROQ_API_KEY = "<your groq key>"
    # Optional: the shipped default risk model may 404 for your Groq account;
    # point it at a model your key can access (see `python -m groq` / models.list).
    $env:GROQ_MODEL = "qwen/qwen3.8-27b"
    python tests/windows_e2e/walkthrough.py

Requires: pwsh 7.2+ on PATH, pywinpty + pyte (pip install -e ".[windows-test]"),
and shellmate importable (editable install or installed wheel).
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
ADAPTER = REPO / "shellmate" / "adapters" / "powershell_adapter.ps1"


def _die(msg: str):
    print(f"[walkthrough] {msg}")
    sys.exit(1)


if not os.environ.get("GROQ_API_KEY"):
    _die('Set $env:GROQ_API_KEY first (live AI tier needs it).')

PWSH = os.environ.get("SM_PWSH") or shutil.which("pwsh")
if not PWSH:
    alias = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WindowsApps" / "pwsh.exe"
    PWSH = str(alias) if alias.exists() else None
if not PWSH:
    _die("PowerShell 7 (pwsh) not found. Install: winget install Microsoft.PowerShell")

MODEL = os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b")


def banner(n, title):
    print("\n" + "=" * 74)
    print(f"  FEATURE {n}: {title}")
    print("=" * 74)


def show_screen(text):
    lines = [l.rstrip() for l in text.splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    print("  +" + "-" * 70 + "+")
    for l in lines[-10:]:
        print("  | " + l[:68].ljust(68) + " |")
    print("  +" + "-" * 70 + "+")


# Isolate state/config/cache so a stale semantic-cache entry can't mask live output.
_state = tempfile.mkdtemp(prefix="sm_walk_state_")
for _k in ("LOCALAPPDATA", "APPDATA", "XDG_STATE_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME"):
    os.environ[_k] = _state

import yaml  # noqa: E402
from shellmate.config.paths import get_config_dir  # noqa: E402
from shellmate.daemon.lifecycle import start_daemon, stop_daemon  # noqa: E402
from shellmate.ipc.ps_client import PSReadLineSyncClient  # noqa: E402
from tests.e2e.helpers.daemon_utils import kill_stale_daemons, wait_for_daemon_ready  # noqa: E402

# Point risk analysis at a model this key can access (deep-merged over defaults).
cfgdir = get_config_dir()
cfgdir.mkdir(parents=True, exist_ok=True)
(cfgdir / "config.yaml").write_text(
    yaml.safe_dump({"providers": {"risk_analysis": {"primary": "groq", "model": MODEL}}}),
    encoding="utf-8",
)

print("=" * 74)
print("  ShellMate system walkthrough")
print(f"  pwsh={PWSH}")
print(f"  risk model={MODEL}   state={_state}")
print("=" * 74)

print("\nBooting daemon (live Groq)...")
kill_stale_daemons()
start_daemon(wait_ready=True)
info = wait_for_daemon_ready(timeout=30)
print(f"  daemon ready: stage={info.get('startup_stage')} pid={info.get('daemon_pid')}")
client = PSReadLineSyncClient()

# ----- open interactive pwsh in a ConPTY and source the adapter ------------- #
import pyte  # noqa: E402
from winpty import PtyProcess  # noqa: E402

pwsh_env = os.environ.copy()
# python-dir first (so the adapter's `python` has shellmate), then pwsh's dir.
pwsh_env["PATH"] = os.pathsep.join(
    [os.path.dirname(sys.executable), os.path.dirname(PWSH), pwsh_env.get("PATH", "")]
)
workdir = tempfile.mkdtemp(prefix="sm_walk_cwd_")

screen = pyte.Screen(110, 36)
stream = pyte.Stream(screen)
# Spawn bare `pwsh` (resolved via PATH) - pywinpty can't exec the quoted alias path.
proc = PtyProcess.spawn('pwsh -NoProfile -NoLogo -NoExit', dimensions=(36, 110), cwd=workdir, env=pwsh_env)
_alive = [True]


def _pump():
    while _alive[0]:
        try:
            data = proc.read(4096)
        except Exception:
            break
        if data:
            stream.feed(data)
        else:
            time.sleep(0.01)


threading.Thread(target=_pump, daemon=True).start()


def screen_text():
    return "\n".join(screen.display)


def wait_for(needle, t=10):
    end = time.time() + t
    while time.time() < end:
        if needle in screen_text():
            return True
        time.sleep(0.05)
    return False


wait_for("PS ", 15)
proc.write(f". '{ADAPTER}'\r")
time.sleep(2.5)
print("Interactive pwsh ready; adapter sourced.\n")

# ----- FEATURE 1: Tab ghost-text completion -------------------------------- #
banner(1, "Tab ghost-text completion  (type 'git pu', press Tab)")
proc.write("git pu")
time.sleep(0.4)
proc.write("\t")
time.sleep(1.5)
show_screen(screen_text())
print(f"  -> inline ghost-text served by predictor/Tab; suggestions: {client.complete_sync('git pu').get('completions')}")
proc.write("\x1b")
time.sleep(0.2)
proc.write("\r")
time.sleep(0.5)

# ----- FEATURE 2: instant catastrophic block ------------------------------- #
banner(2, "Instant block  (type 'git push --force origin main', Enter)")
proc.write("git push --force origin main")
time.sleep(0.4)
proc.write("\r")
blocked = wait_for("BLOCKING", 8)
show_screen(screen_text())
print(f"  -> BLOCKING banner: {blocked}; first Enter SUPPRESSED (not executed).")
print("  -> second Enter would confirm & run (double-tap safety gate).")
proc.write("\x1b")
time.sleep(0.2)
proc.write("\r")
time.sleep(0.5)

# ----- FEATURE 3: live consequence preview (Groq) -------------------------- #
banner(3, "Live consequence preview  (AI risk analysis via Groq)")


def preview(cmd, tries=3):
    r = {}
    for _ in range(tries):
        r = client.send_command_partial_sync(cmd, timeout=40.0)
        if (r.get("consequence_preview") or {}).get("what_happens"):
            return r
        time.sleep(1.5)
    return r


for cmd in ["kubectl delete deployment api --namespace prod", "rm -rf /"]:
    print(f"\n  $ {cmd}")
    r = preview(cmd)
    cp = r.get("consequence_preview") or {}
    print(f"    pipeline     : {r.get('pipeline')}   severity: {r.get('severity')}")
    print(f"    what happens : {cp.get('what_happens')}")
    print(f"    reversible   : {cp.get('reversible')}")
    if cp.get("suggested_fix"):
        print(f"    safe alt     : {cp.get('suggested_fix')}")

# ----- FEATURE 4: safe command passes clean -------------------------------- #
banner(4, "Safe command  (type 'Get-ChildItem', Enter) - no friction")
screen.reset()  # clear lingering Feature-2 banner from the cumulative screen
proc.write("Get-ChildItem")
time.sleep(0.3)
proc.write("\r")
time.sleep(1.5)
print(f"  -> executed normally; blocking banner absent: {'BLOCKING' not in screen_text()}")

# ----- teardown ------------------------------------------------------------ #
_alive[0] = False
try:
    proc.close(force=True)
except Exception:
    pass
print("\nShutting down daemon...")
stop_daemon()
kill_stale_daemons()
print("Walkthrough complete.")
sys.stdout.flush()
os._exit(0)  # skip noisy winpty/asyncio teardown
