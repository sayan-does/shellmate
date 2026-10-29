#!/bin/bash
# ShellMate ble.sh adapter — two-phase autocomplete annotations
#
# Phase 1 (instant): catastrophic matcher → placeholder annotation
# Phase 2 (debounced 300ms): /analyze-partial → replace annotation in-place
# Tab×2: accept completion → consequence preview below prompt

# Global state
_SHELLMATE_NEEDS_CONFIRM=""
_SHELLMATE_LAST_DANGEROUS=""
_SHELLMATE_LAST_ANNOTATION=""
_SHELLMATE_DEBOUNCE_PID=""
_SHELLMATE_ROOT=""
_SHELLMATE_TAB_STATE=""             # "" | "suggested" | "consequence_shown"
_SHELLMATE_TAB_CMD=""               # full command string after completion accepted
_SHELLMATE_CONSEQUENCE_REQUIRE_CONFIRM=""   # cmd waiting for second Enter
_SHELLMATE_CONSEQUENCE_CONFIRM_ARMED=""     # set after first Enter blocked

_shellmate_resolve_root() {
  if [[ -n "$_SHELLMATE_ROOT" ]]; then
    echo "$_SHELLMATE_ROOT"
    return
  fi
  local root
  root=$(python3 -c "import shellmate, os; print(os.path.dirname(shellmate.__file__))" 2>/dev/null)
  if [[ -z "$root" ]]; then
    # Fallback: adapter lives in <repo>/adapters/
    root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  fi
  _SHELLMATE_ROOT="$root"
  echo "$root"
}

_shellmate_render_annotation() {
  # Render annotation below command line without moving cursor permanently.
  # Uses ble.sh canvas when available; falls back to ANSI save/restore.
  local text="$1"
  _SHELLMATE_LAST_ANNOTATION="$text"
  if type ble/canvas/put.draw &>/dev/null; then
    ble/canvas/put.draw "\e[91m${text}\e[m"
  else
    # ANSI: save cursor, move down, clear line, write, restore
    printf '\e[s\e[1B\e[2K%s\e[u' "$text" >/dev/tty 2>/dev/null || true
  fi
}

_shellmate_clear_annotation() {
  _SHELLMATE_LAST_ANNOTATION=""
  if type ble/canvas/put.draw &>/dev/null; then
    ble/canvas/put.draw ""
  else
    printf '\e[s\e[1B\e[2K\e[u' >/dev/tty 2>/dev/null || true
  fi
}

_shellmate_render_consequence() {
  # Render up to 3 consequence lines below the prompt using ANSI save/restore.
  local line1="$1" line2="$2" line3="${3:-}"
  if type ble/canvas/put.draw &>/dev/null; then
    ble/canvas/put.draw "${line1}"
  else
    printf '\e[s\e[1B\e[2K%b' "${line1}" >/dev/tty 2>/dev/null || true
    printf '\e[2B\e[2K%b' "${line2}" >/dev/tty 2>/dev/null || true
    if [[ -n "$line3" ]]; then
      printf '\e[3B\e[2K%b' "${line3}" >/dev/tty 2>/dev/null || true
    fi
    printf '\e[u' >/dev/tty 2>/dev/null || true
  fi
}

_shellmate_show_consequence_async() {
  local cmd="$1"
  # Show placeholder immediately
  _shellmate_render_consequence "\e[90m  ⚙ Analyzing…\e[m" "" ""
  _shellmate_cancel_debounce

  (
    local sm_path
    sm_path=$(_shellmate_resolve_root)
    local raw
    raw=$(timeout 1.5 python3 -c "
import sys, json, threading
sys.path.insert(0, r'''$sm_path''')
from ipc.client import analyze_partial_debounced
holder = {}
done = threading.Event()
def _cb(r): holder['r'] = r; done.set()
analyze_partial_debounced(sys.argv[1], _cb)
done.wait(timeout=1.2)
result = holder.get('r') or {}
cp = result.get('consequence_preview') or {}
print(json.dumps({
    'what_happens': cp.get('what_happens', ''),
    'scope': cp.get('scope', ''),
    'reversible': cp.get('reversible', True),
    'suggested_fix': cp.get('suggested_fix', ''),
    'severity': result.get('severity', 'MEDIUM'),
}))
" "$cmd" 2>/dev/null)

    if [[ -z "$raw" ]]; then return; fi

    local what_happens scope reversible suggested_fix severity
    what_happens=$(python3 -c "import sys,json; d=json.loads(sys.argv[1]); print(d.get('what_happens',''))" "$raw" 2>/dev/null)
    scope=$(python3 -c "import sys,json; d=json.loads(sys.argv[1]); print(d.get('scope',''))" "$raw" 2>/dev/null)
    reversible=$(python3 -c "import sys,json; d=json.loads(sys.argv[1]); print('No' if not d.get('reversible',True) else 'Yes')" "$raw" 2>/dev/null)
    suggested_fix=$(python3 -c "import sys,json; d=json.loads(sys.argv[1]); print(d.get('suggested_fix',''))" "$raw" 2>/dev/null)
    severity=$(python3 -c "import sys,json; d=json.loads(sys.argv[1]); print(d.get('severity','MEDIUM'))" "$raw" 2>/dev/null)

    # Color scheme mirrors shellmate/ui/colors.py: caution=91 red, warning=93
    # yellow, suggestion/safe=92 green.
    local color="\e[93m"
    [[ "$severity" == "HIGH" || "$severity" == "CRITICAL" || "$severity" == "blocking" ]] && color="\e[91m"
    [[ "$severity" == "SAFE" || "$severity" == "LOW" ]] && color="\e[92m"

    local line1 line2 line3=""
    line1="${color}  → ${what_happens}\e[m"
    line2="${color}  → Reversible: ${reversible}  |  ${scope}\e[m"
    # A suggested fix is a suggestion -> green (92), not dim.
    [[ -n "$suggested_fix" ]] && line3="\e[92m  → Safe alt: ${suggested_fix}\e[m"

    # Gate HIGH/CRITICAL on second Enter
    if [[ "$severity" == "HIGH" || "$severity" == "CRITICAL" || "$severity" == "blocking" ]]; then
      _SHELLMATE_CONSEQUENCE_REQUIRE_CONFIRM="$cmd"
      line2="${line2}  \e[91m[Press Enter again to execute]\e[m"
    fi

    _shellmate_render_consequence "$line1" "$line2" "$line3"
  ) &
  _SHELLMATE_DEBOUNCE_PID=$!
}

sm_instant_check() {
  # Returns 0 if catastrophic match, 1 otherwise. Prints JSON to stdout.
  local cmd="$1"
  local sm_path
  sm_path=$(_shellmate_resolve_root)
  [[ -z "$sm_path" ]] && return 1

  local result
  result=$(python3 -c "
import sys, json
sys.path.insert(0, r'''$sm_path''')
from rules.catastrophic_matcher import match_catastrophic
cmd = sys.argv[1]
print(json.dumps(match_catastrophic(cmd)))
" "$cmd" 2>/dev/null)

  if [[ "$result" == *'"matched": true'* ]] || [[ "$result" == *'"matched":true'* ]]; then
    echo "$result"
    return 0
  fi
  echo "$result"
  return 1
}

_shellmate_cancel_debounce() {
  if [[ -n "$_SHELLMATE_DEBOUNCE_PID" ]]; then
    kill "$_SHELLMATE_DEBOUNCE_PID" 2>/dev/null || true
    _SHELLMATE_DEBOUNCE_PID=""
  fi
  python3 -c "
import sys
try:
    sys.path.insert(0, r'''$(_shellmate_resolve_root)''')
    from ipc.client import _debounced_client
    _debounced_client.cancel()
except Exception:
    pass
" 2>/dev/null || true
}

_shellmate_start_debounce() {
  # Pivot Phase 3 Task 3.3: use ipc.client.analyze_partial_debounced (300ms Timer)
  local cmd="$1"
  _shellmate_cancel_debounce

  (
    local sm_path
    sm_path=$(_shellmate_resolve_root)
    local annotation
    annotation=$(timeout 1.2 python3 -c "
import sys
import threading
sys.path.insert(0, r'''$sm_path''')
from ipc.client import analyze_partial_debounced

holder = {}
done = threading.Event()

def _cb(result):
    holder['r'] = result
    done.set()

analyze_partial_debounced(sys.argv[1], _cb)
if not done.wait(timeout=1.0):
    print('')
    raise SystemExit(0)

result = holder.get('r') or {}
ann = result.get('annotation') or result.get('consequence_preview') or ''
if isinstance(ann, dict):
    ann = ann.get('what_happens') or ann.get('summary') or ''
sev = str(result.get('severity', 'MEDIUM'))
if not ann:
    print('')
else:
    if sev in ('blocking', 'CRITICAL', 'HIGH'):
        icon = '⚠️'
    elif sev in ('SAFE', 'info', 'LOW'):
        icon = 'ℹ️'
    else:
        icon = 'ℹ️'
    print(f'{icon} {str(ann)[:80]}')
" "$cmd" 2>/dev/null)
    if [[ -n "$annotation" ]]; then
      # Replace placeholder in-place (do not append)
      _shellmate_render_annotation "$annotation"
    fi
  ) &
  _SHELLMATE_DEBOUNCE_PID=$!
}

# --- ble.sh widget: keystroke / pre-exec path ---

function ble/widget/shellmate-on-keystroke {
  local cmd="${READLINE_LINE}"

  # Skip empty / very short input
  if [[ ${#cmd} -lt 2 ]]; then
    _shellmate_clear_annotation
    return 0
  fi

  # Phase 1: Instant catastrophic check (target <5ms with cached rules)
  local instant_json
  if instant_json=$(sm_instant_check "$cmd"); then
    _SHELLMATE_NEEDS_CONFIRM="$cmd"
    _shellmate_cancel_debounce
    _shellmate_render_annotation "⚡ BLOCKING — Analyzing..."
    # Kick pipeline anyway so placeholder is replaced with full consequence
    _shellmate_start_debounce "$cmd"
  else
    _SHELLMATE_NEEDS_CONFIRM=""
    # Phase 2: debounce full pipeline for non-catastrophic
    _shellmate_start_debounce "$cmd"
  fi
}

function ble/widget/shellmate-check-catastrophic {
  # PRECMD_EXEC / PREEXEC path — keep confirm double-tap semantics
  local line="${READLINE_LINE}"
  local instant_json
  if instant_json=$(sm_instant_check "$line"); then
    _SHELLMATE_NEEDS_CONFIRM="$line"
    _shellmate_render_annotation "⚡ BLOCKING — Type again to confirm"
  else
    _SHELLMATE_NEEDS_CONFIRM=""
  fi
}

function ble/widget/shellmate-before-exec {
  # Gate 1: catastrophic double-tap
  if [[ -n "$_SHELLMATE_NEEDS_CONFIRM" ]]; then
    if [[ "$_SHELLMATE_LAST_DANGEROUS" != "$_SHELLMATE_NEEDS_CONFIRM" ]]; then
      _SHELLMATE_LAST_DANGEROUS="$_SHELLMATE_NEEDS_CONFIRM"
      echo -e "\e[91m⛔ Confirmation required. Type command again.\e[m"
      return 1
    fi
  fi

  # Gate 2: consequence preview requires second Enter for HIGH/CRITICAL
  local current_cmd="${READLINE_LINE}"
  if [[ -n "$_SHELLMATE_CONSEQUENCE_REQUIRE_CONFIRM" && \
        "$_SHELLMATE_CONSEQUENCE_REQUIRE_CONFIRM" == "$current_cmd" ]]; then
    if [[ "$_SHELLMATE_CONSEQUENCE_CONFIRM_ARMED" != "$current_cmd" ]]; then
      _SHELLMATE_CONSEQUENCE_CONFIRM_ARMED="$current_cmd"
      echo -e "\e[91m[Press Enter again to execute]\e[m"
      return 1
    fi
    _SHELLMATE_CONSEQUENCE_REQUIRE_CONFIRM=""
    _SHELLMATE_CONSEQUENCE_CONFIRM_ARMED=""
  else
    _SHELLMATE_CONSEQUENCE_CONFIRM_ARMED=""
  fi

  _SHELLMATE_LAST_DANGEROUS=""
  _SHELLMATE_TAB_STATE=""
  _SHELLMATE_TAB_CMD=""
  return 0
}

function ble/widget/shellmate-cancel-debounce {
  _shellmate_cancel_debounce
}

function ble/widget/shellmate-complete {
  local line="${READLINE_LINE}"

  # Second Tab: suggestion already shown → accept it and trigger consequence
  if [[ "$_SHELLMATE_TAB_STATE" == "suggested" && -n "$_SHELLMATE_TAB_CMD" ]]; then
    READLINE_LINE="$_SHELLMATE_TAB_CMD"
    READLINE_POINT=${#READLINE_LINE}
    _SHELLMATE_TAB_STATE="consequence_shown"
    _shellmate_clear_annotation
    _shellmate_show_consequence_async "$_SHELLMATE_TAB_CMD"
    return
  fi

  # Reset state on fresh Tab
  _SHELLMATE_TAB_STATE=""
  _SHELLMATE_TAB_CMD=""
  [[ ${#line} -lt 2 ]] && return

  local sm_path
  sm_path=$(_shellmate_resolve_root)
  [[ -z "$sm_path" ]] && return

  local completions
  completions=$(python3 -c "
import sys
sys.path.insert(0, r'''$sm_path''')
from completion.bash_adapter import get_completions
print('\n'.join(get_completions(sys.argv[1])))
" "$line" 2>/dev/null)

  if [[ -n "$completions" ]]; then
    local first
    first=$(echo "$completions" | head -n1)
    if [[ "$first" != "$line" ]]; then
      _SHELLMATE_TAB_CMD="$first"
      _SHELLMATE_TAB_STATE="suggested"
      local suffix="${first#$line}"
      if [[ -n "$suffix" ]] && type ble/canvas/put.draw &>/dev/null; then
        ble/canvas/put.draw "\e[90m${suffix}\e[m"
      elif [[ -n "$suffix" ]]; then
        printf '\e[90m%s\e[m' "$suffix" >/dev/tty
        printf '\e[%dD' "${#suffix}" >/dev/tty
      fi
    fi
  fi
}

# Bind hooks only when ble.sh is present
if type blehook &>/dev/null; then
  ble-bind -f __default__ 'ble/widget/shellmate-on-keystroke' 2>/dev/null || true
  ble-bind -f C-i 'ble/widget/shellmate-complete' 2>/dev/null || true   # Tab = C-i
  blehook PRECMD+=ble/widget/shellmate-check-catastrophic
  blehook PREEXEC+=ble/widget/shellmate-before-exec
  blehook PREEXEC+=ble/widget/shellmate-cancel-debounce
fi


