# Windows pip-package test series

End-to-end validation of **ShellMate as the installed `shellmate-cli` wheel on
Windows**, targeting **PowerShell 7.2+ (`pwsh`) + PSReadLine**. Every test runs
against a wheel built and `pip install`ed into a throwaway venv (not the dev
tree), with config/state isolated under temp `APPDATA`/`LOCALAPPDATA`.

## Series

| File | Series | What it proves | Needs |
|------|--------|----------------|-------|
| `test_a_install_deps.py` | A | entry points, all runtime deps import, bundled adapters/rules present | wheel build |
| `test_b_cli_lifecycle.py` | B | profile hook idempotency, enable/status/disable daemon, config/uninstall on `%APPDATA%` | — |
| `test_c_instant_tier.py` | C | local catastrophic matcher (Tier-1 Enter block), keystroke P99 <10 ms | — |
| `test_d_pipeline_offline.py` | D | `/analyze-partial` degrades gracefully with no key, completions, daemon endpoints | — |
| `test_e_live_ai.py` | E | consequence preview, AI risk classification, remediation, latency | **API key** |
| `test_f_psreadline_conpty.py` | F | real PSReadLine UX (Enter-block, passthrough, no corruption) via ConPTY | **pwsh + pywinpty + pyte** |
| `test_g_predictor.py` | G | predictor subsystem registration + completion data source | **pwsh** |
| `pester/ShellMateAdapter.Tests.ps1` | G-floor | adapter function surface + behaviour (deterministic) | Pester 5+ |

## Prerequisites

```powershell
# core (Series A–D, G-predictor)
pip install -e ".[dev]"

# interactive UX automation (Series F)
pip install -e ".[windows-test]"      # pywinpty + pyte
winget install Microsoft.PowerShell   # provides pwsh 7.2+ (Series F & G)

# Pester floor
Install-Module Pester -Scope CurrentUser -Force
```

> Series F and G **auto-skip** when `pwsh` / `pywinpty` / `pyte` are missing — they
> never fail the run; they just don't execute. Windows PowerShell 5.1 does **not**
> count as `pwsh`.

## Running

```powershell
# offline tiers — no key needed (A–D, G-predictor if pwsh present)
pytest tests/windows_e2e -m "windows and not requires_api" -v

# interactive UX only (opt-in; flaky by nature)
pytest tests/windows_e2e/test_f_psreadline_conpty.py -m conpty -v

# live AI tier — set a key first, then:
$env:GROQ_API_KEY       = "<groq key>"        # required for risk analysis
$env:OPENROUTER_API_KEY = "<openrouter key>"  # optional: remediation / fallback
pytest tests/windows_e2e -m requires_api -v

# Pester floor (run from repo root so python can import the package)
Invoke-Pester tests/windows_e2e/pester/ShellMateAdapter.Tests.ps1
```

**Never paste keys into source or chat** — set them as environment variables in the
session. With no key present, the entire live tier skips cleanly (green, not failed).

## Live feature walkthrough

`walkthrough.py` boots the daemon and opens a REAL pwsh ConPTY session, narrating
every feature one-by-one as a user experiences it (Tab ghost-text, instant block,
live AI consequence preview, safe passthrough):

```powershell
$env:GROQ_API_KEY = "<your groq key>"
$env:GROQ_MODEL   = "qwen/qwen3.8-27b"   # see caveat below
python tests/windows_e2e/walkthrough.py
```

### Caveat: default Groq model may 404 for your key

ShellMate's shipped defaults use `llama-3.3-70b-versatile` (risk) and
`llama-3.1-8b-instant` (supervisor/command-guide). Some Groq accounts do **not**
have access to those ids and return `404 - model does not exist`, in which case
the AI tier silently degrades to a static `MEDIUM` fallback. Check your account's
models with `python -c "from groq import Groq; print([m.id for m in Groq().models.list().data])"`
and override via a `config.yaml` (deep-merged over defaults):

```yaml
providers:
  risk_analysis:
    primary: groq
    model: qwen/qwen3.8-27b    # a model your key can access
```

Note: the `GROQ_MODEL` env var only affects a directly-instantiated GroqProvider;
the daemon's risk analyzer reads `providers.risk_analysis.model` from config, so
use `config.yaml` to change it (the walkthrough writes one automatically).

## Notes / known limits

- **ConPTY (Series F) is best-effort.** Pseudo-console timing is inherently flaky;
  tests are marked `@conpty` so they can be deselected. The `@pwsh` predictor tests
  and the Pester floor are the deterministic baseline for the adapter surface.
- The first wheel build per session is slow (session-scoped fixture) — Series using
  the daemon are marked `@slow`.
- Live-tier latency is recorded with a generous 30 s ceiling, not a hard budget.
