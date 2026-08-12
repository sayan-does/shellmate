import asyncio
import logging
import os
import time
from typing import Any, Dict, Optional, List
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from shellmate.orchestration.state import AnalysisState
from shellmate.parser.command_parser import parse_command
from shellmate.sanitizer.typo_detector import sanitize
from shellmate.rules.engine import load_rules, match_rule
from shellmate.cache.semantic_cache import cache_lookup, cache_store
from shellmate.agents.watcher import get_watcher_agent
from shellmate.agents.librarian import get_librarian_agent
from shellmate.agents.repomix_backend import get_repomix_backend
from shellmate.providers.router import analyze_risk, generate_remediation
from shellmate.providers.groq_provider import _format_context
from shellmate.providers.groq_supervisor import route_command, SupervisorError
from shellmate.providers.groq_command_guide import generate_command_guide, CommandGuideError, alternatives_from_guide
from shellmate.config.defaults import get_default_config
from shellmate.config.secrets import redact_dict

logger = logging.getLogger("shellmate.orchestration")

CONTEXT_TIMEOUT = 0.5

_rules = None


def _get_rules():
    global _rules
    if _rules is None:
        _rules = load_rules()
    return _rules


def _merge_stages(state: AnalysisState, key: str, elapsed: float) -> dict:
    existing = state.get("stages", {})
    merged = dict(existing)
    merged[key] = elapsed
    return merged


def sanitize_node(state: AnalysisState) -> dict:
    start = time.monotonic()
    command = state["command"]
    sanitized = sanitize(command)
    elapsed = (time.monotonic() - start) * 1000
    return {
        "sanitized": sanitized,
        "stages": _merge_stages(state, "sanitizer", elapsed),
        "errors": [],
        "agent_latency": {"watcher": 0, "librarian": 0},
    }


def parse_node(state: AnalysisState) -> dict:
    start = time.monotonic()
    sanitized = state.get("sanitized", {})
    normalized = sanitized.get("normalized", state["command"])
    parsed = parse_command(normalized)
    elapsed = (time.monotonic() - start) * 1000
    return {
        "parsed": parsed if isinstance(parsed, dict) else {},
        "stages": _merge_stages(state, "parser", elapsed),
    }


async def command_chain_node(state: AnalysisState) -> dict:
    """Query command chain history and detect patterns."""
    start = time.monotonic()
    current_command = state.get("command", "")
    
    try:
        result = await _query_command_chain_agent(current_command)
        elapsed = (time.monotonic() - start) * 1000
        
        return {
            "command_chain": result.get("recent_commands", []),
            "chain_patterns": result.get("patterns", {}),
            "stages": _merge_stages(state, "command_chain", elapsed),
        }
    except Exception as e:
        logger.warning(f"Command chain node error: {e}")
        elapsed = (time.monotonic() - start) * 1000
        return {
            "command_chain": [],
            "chain_patterns": {},
            "stages": _merge_stages(state, "command_chain", elapsed),
        }


async def query_node(state: AnalysisState) -> dict:
    """Process user queries if present."""
    queries = state.get("user_queries", [])
    
    if not queries:
        return {}  # No queries to process
    
    start = time.monotonic()
    
    try:
        from shellmate.agents.query import get_query_agent
        
        query_agent = get_query_agent()
        
        # Process all queries with timeout
        response = await asyncio.wait_for(
            query_agent.send_request(
                "process_queries",
                data={"queries": queries, "state": state},
                timeout=0.1  # 100ms timeout per config
            ),
            timeout=0.15  # Total timeout with buffer
        )
        
        responses = response.data.get("responses", {}) if response and response.status == "ok" else {}
        elapsed = (time.monotonic() - start) * 1000
        
        return {
            "query_responses": responses,
            "stages": _merge_stages(state, "query", elapsed),
        }
    except asyncio.TimeoutError:
        responses = {q: "Unable to answer (timeout)" for q in queries}
        elapsed = (time.monotonic() - start) * 1000
        return {
            "query_responses": responses,
            "stages": _merge_stages(state, "query", elapsed),
        }
    except Exception as e:
        logger.warning(f"Query node error: {e}")
        elapsed = (time.monotonic() - start) * 1000
        return {
            "query_responses": {},
            "stages": _merge_stages(state, "query", elapsed),
        }


def rules_node(state: AnalysisState) -> dict:
    start = time.monotonic()
    sanitized = state.get("sanitized", {})
    normalized = sanitized.get("normalized", state["command"])
    rules = _get_rules()
    rule_result = match_rule(normalized, rules)
    elapsed = (time.monotonic() - start) * 1000
    return {
        "rule_match": rule_result if rule_result["matched"] else None,
        "stages": _merge_stages(state, "rule_engine", elapsed),
    }


def cache_node(state: AnalysisState) -> dict:
    start = time.monotonic()
    sanitized = state.get("sanitized", {})
    normalized = sanitized.get("normalized", state["command"])
    cached = cache_lookup(normalized)
    elapsed = (time.monotonic() - start) * 1000
    return {
        "cached": cached,
        "stages": _merge_stages(state, "cache", elapsed),
    }


def early_exit_router(state: AnalysisState) -> str:
    sanitized = state.get("sanitized", {})
    if sanitized:
        if sanitized.get("correction"):
            return "early_exit_sanitizer"
        if not sanitized.get("syntax", {}).get("valid", True):
            return "early_exit_sanitizer"
    rule_match = state.get("rule_match")
    if rule_match and rule_match.get("confidence", 0) >= 0.9:
        return "early_exit_rule"
    cached = state.get("cached")
    if cached:
        return "early_exit_cache"
    return "needs_context"


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


async def supervisor_node(state: AnalysisState) -> dict:
    start = time.monotonic()
    command = state["command"]
    decision = {"run_watcher": False, "run_librarian": False, "command": command}

    if os.environ.get("GROQ_API_KEY"):
        cfg = get_default_config()
        sup = cfg.get("supervisor", {})
        try:
            routed = await route_command(
                command,
                model=sup.get("model"),
                timeout_ms=sup.get("timeout_ms", 500),
            )
            decision["run_watcher"] = routed["run_watcher"]
            decision["run_librarian"] = routed["run_librarian"]
        except SupervisorError as e:
            elapsed = (time.monotonic() - start) * 1000
            return {
                "needs_context": False,
                "supervisor_decision": decision,
                "supervisor_fallback": True,
                "supervisor_warning": "Context skipped: supervisor unavailable",
                "stages": _merge_stages(state, "supervisor", elapsed),
                "errors": [str(e)],
            }
    else:
        needs = _needs_context(command)
        decision["run_watcher"] = needs
        decision["run_librarian"] = needs

    needs_context = decision["run_watcher"] or decision["run_librarian"]
    elapsed = (time.monotonic() - start) * 1000
    return {
        "needs_context": needs_context,
        "supervisor_decision": decision,
        "stages": _merge_stages(state, "supervisor", elapsed),
    }


def supervisor_router(state: AnalysisState) -> str:
    if state.get("supervisor_fallback"):
        return "skip_context"
    if state.get("needs_context"):
        return "context_worker"
    return "skip_context"


async def env_context_node(state: AnalysisState) -> dict:
    """
    Lightweight environment lookup for autocomplete / skip_context path.

    Watcher and Librarian are skipped; EnvironmentAgent is still queried so
    production badges and blast-radius context remain available (<50ms cached).
    """
    start = time.monotonic()
    result = await _query_environment_agent(state.get("overrides", {}) or {})
    env_context = {k: v for k, v in (result or {}).items() if k != "_latency_ms"}
    elapsed = (time.monotonic() - start) * 1000
    agent_latency = dict(state.get("agent_latency") or {})
    agent_latency["environment"] = (result or {}).get("_latency_ms", round(elapsed, 1))
    return {
        "environment_context": env_context,
        "agent_latency": agent_latency,
        "stages": _merge_stages(state, "environment", elapsed),
    }


def _query_router(state: AnalysisState) -> str:
    """Route to query_node if queries present, else END."""
    if state.get("user_queries"):
        return "query"
    return "end"


async def context_worker_node(state: AnalysisState) -> dict:
    start = time.monotonic()
    command = state["command"]
    agent_latency = {"watcher": 0, "librarian": 0, "environment": 0}

    decision = state.get("supervisor_decision") or {}
    run_watcher = decision.get("run_watcher", state.get("needs_context", True))
    run_librarian = decision.get("run_librarian", state.get("needs_context", True))

    watcher_context = {}
    librarian_context = {"matches": []}
    environment_context = {}
    partial = False

    tasks = {}
    if run_watcher:
        tasks["watcher"] = asyncio.create_task(_query_watcher(command))
    if run_librarian:
        tasks["librarian"] = asyncio.create_task(_query_librarian(command))
        tasks["repomix"] = asyncio.create_task(_query_repomix(command))
    
    # NEW: Add EnvironmentAgent
    tasks["environment"] = asyncio.create_task(
        _query_environment_agent(state.get("overrides", {}))
    )

    if not tasks:
        elapsed = (time.monotonic() - start) * 1000
        return {
            "watcher_context": watcher_context,
            "librarian_context": librarian_context,
            "environment_context": environment_context,
            "merged_context": {"watcher": watcher_context, "librarian": librarian_context, "partial": False},
            "agent_latency": agent_latency,
            "stages": _merge_stages(state, "context", elapsed),
        }

    done, pending = await asyncio.wait(
        tasks.values(),
        timeout=CONTEXT_TIMEOUT,
        return_when=asyncio.ALL_COMPLETED,
    )

    for name, task in tasks.items():
        if task in pending:
            task.cancel()
            partial = True
            continue
        try:
            result = await task
            if name == "watcher":
                watcher_context = result or {}
                agent_latency["watcher"] = result.get("_latency_ms", 0) if result else 0
            elif name == "librarian":
                librarian_context = result if result else {"matches": []}
                agent_latency["librarian"] = result.get("_latency_ms", 0) if result else 0
            elif name == "repomix":
                if result and result.get("matches"):
                    existing = librarian_context.get("matches", [])
                    existing.extend(result["matches"])
                    librarian_context["matches"] = existing
            elif name == "environment":
                environment_context = result or {}
                agent_latency["environment"] = result.get("_latency_ms", 0) if result else 0
        except asyncio.CancelledError:
            partial = True
        except Exception as e:
            logger.warning(f"Context worker {name} error: {e}")
            partial = True

    elapsed = (time.monotonic() - start) * 1000
    return {
        "watcher_context": watcher_context,
        "librarian_context": librarian_context,
        "environment_context": environment_context,
        "merged_context": {"watcher": watcher_context, "librarian": librarian_context, "partial": partial},
        "agent_latency": agent_latency,
        "stages": _merge_stages(state, "context", elapsed),
    }


async def _query_watcher(command: str) -> dict:
    start = time.monotonic()
    try:
        watcher = get_watcher_agent()
        if watcher.status.value != "ready":
            return {}
        response = await watcher.send_request("get_context", timeout=CONTEXT_TIMEOUT)
        elapsed = (time.monotonic() - start) * 1000
        if response.status == "ok":
            result = redact_dict(response.data)
            result["_latency_ms"] = round(elapsed, 1)
            return result
        return {}
    except Exception as e:
        logger.debug(f"Watcher query failed: {e}")
        return {}


async def _query_librarian(command: str) -> dict:
    start = time.monotonic()
    try:
        librarian = get_librarian_agent()
        if not librarian.is_indexed:
            return {"matches": []}
        response = await librarian.send_request("search", data={"query": command}, timeout=CONTEXT_TIMEOUT)
        elapsed = (time.monotonic() - start) * 1000
        if response.status == "ok":
            data = response.data
            data["_latency_ms"] = round(elapsed, 1)
            return data
        return {"matches": []}
    except Exception as e:
        logger.debug(f"Librarian query failed: {e}")
        return {"matches": []}


async def _query_repomix(command: str) -> dict:
    try:
        backend = get_repomix_backend()
        return await backend.search(command)
    except Exception as e:
        logger.debug(f"Repomix query failed: {e}")
        return {"matches": []}


async def _query_environment_agent(overrides: dict) -> dict:
    """Query EnvironmentAgent for context."""
    start = time.monotonic()
    try:
        from shellmate.agents.environment import get_environment_agent
        
        agent = get_environment_agent()
        response = await agent.send_request(
            "detect_context",
            data={"overrides": overrides},
            timeout=0.05  # 50ms timeout
        )
        elapsed = (time.monotonic() - start) * 1000
        if response and response.status == "ok":
            result = response.data or {}
            result["_latency_ms"] = round(elapsed, 1)
            return result
        return {}
    except Exception as e:
        logger.debug(f"Environment agent query failed: {e}")
        return {}


async def _query_command_chain_agent(current_command: str) -> dict:
    """Query CommandChainAgent for recent commands and patterns."""
    start = time.monotonic()
    try:
        from shellmate.agents.command_chain import get_command_chain_agent
        
        agent = get_command_chain_agent()
        
        # Get recent commands and patterns in one request
        response = await agent.send_request(
            "get_chain_patterns",
            data={"command": current_command, "count": 10, "minutes": 30},
            timeout=0.01  # 10ms timeout
        )
        
        elapsed = (time.monotonic() - start) * 1000
        
        if response and response.status == "ok":
            return {
                "recent_commands": response.data.get("command_chain", []),
                "patterns": response.data.get("chain_patterns", {}),
                "_latency_ms": elapsed,
            }
        
        return {"recent_commands": [], "patterns": {}, "_latency_ms": elapsed}
    except Exception as e:
        logger.debug(f"Command chain query failed: {e}")
        return {"recent_commands": [], "patterns": {}}


async def risk_analyzer_node(state: AnalysisState) -> dict:
    start = time.monotonic()
    command = state["command"]
    context = state.get("merged_context", {})
    result = await analyze_risk(command, context=context)
    elapsed = (time.monotonic() - start) * 1000
    return {
        "risk_analysis": result,
        "stages": _merge_stages(state, "risk_agent", elapsed),
    }


async def consequence_builder_node(state: AnalysisState) -> dict:
    """
    Build structured consequence preview from parsed command, risk, environment, and chain context.

    Transforms abstract risk levels into concrete "what will happen in YOUR environment"
    statements that are actionable and understandable.
    """
    start = time.monotonic()

    try:
        parsed = state.get("parsed", {}) or {}
        risk_analysis = state.get("risk_analysis", {}) or {}
        env_context = state.get("environment_context", {}) or {}
        chain_patterns = state.get("chain_patterns", {}) or {}

        risk_tier = risk_analysis.get("risk", "MEDIUM")
        severity = _map_risk_to_severity(risk_tier)

        what_happens = _build_what_happens(parsed, risk_analysis, env_context)
        scope = _build_scope(env_context, chain_patterns)
        reversible = _is_reversible(parsed, risk_analysis)
        affected_count = env_context.get("blast_radius", {}).get("estimated_users")
        suggested_fix = None  # remediation_node fills this later

        consequence_preview = {
            "what_happens": what_happens,
            "scope": scope,
            "reversible": reversible,
            "affected_count": affected_count,
            "suggested_fix": suggested_fix,
            "severity": severity,
        }

        elapsed = (time.monotonic() - start) * 1000
        return {
            "consequence_preview": consequence_preview,
            "stages": _merge_stages(state, "consequence_builder", elapsed),
        }
    except Exception as e:
        logger.warning(f"Consequence builder error: {e}")
        elapsed = (time.monotonic() - start) * 1000
        return {
            "consequence_preview": {
                "what_happens": "Analysis complete",
                "scope": "unknown",
                "reversible": True,
                "affected_count": None,
                "suggested_fix": None,
                "severity": "warning",
            },
            "stages": _merge_stages(state, "consequence_builder", elapsed),
        }


def _map_risk_to_severity(risk_tier: str) -> str:
    """Map risk tier to consequence severity for UI rendering."""
    mapping = {
        "CRITICAL": "blocking",
        "HIGH": "warning",
        "MEDIUM": "warning",
        "LOW": "info",
        "SAFE": "info",
    }
    return mapping.get(risk_tier, "warning")


def _build_what_happens(parsed: dict, risk_analysis: dict, env_context: dict) -> str:
    """Build plain-English description of what the command will do."""
    if not parsed or not parsed.get("program"):
        reason = risk_analysis.get("reason", "Unknown consequence")
        return reason[:100] if reason else "Consequence unclear"

    program = parsed.get("program", "unknown")
    risk_reason = risk_analysis.get("reason", "")

    consequence = _describe_command_consequence(program, parsed, risk_reason)

    env_type = env_context.get("type", "")
    if env_type and env_type != "development":
        consequence = f"{consequence} in {env_type} environment"

    return consequence


def _describe_command_consequence(program: str, parsed: dict, risk_reason: str) -> str:
    """Describe specific consequences based on command type."""
    if program in ("rm", "rmdir"):
        args = parsed.get("arguments", [])
        flags = [f.get("flag") for f in parsed.get("flags", [])]
        if "/" in str(args) or any(f in ("-rf", "-r") for f in flags):
            targets = ", ".join(str(a) for a in args[:2]) if args else "filesystem paths"
            return f"Will permanently delete {targets}"
        return "Will delete files"

    if program == "git" and parsed.get("subcommand") == "push":
        flags = [f.get("flag") for f in parsed.get("flags", [])]
        if any(f in ("--force", "-f", "--force-with-lease") for f in flags):
            branch = next((str(a) for a in parsed.get("arguments", [])), "current branch")
            return f"Will force-push and rewrite history on {branch}"
        return "Will push changes to remote"

    if program == "docker":
        subcommand = parsed.get("subcommand", "")
        if subcommand in ("rm", "stop"):
            containers = parsed.get("arguments", [])
            count = len(containers) if containers else "multiple"
            return f"Will stop/remove {count} container(s)"
        if subcommand == "run":
            return "Will start new container with specified config"

    if program == "sudo":
        return "Will execute with elevated privileges"

    if program == "chmod":
        targets = parsed.get("arguments", [])
        target_str = ", ".join(str(t) for t in targets[:2]) if targets else "files"
        return f"Will change permissions on {target_str}"

    if program == "mkfs":
        targets = parsed.get("arguments", [])
        device = str(targets[0]) if targets else "device"
        return f"Will format and erase all data on {device}"

    if risk_reason:
        return risk_reason[:80]

    return f"Will execute {program} command"


def _build_scope(env_context: dict, chain_patterns: dict) -> str:
    """Build scope description: how many resources/users/systems affected."""
    parts = []

    blast = env_context.get("blast_radius", {}) or {}
    if blast.get("estimated_size_gb"):
        parts.append(f"{blast['estimated_size_gb']}GB")

    if blast.get("num_directories"):
        parts.append(f"{blast['num_directories']} directories")

    if blast.get("num_files"):
        parts.append(f"{blast['num_files']} files")

    if blast.get("estimated_users"):
        parts.append(f"{blast['estimated_users']} users affected")

    if chain_patterns.get("dangerous_escalations"):
        parts.append(f"{len(chain_patterns['dangerous_escalations'])} escalation(s)")

    if chain_patterns.get("broken", []):
        parts.append("broken workflow detected")

    env_type = env_context.get("type", "")
    if env_type == "production":
        parts.append("production")
    elif env_type == "staging":
        parts.append("staging")

    if not parts:
        return "scope unclear"

    return " · ".join(parts)


def _is_reversible(parsed: dict, risk_analysis: dict) -> bool:
    """Determine if the command's effects can be undone."""
    program = parsed.get("program", "")
    subcommand = parsed.get("subcommand", "")
    flags = [f.get("flag") for f in parsed.get("flags", [])]

    irreversible_cmds = {
        "rm", "rmdir", "mkfs", "mkfs.ext4", "mkfs.btrfs",
        "shred", "wipe", "fdisk", "parted",
    }
    if program in irreversible_cmds:
        return False

    if program == "kill":
        if any(f in ("-9", "-KILL", "-SIGKILL") for f in flags):
            return False

    if program == "git" and subcommand == "push":
        if any(f in ("--force", "-f", "--force-with-lease") for f in flags):
            return False

    if program in ("mysql", "psql", "sqlite3", "mongo"):
        if any("drop" in str(f).lower() for f in flags):
            return False

    if program == "sudo" and parsed.get("arguments"):
        first_arg = str(parsed["arguments"][0]).lower()
        if any(cmd in first_arg for cmd in ("rm", "mkfs", "dd")):
            return False

    return True


async def remediation_node(state: AnalysisState) -> dict:
    start = time.monotonic()
    command = state["command"]
    risk = state.get("risk_analysis", {})
    context = state.get("merged_context", {})
    result = await generate_remediation(command, risk, context=context)
    elapsed = (time.monotonic() - start) * 1000
    out = {
        "remediation": result,
        "stages": _merge_stages(state, "remediation_agent", elapsed),
    }
    if result.get("command_guide"):
        out["command_guide"] = result["command_guide"]
    return out


async def command_guide_node(state: AnalysisState) -> dict:
    if _detect_early_exit(state):
        return {}
    if state.get("command_guide"):
        return {}
    from shellmate.providers.router import get_groq_provider
    if not get_groq_provider().is_available():
        return {}
    start = time.monotonic()
    try:
        merged_context = state.get("merged_context")
        context_str = _format_context(merged_context)
        risk = state.get("risk_analysis") or {}
        guide = await generate_command_guide(
            state["command"],
            context=context_str,
            risk_reason=risk.get("reason", ""),
        )
        elapsed = (time.monotonic() - start) * 1000
        return {"command_guide": guide, "stages": _merge_stages(state, "command_guide", elapsed)}
    except Exception as e:
        logger.debug(f"Command guide skipped: {e}")
        return {}


RISK_ORDER = {"SAFE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


def _calculate_risk_factors(state: AnalysisState) -> dict:
    """Calculate weighted risk factor breakdown."""
    factors = {
        "rule": 0.3,        # 30% from rule match
        "environment": 0.5,  # 50% from environment
        "chain": 0.2,        # 20% from command chain
    }
    
    # Adjust if components missing
    if not state.get("rule_match"):
        factors["rule"] = 0.0
        factors["environment"] = 0.6
        factors["chain"] = 0.4
    
    if not state.get("chain_patterns", {}).get("detected"):
        factors["chain"] = 0.0
        factors["rule"] += 0.1
        factors["environment"] += 0.1
    
    return factors


def _adjust_risk_for_environment(base_risk: str, env_context: dict) -> str:
    """Adjust risk level based on environment context."""
    current_level = RISK_ORDER.get(base_risk, 2)
    
    env_type = env_context.get("type", "unknown")
    time_ctx = env_context.get("time", {})
    blast_ctx = env_context.get("blast_radius", {})
    resources = env_context.get("resources", {})
    
    # Environment type adjustments
    if env_type == "production":
        current_level += 2
    elif env_type == "staging":
        current_level += 1
    elif env_type == "development":
        current_level -= 1
    
    # Time adjustments
    if time_ctx.get("is_business_hours"):
        current_level += 1
    
    # Blast radius adjustments
    if blast_ctx.get("is_multi_user"):
        current_level += 1
    
    # Resource adjustments
    if resources.get("disk_low") or resources.get("memory_high"):
        current_level += 1
    
    # Clamp to valid range
    current_level = max(0, min(4, current_level))
    
    # Convert back to label
    for label, level in RISK_ORDER.items():
        if level == current_level:
            return label
    return base_risk


def _adjust_risk_for_chain(base_risk: str, chain_patterns: dict) -> str:
    """Adjust risk level based on command chain patterns."""
    current_level = RISK_ORDER.get(base_risk, 2)
    
    # Apply adjustments from detected patterns (expected workflows lower risk)
    for pattern in chain_patterns.get("detected", []):
        current_level += pattern.get("risk_adjustment", 0)
    
    # Apply adjustments from broken workflows (increase risk)
    for pattern in chain_patterns.get("broken", []):
        current_level += pattern.get("risk_adjustment", 0)
    
    # Apply adjustments from dangerous escalations (significant increase)
    for pattern in chain_patterns.get("dangerous_escalations", []):
        current_level += pattern.get("risk_adjustment", 0)
    
    # Clamp to valid range
    current_level = max(0, min(4, current_level))
    
    # Convert back to label
    for label, level in RISK_ORDER.items():
        if level == current_level:
            return label
    return base_risk


def format_node(state: AnalysisState) -> dict:
    sanitized = state.get("sanitized", {}) or {}
    rule_match = state.get("rule_match")
    cached = state.get("cached")
    risk_analysis = state.get("risk_analysis")
    remediation = state.get("remediation")
    merged_context = state.get("merged_context")
    environment_context = state.get("environment_context", {})
    stages = state.get("stages", {})
    chain_patterns = state.get("chain_patterns", {}) or {}
    consequence_preview = _ensure_consequence_preview(state)

    detected_early_exit = _detect_early_exit(state)

    if detected_early_exit == "sanitizer":
        if sanitized.get("correction"):
            output = _build_output(
                risk="LOW",
                confidence=1.0,
                message=sanitized["correction"],
                explanation=sanitized.get("trailing_char", {}).get("message", ""),
                alternatives=[sanitized["correction"]],
                stages=stages,
                early_exit="sanitizer",
                consequence_preview=consequence_preview,
                environment_context=environment_context,
                chain_patterns=chain_patterns,
            )
            return {"output": output, "consequence_preview": consequence_preview}
        output = _build_output(
            risk="MEDIUM",
            confidence=0.9,
            message="Syntax error detected",
            explanation="; ".join(sanitized.get("syntax", {}).get("errors", [])),
            alternatives=["Fix the syntax and try again."],
            stages=stages,
            early_exit="sanitizer",
            consequence_preview=consequence_preview,
            environment_context=environment_context,
            chain_patterns=chain_patterns,
        )
        return {"output": output, "consequence_preview": consequence_preview}

    if detected_early_exit == "rule" and rule_match:
        output = _build_output(
            risk=rule_match.get("severity", rule_match.get("risk", "MEDIUM")),
            confidence=rule_match.get("confidence", 0.9),
            message=rule_match.get("message", ""),
            explanation=rule_match.get("description", ""),
            rule_id=rule_match.get("rule_id"),
            category=rule_match.get("category"),
            stages=stages,
            early_exit="rule_engine",
            consequence_preview=consequence_preview,
            environment_context=environment_context,
            chain_patterns=chain_patterns,
        )
        return {"output": output, "consequence_preview": consequence_preview}

    if detected_early_exit == "cache" and cached:
        output = _build_output(
            risk=cached.get("risk", "MEDIUM"),
            confidence=cached.get("confidence", 0.9),
            message=cached.get("explanation", ""),
            explanation=cached.get("explanation", ""),
            alternatives=cached.get("alternatives", []),
            cached=True,
            stages=stages,
            early_exit="cache",
            consequence_preview=consequence_preview or cached.get("consequence_preview"),
            environment_context=environment_context or cached.get("environment_context"),
            chain_patterns=chain_patterns or cached.get("chain_patterns"),
        )
        return {"output": output, "consequence_preview": consequence_preview}

    context_used = {
        "watcher": bool(merged_context and merged_context.get("watcher")),
        "librarian": bool(merged_context and merged_context.get("librarian", {}).get("matches")),
    } if merged_context else {"watcher": False, "librarian": False}

    # Get base risk from analysis
    base_risk = risk_analysis.get("risk", "MEDIUM") if risk_analysis else "MEDIUM"
    if rule_match and rule_match.get("matched"):
        rule_severity = rule_match.get("severity", rule_match.get("risk", "MEDIUM"))
        if RISK_ORDER.get(rule_severity, 0) > RISK_ORDER.get(base_risk, 0):
            base_risk = rule_severity

    # NEW v3: Adjust risk based on environment context and command chain
    risk_level = base_risk
    risk_factors = {}
    
    if environment_context:
        risk_level = _adjust_risk_for_environment(base_risk, environment_context)
    
    # Apply chain-based risk adjustments
    if chain_patterns:
        risk_level = _adjust_risk_for_chain(risk_level, chain_patterns)
    
    # Calculate risk factor breakdown
    if environment_context or chain_patterns:
        risk_factors = _calculate_risk_factors(state)

    if risk_analysis and risk_analysis.get("provider") != "fallback":
        normalized = sanitized.get("normalized", state["command"])
        cache_store(normalized, risk_analysis)

    alternatives = remediation.get("alternatives", []) if remediation else []
    command_guide = state.get("command_guide")
    if command_guide and _is_generic_remediation(alternatives):
        alternatives = alternatives_from_guide(command_guide) or alternatives

    output = _build_output(
        risk=risk_level,
        confidence=risk_analysis.get("confidence", 0.5) if risk_analysis else 0.5,
        message=risk_analysis.get("reason", remediation.get("explanation", "")) if risk_analysis or remediation else "Analysis completed",
        explanation=remediation.get("explanation", "") if remediation else "",
        alternatives=alternatives,
        context_used=context_used,
        rule_match=rule_match if rule_match and rule_match.get("matched") else None,
        risk_analysis=risk_analysis,
        stages=stages,
        agent_latency=state.get("agent_latency", {}),
        supervisor_fallback=state.get("supervisor_fallback", False),
        supervisor_warning=state.get("supervisor_warning"),
        command_guide=command_guide,
        failed_provider=(risk_analysis or {}).get("failed_provider")
        or (remediation or {}).get("failed_provider"),
        failed_credential=(risk_analysis or {}).get("failed_credential")
        or (remediation or {}).get("failed_credential"),
        consequence_preview=consequence_preview,
        environment_context=environment_context,
        chain_patterns=chain_patterns,
    )
    return {"output": output, "consequence_preview": consequence_preview}


def _ensure_consequence_preview(state: AnalysisState) -> Optional[Dict[str, Any]]:
    """Return existing consequence_preview or synthesize for early-exit paths."""
    existing = state.get("consequence_preview")
    if existing and existing.get("what_happens"):
        return existing

    parsed = state.get("parsed") or {}
    risk_analysis = state.get("risk_analysis") or {}
    if not risk_analysis:
        rule_match = state.get("rule_match") or {}
        if rule_match.get("matched"):
            risk_analysis = {
                "risk": rule_match.get("severity", rule_match.get("risk", "MEDIUM")),
                "reason": rule_match.get("message") or rule_match.get("description") or "",
            }
        cached = state.get("cached") or {}
        if cached and not risk_analysis:
            risk_analysis = {
                "risk": cached.get("risk", "MEDIUM"),
                "reason": cached.get("explanation", ""),
            }

    # Need at least a program or risk reason to build something useful
    if not parsed.get("program") and not risk_analysis.get("reason"):
        return existing

    env_context = state.get("environment_context") or {}
    chain_patterns = state.get("chain_patterns") or {}
    return {
        "what_happens": _build_what_happens(parsed, risk_analysis, env_context),
        "scope": _build_scope(env_context, chain_patterns),
        "reversible": _is_reversible(parsed, risk_analysis),
        "affected_count": (env_context.get("blast_radius") or {}).get("estimated_users"),
        "suggested_fix": None,
        "severity": _map_risk_to_severity(risk_analysis.get("risk", "MEDIUM")),
    }


_GENERIC_REMEDIATION = frozenset({
    "Review the command carefully before executing.",
    "Fix the syntax and try again.",
})


def _is_generic_remediation(alternatives: list) -> bool:
    if not alternatives:
        return True
    return all(alt in _GENERIC_REMEDIATION for alt in alternatives)


def _detect_early_exit(state: AnalysisState) -> str:
    sanitized = state.get("sanitized", {}) or {}
    if sanitized.get("correction"):
        return "sanitizer"
    if not sanitized.get("syntax", {}).get("valid", True):
        return "sanitizer"
    rule_match = state.get("rule_match")
    if rule_match and rule_match.get("matched") and rule_match.get("confidence", 0) >= 0.9:
        return "rule"
    cached = state.get("cached")
    if cached:
        return "cache"
    return ""


def _build_output(
    risk="MEDIUM",
    confidence=0.5,
    message="",
    explanation="",
    alternatives=None,
    context_used=None,
    rule_id=None,
    category=None,
    cached=False,
    rule_match=None,
    risk_analysis=None,
    stages=None,
    agent_latency=None,
    early_exit=None,
    supervisor_fallback=False,
    supervisor_warning=None,
    command_guide=None,
    failed_provider=None,
    failed_credential=None,
    consequence_preview=None,
    environment_context=None,
    chain_patterns=None,
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
    if early_exit:
        result["early_exit"] = early_exit
    if rule_match:
        result["rule_match"] = rule_match
    if risk_analysis:
        result["risk_analysis"] = risk_analysis
    if stages:
        result["latency"] = {k: round(v, 2) for k, v in stages.items()}
        result["total_ms"] = round(sum(stages.values()), 2)
    if agent_latency:
        result["agent_latency_ms"] = agent_latency
    if supervisor_fallback:
        result["supervisor_fallback"] = True
    if supervisor_warning:
        result["supervisor_warning"] = supervisor_warning
    if command_guide:
        result["command_guide"] = command_guide
    if failed_provider:
        result["failed_provider"] = failed_provider
    if failed_credential:
        result["failed_credential"] = failed_credential
    if consequence_preview:
        result["consequence_preview"] = consequence_preview
    if environment_context:
        result["environment_context"] = environment_context
    if chain_patterns:
        result["chain_patterns"] = chain_patterns
    return result


class AnalysisGraph:
    def __init__(self):
        self._compiled = None

    def build(self):
        workflow = StateGraph(AnalysisState)

        workflow.add_node("sanitize", sanitize_node)
        workflow.add_node("parse", parse_node)
        workflow.add_node("command_chain", command_chain_node)
        workflow.add_node("rules", rules_node)
        workflow.add_node("cache", cache_node)
        workflow.add_node("supervisor", supervisor_node)
        workflow.add_node("context_worker", context_worker_node)
        workflow.add_node("env_context", env_context_node)
        workflow.add_node("risk_analyzer", risk_analyzer_node)
        workflow.add_node("consequence_builder", consequence_builder_node)
        workflow.add_node("remediation", remediation_node)
        workflow.add_node("command_guide", command_guide_node)
        workflow.add_node("format", format_node)
        workflow.add_node("query", query_node)  # NEW v3

        workflow.set_entry_point("sanitize")

        workflow.add_edge("sanitize", "parse")
        workflow.add_edge("parse", "command_chain")
        workflow.add_edge("command_chain", "rules")
        workflow.add_edge("rules", "cache")

        workflow.add_conditional_edges(
            "cache",
            early_exit_router,
            {
                "early_exit_sanitizer": "format",
                "early_exit_rule": "format",
                "early_exit_cache": "format",
                "needs_context": "supervisor",
            },
        )

        workflow.add_conditional_edges(
            "supervisor",
            supervisor_router,
            {
                "context_worker": "context_worker",
                # Autocomplete / skip path: still fetch EnvironmentAgent for badges
                "skip_context": "env_context",
            },
        )

        workflow.add_edge("context_worker", "risk_analyzer")
        workflow.add_edge("env_context", "risk_analyzer")
        workflow.add_edge("risk_analyzer", "consequence_builder")
        workflow.add_edge("consequence_builder", "remediation")
        workflow.add_edge("remediation", "command_guide")
        workflow.add_edge("command_guide", "format")
        
        # NEW v3: Conditional query node
        workflow.add_conditional_edges(
            "format",
            _query_router,
            {
                "query": "query",
                "end": END,
            },
        )
        workflow.add_edge("query", END)

        self._compiled = workflow.compile(checkpointer=MemorySaver())
        return self._compiled

    async def ainvoke(self, command: str, user_queries=None, overrides=None, skip_context=False) -> dict:
        if self._compiled is None:
            self.build()

        initial_state: AnalysisState = {
            "command": command,
            "sanitized": None,
            "parsed": None,
            "rule_match": None,
            "cached": None,
            "needs_context": not skip_context,  # NEW: Disable context if skip_context=True
            "watcher_context": None,
            "librarian_context": None,
            "merged_context": None,
            "risk_analysis": None,
            "remediation": None,
            "output": None,
            "errors": [],
            "stages": {},
            "agent_latency": {"watcher": 0, "librarian": 0},
            "early_exit": None,
            "supervisor_decision": None,
            "supervisor_fallback": skip_context,  # NEW: Mark as fallback if skipping context
            "supervisor_warning": "Fast mode: context skipped" if skip_context else None,
            "command_guide": None,
            # NEW v3 fields
            "environment_context": None,
            "command_chain": [],
            "chain_patterns": {},
            "user_queries": user_queries or [],
            "query_responses": {},
            "overrides": overrides or {},
            "risk_factors": {},
            "consequence_preview": None,
        }

        try:
            result = await self._compiled.ainvoke(initial_state, {"configurable": {"thread_id": "main"}})
            output = result.get("output", {})
            if not output:
                output = _build_output(
                    risk="MEDIUM",
                    confidence=0.5,
                    message="Analysis completed with no output",
                )
            # query_responses are set by query_node which runs after format_node;
            # merge them into output so callers receive them.
            query_responses = result.get("query_responses", {})
            if query_responses:
                output["query_responses"] = query_responses
            # consequence_preview is built before format; ensure callers always see it
            # even if format_node took an early-exit path that omitted it.
            consequence_preview = result.get("consequence_preview")
            if consequence_preview and "consequence_preview" not in output:
                output["consequence_preview"] = consequence_preview
            if result.get("environment_context") and "environment_context" not in output:
                output["environment_context"] = result["environment_context"]
            if result.get("chain_patterns") and "chain_patterns" not in output:
                output["chain_patterns"] = result["chain_patterns"]
            return output
        except Exception as e:
            logger.error(f"Analysis graph error: {e}", exc_info=True)
            return _build_output(
                risk="MEDIUM",
                confidence=0.5,
                message=f"Analysis error: {e}",
                explanation="An error occurred during analysis.",
            )

    async def analyze_command(self, command: str, user_queries=None, overrides=None, skip_context=False) -> dict:
        """
        Analyze command through LangGraph pipeline.
        
        Args:
            command: The command to analyze
            user_queries: Optional list of user queries
            overrides: Optional environment overrides
            skip_context: If True, skip context gathering (for fast autocomplete)
        """
        return await self.ainvoke(command, user_queries, overrides, skip_context)

    async def gather_context(self, command: str) -> dict:
        if self._compiled is None:
            self.build()

        initial_state: AnalysisState = {
            "command": command,
            "sanitized": None,
            "parsed": None,
            "rule_match": None,
            "cached": None,
            "needs_context": True,
            "watcher_context": None,
            "librarian_context": None,
            "merged_context": None,
            "risk_analysis": None,
            "remediation": None,
            "output": None,
            "errors": [],
            "stages": {},
            "agent_latency": {"watcher": 0, "librarian": 0},
            "early_exit": None,
            "supervisor_decision": None,
            "supervisor_fallback": False,
            "supervisor_warning": None,
            "command_guide": None,
            # NEW v3 fields
            "environment_context": None,
            "command_chain": [],
            "chain_patterns": {},
            "user_queries": [],
            "query_responses": {},
            "overrides": {},
            "risk_factors": {},
            "consequence_preview": None,
        }

        try:
            context_result = await context_worker_node(initial_state)
            return {
                "watcher": context_result.get("watcher_context", {}),
                "librarian": context_result.get("librarian_context", {"matches": []}),
                "partial": context_result.get("merged_context", {}).get("partial", False),
                "latency_ms": context_result.get("stages", {}).get("context", 0),
                "agent_latency_ms": context_result.get("agent_latency", {"watcher": 0, "librarian": 0}),
            }
        except Exception as e:
            logger.error(f"Context gather error: {e}")
            return {
                "watcher": {},
                "librarian": {"matches": []},
                "partial": True,
                "latency_ms": 0,
                "agent_latency_ms": {"watcher": 0, "librarian": 0},
            }


_analysis_graph: Optional[AnalysisGraph] = None


def get_analysis_graph() -> AnalysisGraph:
    global _analysis_graph
    if _analysis_graph is None:
        _analysis_graph = AnalysisGraph()
    return _analysis_graph
