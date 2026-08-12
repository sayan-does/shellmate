import asyncio
import time
import logging
from shellmate.parser.command_parser import parse_command
from shellmate.sanitizer.typo_detector import sanitize
from shellmate.rules.engine import load_rules, match_rule
from shellmate.cache.semantic_cache import cache_lookup, cache_store
from shellmate.providers.router import analyze_risk, generate_remediation
from documentation.context7_client import retrieve_documentation_async, should_retrieve_documentation
from shellmate.config.defaults import get_default_config

logger = logging.getLogger("shellmate.pipeline")

_rules = None


def _get_rules():
    global _rules
    if _rules is None:
        _rules = load_rules()
    return _rules


async def run_pipeline_async(command):
    """Run analysis using the modern graph-based approach with FAISS caching."""
    try:
        from shellmate.orchestration.analysis_graph import get_analysis_graph
        graph = get_analysis_graph()
        return await graph.analyze_command(command)
    except (ImportError, Exception) as e:
        logger.error(f"Failed to run analysis graph: {e}")
        # Return minimal safe response
        return _build_response(
            risk="UNKNOWN",
            confidence=0.0,
            message="Analysis temporarily unavailable",
            explanation=str(e),
            stages={},
        )


# Legacy pipeline removed - using graph-based analysis with FAISS cache only

def _needs_context(command: str) -> bool:
    tokens = command.split()
    if not tokens:
        return False
    cmd = tokens[0].lower()
    if cmd in ("rm", "mv", "cp", "cat", "less", "nano", "vim", "vi", "code", "open"):
        return True
    for token in tokens:
        if token.startswith(("./", "../", "/", ".\\", "..\\")):
            return True
    if cmd in ("git", "docker", "docker-compose", "pip", "npm", "yarn", "pnpm"):
        return True
    return False


def run_pipeline(command):
    """Synchronous wrapper - deprecated, use run_pipeline_async."""
    logger.warning("run_pipeline() is deprecated, use run_pipeline_async()")
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
    context_used=None,
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

    if context_used:
        result["context_used"] = context_used
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
