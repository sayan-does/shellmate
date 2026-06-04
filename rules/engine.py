import os
import re
import yaml
from parser.command_parser import parse_command

RULES_DIR = os.path.join(os.path.dirname(__file__), "definitions")


def load_rules():
    rules = []
    if not os.path.isdir(RULES_DIR):
        return rules

    for filename in sorted(os.listdir(RULES_DIR)):
        if filename.endswith((".yaml", ".yml")):
            filepath = os.path.join(RULES_DIR, filename)
            try:
                with open(filepath, "r") as f:
                    file_rules = yaml.safe_load(f)
                    if file_rules:
                        for rule in file_rules:
                            rule["source"] = filename
                        rules.extend(file_rules)
            except yaml.YAMLError as e:
                raise ValueError(f"Error parsing {filename}: {e}")

    return rules


def match_rule(command_string, rules):
    parsed = parse_command(command_string)

    for rule in rules:
        if rule.get("pipeline") and "|" in command_string:
            result = _match_pipeline_rule_on_string(command_string, rule)
        else:
            result = _match_single_rule(parsed, rule)
        if result["matched"]:
            return result

    return {"matched": False, "risk": None, "confidence": 0.0}


def _match_pipeline_rule_on_string(command_string, rule):
    pattern = rule.get("pattern", [])
    parts = [p.strip() for p in command_string.split("|")]
    if len(parts) != len([p for p in pattern if not p.get("operator")]):
        return {"matched": False}

    cmd_index = 0
    for pattern_item in pattern:
        if pattern_item.get("operator"):
            continue
        part = parts[cmd_index]
        expected_program = pattern_item.get("program")
        if expected_program and not part.startswith(expected_program):
            return {"matched": False}
        cmd_index += 1

    return _build_match_result(rule)


def _match_single_rule(parsed_command, rule):
    if isinstance(parsed_command, dict) and parsed_command.get("pipeline"):
        segments = parsed_command.get("segments", [])
        for seg_type, seg_data in segments:
            if seg_type == "command":
                result = _match_single_command_rule(seg_data, rule)
                if result["matched"]:
                    return result
        return {"matched": False}

    return _match_single_command_rule(parsed_command, rule)


def _match_pipeline_rule(parsed_command, rule):
    pattern = rule.get("pattern", [])

    if isinstance(parsed_command, dict) and parsed_command.get("pipeline"):
        segments = parsed_command.get("segments", [])
        if len(segments) != len(pattern):
            return {"matched": False}

        for (seg_type, seg_data), pattern_item in zip(segments, pattern):
            if seg_type == "command":
                expected_program = pattern_item.get("program")
                if isinstance(seg_data, dict):
                    if seg_data.get("program") != expected_program:
                        return {"matched": False}
            elif seg_type == "pipe":
                expected_op = pattern_item.get("operator")
                if seg_data != expected_op:
                    return {"matched": False}

        return _build_match_result(rule)

    if isinstance(parsed_command, dict):
        cmd_str = " ".join(filter(None, [
            parsed_command.get("program", ""),
            *([parsed_command.get("subcommand", "")] if parsed_command.get("subcommand") else []),
            *([str(f) for f in parsed_command.get("flags", [])] if isinstance(parsed_command.get("flags"), list) else []),
            *parsed_command.get("arguments", []),
        ]))
    else:
        cmd_str = str(parsed_command)

    if "|" not in cmd_str:
        return {"matched": False}

    parts = [p.strip() for p in cmd_str.split("|")]
    if len(parts) != len(pattern):
        return {"matched": False}

    for part, pattern_item in zip(parts, pattern):
        if pattern_item.get("operator"):
            continue
        expected_program = pattern_item.get("program")
        if expected_program and not part.startswith(expected_program):
            return {"matched": False}

    return _build_match_result(rule)


def _match_single_command_rule(parsed_command, rule):
    if isinstance(parsed_command, dict):
        cmd_program = parsed_command.get("program")
    else:
        try:
            import shlex
            tokens = shlex.split(str(parsed_command))
            cmd_program = tokens[0] if tokens else None
        except ValueError:
            return {"matched": False}

    expected_program = rule.get("program")
    if cmd_program != expected_program:
        if expected_program and cmd_program:
            if not cmd_program.startswith(expected_program + "."):
                return {"matched": False}
        else:
            return {"matched": False}

    expected_flags = rule.get("flags", [])
    if expected_flags:
        if isinstance(parsed_command, dict):
            cmd_flags = parsed_command.get("flags", [])
            flag_values = {f["flag"] for f in cmd_flags} if isinstance(cmd_flags, list) else set()
            if not any(f in flag_values for f in expected_flags):
                return {"matched": False}
        else:
            cmd_str = str(parsed_command)
            if not any(f in cmd_str for f in expected_flags):
                return {"matched": False}

    expected_args = rule.get("arguments", [])
    if expected_args:
        if isinstance(parsed_command, dict):
            cmd_args = parsed_command.get("arguments", [])
            arg_strings = " ".join(cmd_args) if isinstance(cmd_args, list) else str(cmd_args)
        else:
            arg_strings = str(parsed_command)

        if not any(re.search(pat, arg_strings) for pat in expected_args):
            return {"matched": False}

    return _build_match_result(rule)


def _build_match_result(rule):
    return {
        "matched": True,
        "rule_id": rule.get("id"),
        "category": rule.get("category"),
        "severity": rule.get("severity", "MEDIUM"),
        "risk": rule.get("severity", "MEDIUM"),
        "confidence": rule.get("confidence", 0.8),
        "description": rule.get("message", rule.get("description", "")),
        "message": rule.get("message", rule.get("description", "")),
        "rule": rule,
    }


def validate_rules():
    rules = load_rules()
    rule_ids = {}
    for rule in rules:
        rid = rule.get("id")
        if not rid:
            raise ValueError(f"Rule missing 'id' in {rule.get('source', 'unknown')}")
        if rid in rule_ids:
            raise ValueError(f"Duplicate rule ID: {rid}")
        rule_ids[rid] = True
        if not rule.get("category"):
            raise ValueError(f"Rule {rid} missing 'category'")
        if not rule.get("severity"):
            raise ValueError(f"Rule {rid} missing 'severity'")
        if not rule.get("program") and not rule.get("pipeline"):
            raise ValueError(f"Rule {rid} missing 'program' or 'pipeline'")

    return rules
