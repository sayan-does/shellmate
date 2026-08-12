import os
import sys
import click
import subprocess
from shellmate.config.credentials import load_env, save_env, CREDENTIAL_KEYS


def _echo(message: str, **style_kwargs):
    """Echo text safely on Windows consoles that reject emoji codepoints."""
    text = message if not style_kwargs else click.style(message, **style_kwargs)
    try:
        click.echo(text)
    except UnicodeEncodeError:
        click.echo(text.encode("ascii", errors="replace").decode("ascii"))


def _confirm(text: str, default: bool = True) -> bool:
    """click.confirm that returns default when stdin is non-interactive."""
    try:
        return click.confirm(text, default=default)
    except click.Abort:
        return default
    except EOFError:
        return default


def _get_sm_path() -> str:
    """Resolve ShellMate package/repo root for adapter paths."""
    try:
        import shellmate

        path = os.path.dirname(shellmate.__file__)
        if os.path.isdir(os.path.join(path, "adapters")):
            return path
    except ImportError:
        pass

    # cli/commands/init.py -> commands -> cli -> repo root
    here = os.path.abspath(__file__)
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(here)))
    if os.path.isdir(os.path.join(repo_root, "adapters")):
        return repo_root

    # Last resort: walk parents looking for adapters/
    cur = os.path.dirname(here)
    for _ in range(5):
        if os.path.isdir(os.path.join(cur, "adapters")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return repo_root


def _powershell_profile_paths():
    home = os.path.expanduser("~")
    return [
        os.path.join(home, "Documents", "PowerShell", "Microsoft.PowerShell_profile.ps1"),
        os.path.join(
            home, "Documents", "WindowsPowerShell", "Microsoft.PowerShell_profile.ps1"
        ),
    ]


def _is_windows_target() -> bool:
    if sys.platform == "win32":
        return True
    try:
        from shellmate.environment.detector import detect_os, detect_shell

        return detect_os() == "windows" or detect_shell() == "powershell"
    except Exception:
        return False


@click.command()
@click.option("--skip-keys", is_flag=True, help="Skip API key setup")
@click.option("--skip-blesh", is_flag=True, help="Skip ble.sh installation")
@click.option(
    "--install-hooks",
    is_flag=True,
    help="Install shell hooks even with --skip-keys/--skip-blesh",
)
@click.option(
    "--validate",
    "validate_only",
    is_flag=True,
    help="Only run setup validation checks",
)
def init(skip_keys, skip_blesh, install_hooks, validate_only):
    """First-run setup wizard for ShellMate autocomplete"""

    if validate_only:
        _validate_setup()
        return

    _echo("\nShellMate Autocomplete Setup\n", bold=True, fg="cyan")

    windows = _is_windows_target()

    # Step 1: Check ble.sh (Unix/WSL autocomplete surface)
    if windows:
        if not skip_blesh:
            _echo("Windows detected: PowerShell adapter will be used (ble.sh skipped).")
    elif not skip_blesh:
        if not _check_blesh_installed():
            _echo("ble.sh not found. Installing...")
            if _confirm("Install ble.sh now?", default=True):
                _install_blesh()
            else:
                _echo("[!] ble.sh required for autocomplete mode.")
                _echo("Install manually: https://github.com/akinomyoga/ble.sh")
                return

    # Step 2: API keys
    if not skip_keys:
        _setup_api_keys()

    # Step 3: Install platform hook
    # Smoke path (--skip-keys --skip-blesh) avoids mutating shell RC files
    # unless --install-hooks is set (so --validate can pass after a dry init).
    smoke_skip_hooks = skip_keys and skip_blesh and not install_hooks
    if smoke_skip_hooks:
        _echo("Skipping shell hook install (--skip-keys --skip-blesh).")
        _echo("  Tip: re-run with --install-hooks to wire your shell profile.")
    elif windows:
        _install_powershell_hook()
    elif _check_blesh_installed():
        _install_autocomplete_hook()
    else:
        _echo("[!] Skipping autocomplete hook (ble.sh not installed).")

    # Step 4: Validate setup
    if smoke_skip_hooks:
        _echo("Skipping interactive validation (--skip-keys --skip-blesh).")
    elif install_hooks or skip_keys:
        # Non-interactive polish path: always validate after hook install
        _validate_setup()
    elif _confirm("\nRun validation check?", default=True):
        _validate_setup()

    _echo("\n[OK] Setup complete!", bold=True, fg="green")
    _echo("\nNext steps:")
    if windows:
        _echo("  1. Restart PowerShell (or reload your profile)")
        _echo("  2. Run: shellmate enable")
        _echo("  3. Start typing commands to see annotations!\n")
    else:
        _echo("  1. Restart your shell (or run: source ~/.bashrc)")
        _echo("  2. Run: shellmate enable")
        _echo("  3. Start typing commands to see autocomplete!\n")


def _check_blesh_installed():
    """Check if ble.sh is already installed"""
    blesh_paths = [
        os.path.expanduser("~/.local/share/blesh/ble.sh"),
        os.path.expanduser("~/ble.sh/out/ble.sh"),
    ]
    return any(os.path.exists(p) for p in blesh_paths)


def _install_blesh():
    """Auto-install ble.sh to ~/.local (requires bash + make; typically Linux/WSL)."""
    import shutil

    home = os.path.expanduser("~")
    clone_dir = os.path.join(home, ".shellmate", "ble.sh")
    make_bin = shutil.which("make")

    # Windows/MINGW often has no make on PATH — fail early with guidance
    if not make_bin and sys.platform == "win32":
        _echo("[X] Cannot build ble.sh: 'make' was not found on PATH.", fg="red")
        _echo("")
        _echo("ble.sh autocomplete needs a Unix build toolchain.")
        _echo("On this Windows machine you can:")
        _echo("  1. Use ShellMate PowerShell adapter (recommended here):")
        _echo("       sm init --skip-blesh")
        _echo("       sm enable")
        _echo("  2. Install make (MSYS2 / Git for Windows SDK) and re-run: sm init")
        _echo("  3. Use WSL/Linux bash for full ble.sh autocomplete:")
        _echo("       wsl")
        _echo("       cd /mnt/d/projects/shellmate && sm init && sm enable")
        _echo("")
        if os.path.isdir(clone_dir):
            _echo(f"(ble.sh sources already cloned at {clone_dir})")
        return False

    try:
        if not os.path.exists(clone_dir):
            _echo("Cloning ble.sh...")
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--recursive",
                    "https://github.com/akinomyoga/ble.sh.git",
                    clone_dir,
                ],
                check=True,
            )

        _echo("Building ble.sh...")
        subprocess.run(
            [make_bin or "make", "install", f"PREFIX={home}/.local"],
            cwd=clone_dir,
            check=True,
        )

        _echo("[OK] ble.sh installed", fg="green")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        _echo(f"[X] Installation failed: {e}", fg="red")
        _echo("\nManual installation (Linux/WSL/Git Bash with make):")
        _echo("  git clone --recursive https://github.com/akinomyoga/ble.sh.git")
        _echo("  cd ble.sh && make install PREFIX=~/.local")
        return False


def _setup_api_keys():
    """Interactive API key setup"""
    _echo("\nAPI Key Setup")
    _echo(
        "ShellMate uses AI for risk analysis. Configure keys or skip for rule-based mode.\n"
    )

    if not _confirm("Configure API keys now?", default=True):
        _echo("Skipped. Run 'shellmate configure' later.")
        return

    env = load_env()
    for key_name in CREDENTIAL_KEYS:
        current = env.get(key_name, "")
        if current:
            _echo(f"{key_name}: [already set]")
            if not _confirm("Update?", default=False):
                continue

        try:
            value = click.prompt(f"Enter {key_name}", default="", show_default=False)
        except (click.Abort, EOFError):
            value = ""
        if value:
            env[key_name] = value

    save_env(env)
    _echo("[OK] Keys saved to ~/.shellmate/.env", fg="green")


def _install_autocomplete_hook():
    """Add ble.sh + ShellMate to .bashrc (Unix autocomplete surface)."""
    home = os.path.expanduser("~")
    bashrc = os.path.join(home, ".bashrc")

    # Detect ble.sh location
    blesh_path = None
    for path in [
        os.path.join(home, ".local/share/blesh/ble.sh"),
        os.path.join(home, "ble.sh/out/ble.sh"),
    ]:
        if os.path.exists(path):
            blesh_path = path
            break

    if not blesh_path:
        _echo("[X] ble.sh not found after installation")
        return False

    sm_path = _get_sm_path()
    adapter_path = os.path.join(sm_path, "adapters", "ble_adapter.sh")

    if not os.path.exists(adapter_path):
        _echo(f"[X] Adapter not found at {adapter_path}")
        return False

    snippet = f'''
# ShellMate Autocomplete Integration
if [[ $- == *i* ]]; then
    # Ensure ShellMate is in PYTHONPATH
    export PYTHONPATH="{sm_path}:$PYTHONPATH"

    source {blesh_path}
    [[ -f {adapter_path} ]] && source {adapter_path}
fi
'''

    if os.path.exists(bashrc):
        with open(bashrc, "r") as f:
            content = f.read()
        if "ShellMate Autocomplete" in content:
            _echo("[OK] Already integrated in .bashrc")
            return True

    with open(bashrc, "a") as f:
        f.write(snippet)

    _echo(f"[OK] Added to {bashrc}", fg="green")
    return True


def _install_powershell_hook():
    """Add ShellMate PowerShell adapter to the user profile."""
    sm_path = _get_sm_path()
    adapter_path = os.path.join(sm_path, "adapters", "powershell_adapter.ps1")

    if not os.path.exists(adapter_path):
        _echo(f"[X] Adapter not found at {adapter_path}")
        return False

    # Prefer forward-slash style that PowerShell accepts; keep absolute path.
    adapter_ps = adapter_path.replace("'", "''")
    snippet = (
        "\n# ShellMate Autocomplete Integration\n"
        f"if (Test-Path '{adapter_ps}') {{ . '{adapter_ps}' }}\n"
    )

    installed = False
    for profile_path in _powershell_profile_paths():
        profile_dir = os.path.dirname(profile_path)
        if profile_dir and not os.path.exists(profile_dir):
            try:
                os.makedirs(profile_dir, exist_ok=True)
            except OSError as e:
                _echo(f"[!] Could not create {profile_dir}: {e}")
                continue

        if os.path.exists(profile_path):
            with open(profile_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            if "ShellMate Autocomplete" in content:
                _echo(f"[OK] Already integrated in {profile_path}")
                installed = True
                continue
            with open(profile_path, "a", encoding="utf-8") as f:
                f.write(snippet)
        else:
            try:
                with open(profile_path, "w", encoding="utf-8") as f:
                    f.write(snippet.lstrip("\n"))
            except OSError as e:
                _echo(f"[!] Could not write {profile_path}: {e}")
                continue

        _echo(f"[OK] Added to {profile_path}", fg="green")
        installed = True

    if not installed:
        _echo("[X] Could not install PowerShell profile hook")
        return False
    return True


def _profile_integration_ok() -> bool:
    """True if bashrc or a PowerShell profile already has ShellMate Autocomplete."""
    bashrc = os.path.expanduser("~/.bashrc")
    if os.path.exists(bashrc):
        with open(bashrc, "r", encoding="utf-8", errors="replace") as f:
            if "ShellMate Autocomplete" in f.read():
                return True

    for profile_path in _powershell_profile_paths():
        if os.path.exists(profile_path):
            with open(profile_path, "r", encoding="utf-8", errors="replace") as f:
                if "ShellMate Autocomplete" in f.read():
                    return True
    return False


def _adapter_exists() -> bool:
    sm_path = _get_sm_path()
    ble = os.path.join(sm_path, "adapters", "ble_adapter.sh")
    ps = os.path.join(sm_path, "adapters", "powershell_adapter.ps1")
    if _is_windows_target():
        return os.path.exists(ps)
    return os.path.exists(ble) or os.path.exists(ps)


def _validate_setup():
    """Validate ShellMate configuration. Returns True if all checks passed."""
    _echo("\nValidating setup...")

    checks = []
    windows = _is_windows_target()

    # Check 1: ble.sh (required on Unix autocomplete; informational on Windows)
    if windows:
        checks.append(("ble.sh installed (optional on Windows)", True))
    else:
        checks.append(("ble.sh installed", _check_blesh_installed()))

    # Check 2: shell RC integration
    checks.append(("shell profile integration", _profile_integration_ok()))

    # Check 3: API keys configured
    env = load_env()
    has_keys = any(env.get(k) for k in CREDENTIAL_KEYS)
    checks.append(("API keys configured", has_keys))

    # Check 4: Adapter file exists
    checks.append(("Adapter file exists", _adapter_exists()))

    for check_name, passed in checks:
        icon = "[OK]" if passed else "[X]"
        _echo(f"  {icon} {check_name}")

    all_passed = all(c[1] for c in checks)
    if all_passed:
        _echo("\n[OK] All checks passed!", fg="green")
    else:
        _echo("\n[!] Some checks failed", fg="yellow")
    return all_passed
