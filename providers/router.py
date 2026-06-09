import os
from .base import ProviderError
from .groq_provider import GroqProvider
from .openrouter_provider import OpenRouterProvider
from config.credentials import load_env

_groq_provider = None
_openrouter_provider = None


def _inject_env():
    env = load_env()
    for key, value in env.items():
        if value and not os.environ.get(key):
            os.environ[key] = value


def get_groq_provider():
    global _groq_provider
    _inject_env()
    if _groq_provider is None:
        _groq_provider = GroqProvider()
    return _groq_provider


def get_openrouter_provider():
    global _openrouter_provider
    _inject_env()
    if _openrouter_provider is None:
        _openrouter_provider = OpenRouterProvider()
    return _openrouter_provider


async def analyze_risk(command, context=None):
    groq = get_groq_provider()
    try:
        return await groq.analyze_risk(command, context)
    except ProviderError as e:
        return {
            "risk": "MEDIUM",
            "confidence": 0.5,
            "reason": f"AI analysis unavailable: {e}",
            "provider": "fallback",
            "model": "deterministic",
        }


async def generate_remediation(command, risk, context=None):
    openrouter = get_openrouter_provider()
    try:
        return await openrouter.generate_remediation(command, risk, context)
    except ProviderError:
        groq_guide = await _remediation_from_command_guide(command, risk, context)
        if groq_guide:
            return groq_guide
        return {
            "explanation": risk.get("message", risk.get("reason", "Command may be dangerous.")),
            "alternatives": ["Review the command carefully before executing."],
            "provider": "fallback",
            "model": "deterministic",
        }


async def _remediation_from_command_guide(command, risk, context=None):
    groq = get_groq_provider()
    if not groq.is_available():
        return None
    try:
        from providers.groq_provider import _format_context
        from providers.groq_command_guide import generate_command_guide, alternatives_from_guide

        context_str = _format_context(context)
        reason = risk.get("reason", risk.get("message", ""))
        guide = await generate_command_guide(
            command,
            context=context_str,
            risk_reason=reason,
        )
        alternatives = alternatives_from_guide(guide)
        if not alternatives:
            return None
        return {
            "explanation": guide.get("when_to_use") or reason or "Usage suggestion based on your command.",
            "alternatives": alternatives,
            "provider": "fallback",
            "model": "groq_command_guide",
            "command_guide": guide,
        }
    except Exception:
        return None


async def close_providers():
    if _groq_provider is not None:
        await _groq_provider.close()
    if _openrouter_provider is not None:
        await _openrouter_provider.close()


def get_provider_status():
    groq = get_groq_provider()
    openrouter = get_openrouter_provider()

    return {
        "groq": {
            "configured": groq.is_available(),
            "status": "available" if groq.is_available() else "not_configured",
        },
        "openrouter": {
            "configured": openrouter.is_available(),
            "status": "available" if openrouter.is_available() else "not_configured",
            "fallback_models": openrouter.fallback_models,
        },
    }
