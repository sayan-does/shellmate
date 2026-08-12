import os
import re
from typing import Any, Dict, List, Union


SECRET_PATTERNS = [
    (re.compile(r'(api[_-]?key|apikey|secret|token|password|passwd|auth[_-]?token)\s*[:=]\s*["\']?([a-zA-Z0-9_\-]{8,})["\']?', re.IGNORECASE), r'\1=****'),
    (re.compile(r'(gh[po]_[a-zA-Z0-9]{16,})'), r'****'),
    (re.compile(r'(sk-[a-zA-Z0-9]{16,})'), r'****'),
    (re.compile(r'(xox[baprs]-[a-zA-Z0-9\-]{20,})'), r'****'),
    (re.compile(r'(Bearer\s+[a-zA-Z0-9\._\-]{8,})', re.IGNORECASE), r'Bearer ****'),
    (re.compile(r'(Authorization:\s*Bearer\s+[a-zA-Z0-9\._\-]{8,})', re.IGNORECASE), r'Authorization: Bearer ****'),
    (re.compile(r'(Authorization:\s*[\'"]Bearer\s+[a-zA-Z0-9\._\-]{8,})', re.IGNORECASE), r"Authorization: 'Bearer ****"),
    (re.compile(r'(ssh-rsa\s+[a-zA-Z0-9\/\+\=]{20,})', re.IGNORECASE), r'ssh-rsa ****'),
    (re.compile(r'(ssh-ed25519\s+[a-zA-Z0-9\+\=]{20,})', re.IGNORECASE), r'ssh-ed25519 ****'),
    (re.compile(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'), r'****@****'),
]


def redact_secrets(text: str) -> str:
    if not isinstance(text, str):
        return text
    result = text
    for pattern, replacement in SECRET_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def redact_dict(data: Dict[str, Any], keys_to_redact: List[str] = None) -> Dict[str, Any]:
    if keys_to_redact is None:
        keys_to_redact = ['api_key', 'apikey', 'secret', 'token', 'password', 'passwd', 'auth_token', 'authorization']

    result = {}
    for key, value in data.items():
        if key.lower() in [k.lower() for k in keys_to_redact]:
            if isinstance(value, str) and value:
                result[key] = "****"
            else:
                result[key] = "****"
        elif isinstance(value, dict):
            result[key] = redact_dict(value, keys_to_redact)
        elif isinstance(value, list):
            result[key] = [redact_dict(item, keys_to_redact) if isinstance(item, dict) else redact_secrets(str(item)) if isinstance(item, str) else item for item in value]
        elif isinstance(value, str):
            result[key] = redact_secrets(value)
        else:
            result[key] = value
    return result


def sanitize_for_logging(data: Any) -> Any:
    if isinstance(data, dict):
        return redact_dict(data)
    elif isinstance(data, list):
        return [sanitize_for_logging(item) for item in data]
    elif isinstance(data, str):
        return redact_secrets(data)
    return data


def sanitize_prompt(prompt: str) -> str:
    return redact_secrets(prompt)


def sanitize_response(response: Any) -> Any:
    return sanitize_for_logging(response)