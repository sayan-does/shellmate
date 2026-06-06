import asyncio
import time
import logging
from parser.command_parser import parse_command
from sanitizer.typo_detector import sanitize
from rules.engine import load_rules, match_rule
from cache.semantic_cache import cache_lookup, cache_store
from providers.router import analyze_risk, generate_remediation
from documentation.context7_client import retrieve_documentation_async, should_retrieve_documentation
from config.defaults import get_default_config

logger = logging.getLogger("shellmate.pipeline")

_rules = None


def _get_rules():
    global _rules
    if _rules is None:
        _rules = load_rules()
    return _rules


async def run_pipeline_async(command):
    stages = {}
    start_time = time.time()

    sanitize_result = sanitize(command)
    stages["sanitizer"] = time.time() - start_time

    if sanitize_result.get("correction"):
        return _build_response(
            risk="LOW",
            confidence=1.0,
            message=sanitize_result["correction"],
            explanation=sanitize_result["trailing_char"].get("message", ""),
            alternatives=[sanitize_result["correction"]],
            stages=stages,
            early_exit="sanitizer",
        )

    if not sanitize_result["syntax"]["valid"]:
        return _build_response(
            risk="MEDIUM",
            confidence=0.9,
            message="Syntax error detected",
            explanation="; ".join(sanitize_result["syntax"]["errors"]),
            alternatives=["Fix the syntax and try again."],
            stages=stages,
            early_exit="sanitizer",
        )

    parse_start = time.time()
    parsed = parse_command(sanitize_result["normalized"])
    stages["parser"] = time.time() - parse_start

    rule_start = time.time()
    rules = _get_rules()
    rule_result = match_rule(sanitize_result["normalized"], rules)
    stages["rule_engine"] = time.time() - rule_start

    if rule_result["matched"]:
        if rule_result.get("confidence", 0) >= 0.9:
            cache_store(sanitize_result["normalized"], rule_result)
            return _build_response(
                risk=rule_result.get("severity", rule_result.get("risk", "MEDIUM")),
                confidence=rule_result.get("confidence", 0.9),
                message=rule_result.get("message", ""),
                explanation=rule_result.get("description", ""),
                rule_id=rule_result.get("rule_id"),
                category=rule_result.get("category"),
                stages=stages,
                early_exit="rule_engine",
            )

    cache_start = time.time()
    cached = cache_lookup(sanitize_result["normalized"])
    stages["cache"] = time.time() - cache_start

    if cached:
        return _build_response(
            risk=cached.get("risk", "MEDIUM"),
            confidence=cached.get("confidence", 0.9),
            message=cached.get("explanation", ""),
            explanation=cached.get("explanation", ""),
            alternatives=cached.get("alternatives", []),
            cached=True,
            stages=stages,
            early_exit="cache",
        )

    risk_start = time.time()
    risk_result = await analyze_risk(sanitize_result["normalized"])
    stages["risk_agent"] = time.time() - risk_start

    if risk_result.get("provider") != "fallback":
        cache_store(sanitize_result["normalized"], risk_result)

    doc_result = None
    if isinstance(parsed, dict):
        doc_start = time.time()
        if should_retrieve_documentation(parsed, risk_result):
            doc_result = await retrieve_documentation_async(parsed, risk_result)
        stages["documentation"] = time.time() - doc_start

    rem_start = time.time()
    remediation_result = await generate_remediation(
        sanitize_result["normalized"],
        risk_result,
        {"documentation": doc_result} if doc_result else None,
    )
    stages["remediation_agent"] = time.time() - rem_start

    risk_level = risk_result.get("risk", "MEDIUM")
    if rule_result["matched"]:
        rule_severity = rule_result.get("severity", rule_result.get("risk", "MEDIUM"))
        severity_order = {"SAFE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
        if severity_order.get(rule_severity, 0) > severity_order.get(risk_level, 0):
            risk_level = rule_severity

    return _build_response(
        risk=risk_level,
        confidence=risk_result.get("confidence", 0.5),
        message=risk_result.get("reason", remediation_result.get("explanation", "")),
        explanation=remediation_result.get("explanation", ""),
        alternatives=remediation_result.get("alternatives", []),
        documentation=doc_result,
        rule_match=rule_result if rule_result["matched"] else None,
        risk_analysis=risk_result,
        stages=stages,
    )


def run_pipeline(command):
    """Synchronous wrapper for backward compatibility."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    
    if loop and loop.is_running():
        # We're in an async context, run as a task
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, run_pipeline_async(command))
            return future.result()
    else:
        return asyncio.run(run_pipeline_async(command))


RISK_ORDER = {"SAFE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


def _build_response(
    risk="MEDIUM",
    confidence=0.5,
    message="",
    explanation="",
    alternatives=None,
    rule_id=None,
    category=None,
    cached=False,
    documentation=None,
    rule_match=None,
    risk_analysis=None,
    stages=None,
    early_exit=None,
):
    result = {
        "risk": risk,
        "confidence": confidence,
        "message": message,
        "explanation": explanation,
        "alternatives": alternatives or [],
        "cached": cached,
    }

    if rule_id:
        result["rule_id"] = rule_id
    if category:
        result["category"] = category
    if documentation:
        result["documentation"] = documentation
    if early_exit:
        result["early_exit"] = early_exit
    if stages:
        result["latency"] = {k: round(v * 1000, 2) for k, v in stages.items()}
        result["total_ms"] = round(sum(stages.values()) * 1000, 2)

    return result
