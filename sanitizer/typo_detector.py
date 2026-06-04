import re
import shlex

TRAILING_CHARS = re.compile(r"[,;.]$")
MULTI_SPACE = re.compile(r"\s{2,}")


def normalize_whitespace(command):
    return MULTI_SPACE.sub(" ", command.strip())


def detect_trailing_char(command):
    stripped = command.strip()
    match = TRAILING_CHARS.search(stripped)
    if match:
        trailing = match.group()
        corrected = stripped.rstrip(",. ;")
        return {
            "detected": True,
            "trailing": trailing,
            "original": command,
            "suggestion": corrected,
            "message": f"Did you mean: {corrected}",
        }
    return {"detected": False}


def detect_duplicate_flags(tokens):
    seen = []
    duplicates = []
    for token in tokens:
        if token.startswith("-"):
            if token in seen:
                duplicates.append(token)
            else:
                seen.append(token)
    if duplicates:
        return {
            "detected": True,
            "duplicates": duplicates,
            "message": f"Duplicate flag(s) detected: {', '.join(duplicates)}",
        }
    return {"detected": False}


def validate_syntax(command):
    in_single = False
    in_double = False
    i = 0
    char_count = len(command)

    errors = []

    while i < char_count:
        c = command[i]
        if c == "\\" and i + 1 < char_count:
            i += 2
            continue
        if c == "'" and not in_double:
            in_single = not in_single
        elif c == '"' and not in_single:
            in_double = not in_double
        i += 1

    if in_single:
        errors.append("Unmatched single quote")
    if in_double:
        errors.append("Unmatched double quote")

    if not errors:
        try:
            shlex.split(command)
        except ValueError as e:
            errors.append(str(e))

    token_pattern = re.findall(r'(?:^|\s)([<>]{2,3})(?:\s|$)', command)
    for token in token_pattern:
        if token not in (">", "<", ">>", "<<", ">&", "<>", "2>", "2>>"):
            if token not in errors:
                errors.append(f"Invalid redirect operator: {token}")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
    }


def sanitize(command):
    result = {
        "original": command,
        "normalized": normalize_whitespace(command),
        "trailing_char": None,
        "duplicate_flags": None,
        "syntax": None,
        "correction": None,
    }

    trailing = detect_trailing_char(result["normalized"])
    if trailing["detected"]:
        result["trailing_char"] = trailing
        result["correction"] = trailing["suggestion"]

    try:
        tokens = shlex.split(result["normalized"])
        dup = detect_duplicate_flags(tokens)
        if dup["detected"]:
            result["duplicate_flags"] = dup
    except ValueError:
        tokens = result["normalized"].split()

    syntax = validate_syntax(result["normalized"])
    result["syntax"] = syntax

    return result
