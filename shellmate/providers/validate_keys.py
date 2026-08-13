"""Live API-key validation against provider endpoints."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional, Tuple

from shellmate.config.credentials import CREDENTIAL_KEYS

# credential env var -> (url, extra headers)
_VALIDATION_ENDPOINTS = {
    "GROQ_API_KEY": (
        "https://api.groq.com/openai/v1/models",
        {},
    ),
    "OPENROUTER_API_KEY": (
        "https://openrouter.ai/api/v1/models",
        {"HTTP-Referer": "https://github.com/sayan-does/shellmate", "X-Title": "ShellMate"},
    ),
    "XAI_API_KEY": (
        "https://api.x.ai/v1/models",
        {},
    ),
}

DEFAULT_TIMEOUT_SEC = 10


def validate_api_key(
    credential_key: str,
    api_key: str,
    *,
    timeout: float = DEFAULT_TIMEOUT_SEC,
) -> Tuple[bool, str]:
    """
    Ping the provider endpoint with the given API key.

    Returns (ok, message). Context7 and unknown keys without live endpoints
    return ok=True with a note that they were not live-checked.
    """
    if not api_key or not api_key.strip():
        return False, "API key is empty"

    meta = CREDENTIAL_KEYS.get(credential_key, {})
    if not meta.get("live_check", True) or credential_key not in _VALIDATION_ENDPOINTS:
        label = meta.get("label", credential_key)
        return True, f"{label} saved (not live-checked)"

    url, extra_headers = _VALIDATION_ENDPOINTS[credential_key]
    return _ping_models_endpoint(url, api_key.strip(), extra_headers, timeout=timeout)


def _ping_models_endpoint(
    url: str,
    api_key: str,
    extra_headers: dict,
    *,
    timeout: float,
) -> Tuple[bool, str]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        **extra_headers,
    }
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", None) or response.getcode()
            body = response.read(2048)
            if status and 200 <= int(status) < 300:
                # Soft sanity check: body should look like JSON list/object
                if body:
                    try:
                        json.loads(body.decode("utf-8", errors="replace"))
                    except json.JSONDecodeError:
                        pass
                return True, "Key is valid"
            return False, f"Unexpected response status {status}"
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return False, f"Key is invalid or unauthorized ({e.code})"
        if e.code == 429:
            return False, "Rate limited (429); try again later"
        return False, f"Provider returned HTTP {e.code}"
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        return False, f"Could not reach provider: {reason}"
    except TimeoutError:
        return False, "Could not reach provider: timed out"
    except Exception as e:
        return False, f"Could not reach provider: {e}"


def validate_stored_key(credential_key: str, api_key: Optional[str] = None) -> Tuple[bool, str]:
    """Validate a credential using an explicit key or the empty-string no-op."""
    return validate_api_key(credential_key, api_key or "")
