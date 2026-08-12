"""Inline annotation formatting for autocomplete mode."""

from __future__ import annotations

from typing import Any, Dict, Optional

# Emoji mappings for risk levels (short inline / Unix terminals)
RISK_ICONS = {
    "SAFE": "✅",
    "LOW": "ℹ️",
    "MEDIUM": "⚠️",
    "HIGH": "🔥",
    "CRITICAL": "⛔",
}

# ASCII-safe risk icons (Windows PS 5.1 / constrained consoles)
RISK_ICONS_ASCII = {
    "SAFE": "[OK]",
    "LOW": "[i]",
    "MEDIUM": "[!]",
    "HIGH": "[!!]",
    "CRITICAL": "[X]",
}

SEVERITY_ICONS = {
    "blocking": "🔥",
    "warning": "⚠️",
    "info": "ℹ️",
}

SEVERITY_ICONS_ASCII = {
    "blocking": "[X]",
    "warning": "[!]",
    "info": "[i]",
}

# Environment badges (emoji form for short annotations)
ENV_BADGES = {
    "production": "🏭",
    "staging": "🧪",
    "ci": "🤖",
    "development": "💻",
}

# Text badges used in consequence / pipeline annotations (cross-platform)
ENV_TEXT_BADGES = {
    "production": "[PROD]",
    "staging": "[STAGE]",
    "development": "[DEV]",
    "ci": "[CI]",
}

# Time context badges
TIME_BADGES = {
    "business_hours": "⏰",
    "after_hours": "🌙",
}


def format_annotation(
    risk_analysis: Dict[str, Any],
    environment_context: Optional[Dict[str, Any]] = None,
    max_chars: int = 30,
    *,
    ascii_safe: bool = False,
) -> str:
    """
    Format risk analysis into a short inline annotation.

    Returns e.g. "🔥 rewrites history 🏭⏰" (truncated to max_chars).
    """
    severity = risk_analysis.get("severity") or risk_analysis.get("risk", "MEDIUM")
    reason = risk_analysis.get("reason", "")

    icons = RISK_ICONS_ASCII if ascii_safe else RISK_ICONS
    parts = [icons.get(severity, "[!]" if ascii_safe else "⚠️")]

    if reason:
        short_reason = reason[:20] if len(reason) > 20 else reason
        parts.append(short_reason)

    if environment_context:
        env_type = environment_context.get("type")
        if ascii_safe:
            if env_type in ENV_TEXT_BADGES:
                parts.append(ENV_TEXT_BADGES[env_type])
        elif env_type in ENV_BADGES:
            parts.append(ENV_BADGES[env_type])

        time_ctx = environment_context.get("time", {}) or {}
        if time_ctx:
            if time_ctx.get("is_business_hours"):
                parts.append("BH" if ascii_safe else TIME_BADGES["business_hours"])
            elif time_ctx.get("after_hours") or time_ctx.get("is_business_hours") is False:
                parts.append("AH" if ascii_safe else TIME_BADGES["after_hours"])

    annotation = " ".join(parts)
    return annotation[:max_chars]


def format_consequence_annotation(
    consequence: Dict[str, Any],
    env_context: Optional[Dict[str, Any]] = None,
    chain_patterns: Optional[Dict[str, Any]] = None,
    risk: str = "MEDIUM",
    *,
    ascii_safe: bool = False,
) -> str:
    """Format annotation using structured consequence preview + badges."""
    env_context = env_context or {}
    chain_patterns = chain_patterns or {}

    severity = consequence.get("severity", "warning")
    icons = SEVERITY_ICONS_ASCII if ascii_safe else SEVERITY_ICONS
    icon = icons.get(severity)
    if not icon:
        risk_icons = RISK_ICONS_ASCII if ascii_safe else RISK_ICONS
        icon = risk_icons.get(risk, "[!]" if ascii_safe else "ℹ️")

    parts = [icon]

    env_type = env_context.get("type", "")
    if env_type in ENV_TEXT_BADGES:
        parts.append(ENV_TEXT_BADGES[env_type])

    if chain_patterns.get("broken", []):
        parts.append("[BROKEN]")
    elif chain_patterns.get("dangerous_escalations", []):
        parts.append("[ESCALATION]")

    what = consequence.get("what_happens", "") or ""
    if what:
        if len(what) > 50:
            what = what[:47] + "..."
        parts.append(what)

    if not consequence.get("reversible", True):
        parts.append("[IRREVERSIBLE]")

    return " ".join(parts) if len(parts) > 1 else ""


def format_legacy_pipeline_annotation(
    risk_result: Dict[str, Any],
    env_context: Optional[Dict[str, Any]] = None,
    chain_patterns: Optional[Dict[str, Any]] = None,
    *,
    ascii_safe: bool = False,
) -> str:
    """Format annotation from pipeline result without consequence_preview."""
    env_context = env_context or {}
    chain_patterns = chain_patterns or {}

    risk_analysis = risk_result.get("risk_analysis", {}) or {}
    msg = risk_analysis.get("reason", risk_result.get("message", "")) or ""
    risk = risk_result.get("risk", "MEDIUM")

    icons = RISK_ICONS_ASCII if ascii_safe else RISK_ICONS
    # Map HIGH->🔥 style: prefer risk-level icons; CRITICAL uses ⛔ in short form
    # Pipeline historically used 🔥 for CRITICAL — keep that for non-ascii.
    if not ascii_safe:
        pipeline_icons = {
            "CRITICAL": "🔥",
            "HIGH": "⚠️",
            "MEDIUM": "ℹ️",
            "LOW": "✓",
            "SAFE": "✓",
        }
        icon = pipeline_icons.get(risk, "ℹ️")
    else:
        icon = icons.get(risk, "[i]")

    parts = [icon]

    env_type = env_context.get("type", "")
    if env_type in ENV_TEXT_BADGES:
        parts.append(ENV_TEXT_BADGES[env_type])

    if chain_patterns.get("broken", []):
        parts.append("[BROKEN-WORKFLOW]")
    elif chain_patterns.get("dangerous_escalations", []):
        parts.append("[ESCALATION]")

    if msg:
        if len(msg) > 40:
            msg = msg[:37] + "..."
        parts.append(msg)

    return " ".join(parts) if len(parts) > 1 else ""


def format_pipeline_annotation(
    risk_result: Dict[str, Any],
    env_context: Optional[Dict[str, Any]] = None,
    chain_patterns: Optional[Dict[str, Any]] = None,
    *,
    ascii_safe: bool = False,
) -> str:
    """Prefer consequence_preview; fall back to legacy pipeline formatting."""
    consequence = risk_result.get("consequence_preview") or {}
    if consequence.get("what_happens"):
        return format_consequence_annotation(
            consequence,
            env_context,
            chain_patterns,
            risk_result.get("risk", "MEDIUM"),
            ascii_safe=ascii_safe,
        )
    return format_legacy_pipeline_annotation(
        risk_result, env_context, chain_patterns, ascii_safe=ascii_safe
    )


def format_cached_annotation(cached_result: Dict[str, Any], *, ascii_safe: bool = False) -> str:
    """Format a simple annotation from a cache hit payload."""
    msg = cached_result.get("explanation", "") or ""
    risk = cached_result.get("risk", "MEDIUM")
    if ascii_safe:
        icon = RISK_ICONS_ASCII.get(risk, "[i]")
    else:
        icons = {
            "CRITICAL": "🔥",
            "HIGH": "⚠️",
            "MEDIUM": "ℹ️",
            "LOW": "✓",
            "SAFE": "✓",
        }
        icon = icons.get(risk, "ℹ️")

    if len(msg) > 50:
        msg = msg[:47] + "..."
    return f"{icon} {msg}" if msg else ""
