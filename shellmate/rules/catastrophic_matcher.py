import os
import re
import yaml
from shellmate.parser.command_parser import parse_command

CATASTROPHIC_FILE = os.path.join(os.path.dirname(__file__), "catastrophic.yaml")

# In-memory cache — YAML reload every keystroke blew past the <5–10ms budget (~11ms P99).
# Do NOT call getmtime on every match: on WSL /mnt/* mounts that alone can be 5–8ms.
_CACHED_RULES = None


def load_catastrophic_rules(force_reload: bool = False):
    """Load instant-match catastrophic rules (no API dependency).

    Rules are cached in-process. Pass force_reload=True after editing YAML.
    """
    global _CACHED_RULES

    if not force_reload and _CACHED_RULES is not None:
        return _CACHED_RULES

    if not os.path.exists(CATASTROPHIC_FILE):
        _CACHED_RULES = []
        return []

    with open(CATASTROPHIC_FILE, "r", encoding="utf-8") as f:
        rules = yaml.safe_load(f) or []
    _CACHED_RULES = [r for r in rules if r.get("instant")]
    return _CACHED_RULES


def match_catastrophic(command_string):
    """
    Instant match against catastrophic commands.
    Returns: {"matched": bool, "rule": dict, "message": str}
    """
    rules = load_catastrophic_rules()
    parsed = parse_command(command_string)
    
    for rule in rules:
        # Handle both single commands and pipelines
        if isinstance(parsed, dict) and parsed.get("pipeline"):
            # For pipelines, check all segments
            for segment_type, segment_data in parsed.get("segments", []):
                if segment_type == "command" and _match_rule(segment_data, command_string, rule):
                    return {
                        "matched": True,
                        "rule_id": rule["id"],
                        "category": rule["category"],
                        "severity": rule["severity"],
                        "message": rule["message"],
                        "confirm_required": rule.get("confirm_required", True),
                    }
        elif _match_rule(parsed, command_string, rule):
            return {
                "matched": True,
                "rule_id": rule["id"],
                "category": rule["category"],
                "severity": rule["severity"],
                "message": rule["message"],
                "confirm_required": rule.get("confirm_required", True),
            }
    
    return {"matched": False}

def _match_rule(parsed, command_string, rule):
    """Match single rule using existing engine logic"""
    if isinstance(parsed, dict):
        cmd_program = parsed.get("program")
    else:
        import shlex
        try:
            tokens = shlex.split(str(command_string))
            cmd_program = tokens[0] if tokens else None
        except ValueError:
            return False
    
    # Check program match (handle variants like mkfs.ext4 matching mkfs)
    rule_program = rule.get("program")
    if cmd_program != rule_program:
        # Try prefix match for programs like mkfs.ext4
        if not (cmd_program and cmd_program.startswith(rule_program + ".")):
            return False
    
    # Check subcommand (for git push, git reset, docker rm, etc.)
    expected_subcommand = rule.get("subcommand")
    if expected_subcommand:
        if isinstance(parsed, dict):
            actual_subcommand = parsed.get("subcommand")
            if actual_subcommand != expected_subcommand:
                return False
        else:
            import shlex
            try:
                tokens = shlex.split(command_string)
                if len(tokens) < 2 or tokens[1] != expected_subcommand:
                    return False
            except ValueError:
                return False
    
    # Check flags
    expected_flags = rule.get("flags", [])
    if expected_flags:
        cmd_flags = parsed.get("flags", []) if isinstance(parsed, dict) else []
        flag_values = {f["flag"] for f in cmd_flags} if cmd_flags else set()
        
        # Check if any expected flag is present (handle combined flags like -rf)
        found_flag = False
        for expected_flag in expected_flags:
            # Direct match
            if expected_flag in flag_values or expected_flag in command_string:
                found_flag = True
                break
            # Check for combined flags (e.g., "-rf" contains both "-r" and "-f")
            if expected_flag.startswith("-") and not expected_flag.startswith("--"):
                # Single dash flags can be combined
                expected_letters = set(expected_flag.lstrip("-"))
                for actual_flag in flag_values:
                    if actual_flag.startswith("-") and not actual_flag.startswith("--"):
                        actual_letters = set(actual_flag.lstrip("-"))
                        if expected_letters.issubset(actual_letters):
                            found_flag = True
                            break
                if found_flag:
                    break
        
        if not found_flag:
            return False
    
    # Check arguments
    expected_args = rule.get("arguments", [])
    if expected_args:
        cmd_args = parsed.get("arguments", []) if isinstance(parsed, dict) else []
        arg_str = " ".join(cmd_args) if cmd_args else ""
        
        # Try matching against arguments first, then full command (for pipes)
        found_arg = False
        for pat in expected_args:
            # Try matching individual arguments for patterns like ^/$
            if arg_str and re.search(pat, arg_str):
                found_arg = True
                break
            # Also check each argument individually
            for arg in cmd_args:
                if re.search(pat, arg):
                    found_arg = True
                    break
            if found_arg:
                break
            # Fallback: check full command string for patterns like pipes
            if re.search(pat, command_string):
                found_arg = True
                break
        
        if not found_arg:
            return False
    
    return True


if __name__ == "__main__":
    import json
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    print(json.dumps(match_catastrophic(cmd)))
