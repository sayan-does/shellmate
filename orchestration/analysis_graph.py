import asyncio
import logging
import os
import time
from typing import Any, Dict, Optional, List
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from orchestration.state import AnalysisState
from parser.command_parser import parse_command
from sanitizer.typo_detector import sanitize
from rules.engine import load_rules, match_rule
from cache.semantic_cache import cache_lookup, cache_store
from agents.watcher import get_watcher_agent
from agents.librarian import get_librarian_agent
from agents.repomix_backend import get_repomix_backend
from providers.router import analyze_risk, generate_remediation
from providers.groq_provider import _format_context
from providers.groq_supervisor import route_command, SupervisorError
from providers.groq_command_guide import generate_command_guide, CommandGuideError, alternatives_from_guide
from config.defaults import get_default_config
from config.secrets import redact_dict

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


async def context_worker_node(state: AnalysisState) -> dict:
    start = time.monotonic()
    command = state["command"]
    agent_latency = {"watcher": 0, "librarian": 0}

    decision = state.get("supervisor_decision") or {}
    run_watcher = decision.get("run_watcher", state.get("needs_context", True))
    run_librarian = decision.get("run_librarian", state.get("needs_context", True))

    watcher_context = {}
    librarian_context = {"matches": []}
    partial = False

    tasks = {}
    if run_watcher:
        tasks["watcher"] = asyncio.create_task(_query_watcher(command))
    if run_librarian:
        tasks["librarian"] = asyncio.create_task(_query_librarian(command))
        tasks["repomix"] = asyncio.create_task(_query_repomix(command))

    if not tasks:
        elapsed = (time.monotonic() - start) * 1000
        return {
            "watcher_context": watcher_context,
            "librarian_context": librarian_context,
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
        except asyncio.CancelledError:
            partial = True
        except Exception as e:
            logger.warning(f"Context worker {name} error: {e}")
            partial = True

    elapsed = (time.monotonic() - start) * 1000
    return {
        "watcher_context": watcher_context,
        "librarian_context": librarian_context,
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
    from providers.router import get_groq_provider
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


def format_node(state: AnalysisState) -> dict:
    sanitized = state.get("sanitized", {}) or {}
    rule_match = state.get("rule_match")
    cached = state.get("cached")
    risk_analysis = state.get("risk_analysis")
    remediation = state.get("remediation")
    merged_context = state.get("merged_context")
    stages = state.get("stages", {})

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
            )
            return {"output": output}
        output = _build_output(
            risk="MEDIUM",
            confidence=0.9,
            message="Syntax error detected",
            explanation="; ".join(sanitized.get("syntax", {}).get("errors", [])),
            alternatives=["Fix the syntax and try again."],
            stages=stages,
            early_exit="sanitizer",
        )
        return {"output": output}

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
        )
        return {"output": output}

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
        )
        return {"output": output}

    context_used = {
        "watcher": bool(merged_context and merged_context.get("watcher")),
        "librarian": bool(merged_context and merged_context.get("librarian", {}).get("matches")),
    } if merged_context else {"watcher": False, "librarian": False}

    risk_level = risk_analysis.get("risk", "MEDIUM") if risk_analysis else "MEDIUM"
    if rule_match and rule_match.get("matched"):
        rule_severity = rule_match.get("severity", rule_match.get("risk", "MEDIUM"))
        if RISK_ORDER.get(rule_severity, 0) > RISK_ORDER.get(risk_level, 0):
            risk_level = rule_severity

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
    )
    return {"output": output}


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
    return result


class AnalysisGraph:
    def __init__(self):
        self._compiled = None

    def build(self):
        workflow = StateGraph(AnalysisState)

        workflow.add_node("sanitize", sanitize_node)
        workflow.add_node("parse", parse_node)
        workflow.add_node("rules", rules_node)
        workflow.add_node("cache", cache_node)
        workflow.add_node("supervisor", supervisor_node)
        workflow.add_node("context_worker", context_worker_node)
        workflow.add_node("risk_analyzer", risk_analyzer_node)
        workflow.add_node("remediation", remediation_node)
        workflow.add_node("command_guide", command_guide_node)
        workflow.add_node("format", format_node)

        workflow.set_entry_point("sanitize")

        workflow.add_edge("sanitize", "parse")
        workflow.add_edge("parse", "rules")
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
                "skip_context": "risk_analyzer",
            },
        )

        workflow.add_edge("context_worker", "risk_analyzer")
        workflow.add_edge("risk_analyzer", "remediation")
        workflow.add_edge("remediation", "command_guide")
        workflow.add_edge("command_guide", "format")
        workflow.add_edge("format", END)

        self._compiled = workflow.compile(checkpointer=MemorySaver())
        return self._compiled

    async def ainvoke(self, command: str) -> dict:
        if self._compiled is None:
            self.build()

        initial_state: AnalysisState = {
            "command": command,
            "sanitized": None,
            "parsed": None,
            "rule_match": None,
            "cached": None,
            "needs_context": False,
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
            return output
        except Exception as e:
            logger.error(f"Analysis graph error: {e}", exc_info=True)
            return _build_output(
                risk="MEDIUM",
                confidence=0.5,
                message=f"Analysis error: {e}",
                explanation="An error occurred during analysis.",
            )

    async def analyze_command(self, command: str) -> dict:
        return await self.ainvoke(command)

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
