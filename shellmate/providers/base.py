from abc import ABC, abstractmethod
from typing import Optional


# Env var names users configure via `sm config`
PROVIDER_CREDENTIAL_KEYS = {
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


class AIProvider(ABC):
    @abstractmethod
    def analyze_risk(self, command: str, context: Optional[dict] = None) -> dict:
        pass

    @abstractmethod
    def generate_remediation(self, command: str, risk: dict, context: Optional[dict] = None) -> dict:
        pass

    @abstractmethod
    def is_available(self) -> bool:
        pass

    async def close(self):
        pass


class ProviderError(Exception):
    def __init__(self, message: str, provider: str, status_code: Optional[int] = None):
        self.provider = provider
        self.status_code = status_code
        super().__init__(message)


def credential_key_for(provider: str) -> str:
    return PROVIDER_CREDENTIAL_KEYS.get(provider, f"{provider.upper()}_API_KEY")


def _extract_status_code(exc: BaseException) -> Optional[int]:
    for attr in ("status_code", "status", "http_status"):
        val = getattr(exc, attr, None)
        if isinstance(val, int):
            return val
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error") or {}
        if isinstance(err, dict) and err.get("code") == "invalid_api_key":
            return 401
    text = str(exc)
    if "401" in text or "invalid_api_key" in text.lower() or "invalid api key" in text.lower():
        return 401
    if "403" in text:
        return 403
    if "429" in text:
        return 429
    return None


def format_provider_failure(provider: str, exc: BaseException, purpose: str = "AI analysis") -> str:
    """
    User-facing error that names which credential failed.

    Example: "AI analysis unavailable: GROQ_API_KEY is invalid (401). Run: sm config"
    """
    key = credential_key_for(provider)
    status = getattr(exc, "status_code", None) if isinstance(exc, ProviderError) else None
    if status is None:
        status = _extract_status_code(exc)
    raw = str(exc)

    if status == 401 or "invalid_api_key" in raw.lower() or "invalid api key" in raw.lower():
        return (
            f"{purpose} unavailable: {key} is invalid or unauthorized (401). "
            f"Update it with: sm config"
        )
    if status == 403:
        return f"{purpose} unavailable: {key} was rejected (403). Check permissions or run: sm config"
    if status == 429:
        return f"{purpose} unavailable: {key} hit rate limits (429). Retry later."
    if "not set" in raw.lower() or "environment variable" in raw.lower():
        return f"{purpose} unavailable: {key} is not set. Configure with: sm config"
    # Keep message short — avoid dumping provider JSON blobs
    brief = raw.split(" - ", 1)[0].strip()
    if len(brief) > 120:
        brief = brief[:117] + "..."
    return f"{purpose} unavailable ({key}): {brief}"


def wrap_provider_exception(exc: BaseException, provider: str) -> ProviderError:
    """Normalize SDK exceptions into ProviderError with status_code when possible."""
    if isinstance(exc, ProviderError):
        if exc.status_code is None:
            exc.status_code = _extract_status_code(exc)
        return exc
    return ProviderError(str(exc), provider, status_code=_extract_status_code(exc))
