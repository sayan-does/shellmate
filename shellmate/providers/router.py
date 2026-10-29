import os
from .base import ProviderError, format_provider_failure, wrap_provider_exception, credential_key_for
from .groq_provider import GroqProvider
from .openrouter_provider import OpenRouterProvider
from .xai_provider import XaiProvider
from shellmate.config.credentials import load_env

_groq_provider = None
_openrouter_provider = None
_xai_provider = None

_RISK_CAPABLE = ("groq", "xai")
_REMEDIATION_CAPABLE = ("openrouter", "xai")


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


def get_xai_provider():
    global _xai_provider
    _inject_env()
    if _xai_provider is None:
        _xai_provider = XaiProvider()
    return _xai_provider


def _provider_instance(name: str):
    if name == "groq":
        return get_groq_provider()
    if name == "openrouter":
        return get_openrouter_provider()
    if name == "xai":
        return get_xai_provider()
    return None


def _role_primary(role: str, default: str) -> str:
    try:
        from shellmate.config import get_config
        cfg = get_config()
        primary = (cfg.get("providers") or {}).get(role, {}).get("primary") or default
        return str(primary).lower()
    except Exception:
        return default


def _apply_role_model(provider, role: str) -> None:
    try:
        from shellmate.config import get_config
        model = (get_config().get("providers") or {}).get(role, {}).get("model")
        if not model:
            return
        if hasattr(provider, "model"):
            provider.model = model
        elif hasattr(provider, "primary_model"):
            provider.primary_model = model
    except Exception:
        pass


def _risk_provider_order() -> list:
    primary = _role_primary("risk_analysis", "groq")
    order = []
    if primary in _RISK_CAPABLE:
        order.append(primary)
    for name in _RISK_CAPABLE:
        if name not in order:
            order.append(name)
    return order


def _remediation_provider_order() -> list:
    primary = _role_primary("remediation", "openrouter")
    order = []
    if primary in _REMEDIATION_CAPABLE:
        order.append(primary)
    for name in _REMEDIATION_CAPABLE:
        if name not in order:
            order.append(name)
    return order


async def check_risk_model_reachable():
    """Best-effort startup check: is the configured risk model actually reachable?

    Returns a warning dict when a key IS configured but the resolved risk model
    is not in the account's accessible-model list — the case where AI analysis
    would silently degrade to a static MEDIUM fallback. Returns None when there
    is nothing to warn about (no key, model reachable, or the check is
    inconclusive). Never raises and never blocks daemon readiness.
    """
    try:
        order = _risk_provider_order()
        name = order[0] if order else "groq"
        provider = _provider_instance(name)
        # No key configured -> AI tier is intentionally offline, not a misconfig.
        if provider is None or not provider.is_available():
            return None
        _apply_role_model(provider, "risk_analysis")
        model = getattr(provider, "model", None)
        lister = getattr(provider, "list_available_models", None)
        if not model or lister is None:
            return None
        available = await lister()
        # Could not determine (network/API error) -> stay silent, don't cry wolf.
        if not available or model in available:
            return None
        return {
            "provider": name,
            "model": model,
            "credential": credential_key_for(name),
            "accessible_models": sorted(available)[:12],
            "message": (
                f"Configured {name} risk model '{model}' is NOT accessible with your "
                f"{credential_key_for(name)}. AI risk analysis will silently fall back to a "
                f"static MEDIUM rating. Set providers.risk_analysis.model in config.yaml to a "
                f"model your key can access (see `sm status` for the accessible list)."
            ),
        }
    except Exception:
        return None


async def analyze_risk(command, context=None):
    last_err = None
    last_provider = "groq"

    for name in _risk_provider_order():
        provider = _provider_instance(name)
        if provider is None or not provider.is_available():
            continue
        last_provider = name
        try:
            _apply_role_model(provider, "risk_analysis")
            return await provider.analyze_risk(command, context)
        except ProviderError as e:
            last_err = wrap_provider_exception(e, name)
            continue
        except NotImplementedError:
            continue

    err = last_err or ProviderError("No risk analysis provider available", last_provider)
    return {
        "risk": "MEDIUM",
        "confidence": 0.5,
        "reason": format_provider_failure(last_provider, err, purpose="AI analysis"),
        "provider": "fallback",
        "model": "deterministic",
        "failed_provider": last_provider,
        "failed_credential": credential_key_for(last_provider),
    }


async def generate_remediation(command, risk, context=None):
    last_err = None
    last_provider = "openrouter"

    for name in _remediation_provider_order():
        provider = _provider_instance(name)
        if provider is None or not provider.is_available():
            continue
        last_provider = name
        try:
            _apply_role_model(provider, "remediation")
            return await provider.generate_remediation(command, risk, context)
        except ProviderError as e:
            last_err = wrap_provider_exception(e, name)
            continue
        except NotImplementedError:
            continue

    err = last_err or ProviderError("No remediation provider available", last_provider)
    groq_guide = await _remediation_from_command_guide(command, risk, context)
    if groq_guide:
        groq_guide["openrouter_error"] = format_provider_failure(
            last_provider, err, purpose="Remediation"
        )
        return groq_guide
    return {
        "explanation": format_provider_failure(last_provider, err, purpose="Remediation")
        + " "
        + risk.get("message", risk.get("reason", "Command may be dangerous.")),
        "alternatives": ["Review the command carefully before executing."],
        "provider": "fallback",
        "model": "deterministic",
        "failed_provider": last_provider,
        "failed_credential": credential_key_for(last_provider),
    }


async def _remediation_from_command_guide(command, risk, context=None):
    groq = get_groq_provider()
    if not groq.is_available():
        return None
    try:
        from shellmate.providers.groq_provider import _format_context
        from shellmate.providers.groq_command_guide import generate_command_guide, alternatives_from_guide

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
    if _xai_provider is not None:
        await _xai_provider.close()


def get_provider_status():
    groq = get_groq_provider()
    openrouter = get_openrouter_provider()
    xai = get_xai_provider()

    return {
        "groq": {
            "configured": groq.is_available(),
            "status": "available" if groq.is_available() else "not_configured",
            "credential": "GROQ_API_KEY",
        },
        "openrouter": {
            "configured": openrouter.is_available(),
            "status": "available" if openrouter.is_available() else "not_configured",
            "credential": "OPENROUTER_API_KEY",
            "fallback_models": openrouter.fallback_models,
        },
        "xai": {
            "configured": xai.is_available(),
            "status": "available" if xai.is_available() else "not_configured",
            "credential": "XAI_API_KEY",
            "model": xai.model,
        },
    }
