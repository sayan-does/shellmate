"""
QueryAgent: Processes user queries about command analysis.

Handles queries like [?why], [?what-if], [?alternatives], [?history], [?impact]
and provides context-aware responses based on AnalysisState.
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from shellmate.agents.base import Agent, AgentRequest, AgentResponse
from shellmate.orchestration.state import AnalysisState


class QueryAgent(Agent):
    """Processes user queries about command analysis."""

    def __init__(self):
        super().__init__(name="query")
        self.query_handlers = {
            "why": self._answer_why,
            "what-if": self._answer_what_if,
            "what if": self._answer_what_if,
            "alternatives": self._answer_alternatives,
            "history": self._answer_history,
            "impact": self._answer_impact,
            "did i": self._answer_did_i,
        }

    async def initialize(self) -> None:
        """Initialize the agent."""
        pass

    async def shutdown(self) -> None:
        """Shutdown the agent."""
        pass

    async def process(self, request: AgentRequest) -> AgentResponse:
        """Process agent requests by dispatching to appropriate methods."""
        start_time = time.time()

        try:
            if request.command == "process_queries":
                queries = request.data.get("queries", [])
                state = request.data.get("state", {})
                responses = await self.process_queries(queries, state)
                latency = (time.time() - start_time) * 1000
                return AgentResponse(
                    request.request_id,
                    self.name,
                    status="ok",
                    data={"responses": responses},
                    latency_ms=latency,
                )
            else:
                return AgentResponse(
                    request.request_id,
                    self.name,
                    status="error",
                    error=f"Unknown command: {request.command}",
                )
        except Exception as e:
            latency = (time.time() - start_time) * 1000
            return AgentResponse(
                request.request_id,
                self.name,
                status="error",
                error=str(e),
                latency_ms=latency,
            )

    async def process_queries(
        self, queries: List[str], state: AnalysisState
    ) -> Dict[str, str]:
        """
        Process all user queries and return responses with caching.

        Args:
            queries: List of query strings
            state: Current AnalysisState with all context

        Returns:
            Dictionary mapping queries to responses
        """
        responses = {}
        cache = self._load_cache()
        command = state.get("command", "")

        for query in queries:
            # Check cache first
            cache_key = f"{command}::{query}"
            if cache_key in cache:
                responses[query] = cache[cache_key]
                continue

            # Process query if not cached
            query_lower = query.lower().strip()

            # Match query to handler
            handler = None
            for key, func in self.query_handlers.items():
                if query_lower.startswith(key) or key in query_lower:
                    handler = func
                    break

            if handler:
                try:
                    response = await handler(query, state)
                    responses[query] = response
                    # Cache the response
                    cache[cache_key] = response
                except Exception as e:
                    responses[query] = f"Unable to answer: {str(e)}"
            else:
                response = (
                    "I don't understand this question. "
                    "Try: [?why], [?what-if], [?alternatives], [?history], [?impact]"
                )
                responses[query] = response
                cache[cache_key] = response

        # Save updated cache
        self._save_cache(cache)
        return responses

    async def _answer_why(self, query: str, state: AnalysisState) -> str:
        """Explain why command is risky."""
        # Get risk level (correction C-1: key is "risk", not "risk_level")
        risk_analysis = state.get("risk_analysis") or {}
        risk_level = risk_analysis.get("risk", "UNKNOWN")
        env_context = state.get("environment_context", {})
        chain_patterns = state.get("chain_patterns", {})
        risk_factors = state.get("risk_factors", {})

        reasons = [f"This command is {risk_level} risk because:"]

        # Environment factors
        env_type = env_context.get("type", "unknown")
        if env_type == "production":
            reasons.append("• Running in production environment")
        elif env_type == "staging":
            reasons.append("• Running in staging environment")

        time_ctx = env_context.get("time", {})
        if time_ctx.get("is_business_hours"):
            hour = time_ctx.get("hour", 0)
            reasons.append(f"• Business hours ({hour}:00)")

        blast = env_context.get("blast_radius", {})
        if blast.get("is_multi_user"):
            user_count = blast.get("active_users", 0)
            reasons.append(f"• {user_count} other users active")

        services = blast.get("critical_services", [])
        if services:
            reasons.append(f"• Critical services running: {', '.join(services)}")

        resources = env_context.get("resources", {})
        if resources.get("disk_low"):
            reasons.append(
                f"• Low disk space ({resources.get('disk_free_percent', 0)}% free)"
            )
        if resources.get("memory_high"):
            reasons.append(
                f"• High memory usage ({resources.get('memory_used_percent', 0)}%)"
            )

        # Chain factors
        for pattern in chain_patterns.get("broken", []):
            reasons.append(f"• Workflow broken: {pattern['description']}")

        for pattern in chain_patterns.get("dangerous_escalations", []):
            reasons.append(f"• Dangerous escalation: {pattern['description']}")

        # Risk breakdown
        if risk_factors:
            reasons.append("")
            reasons.append("Risk Breakdown:")
            for factor, weight in risk_factors.items():
                if weight > 0:
                    percentage = int(weight * 100)
                    reasons.append(f"  {factor.title()}: {percentage}%")

        # Add primary reason from analysis
        if risk_analysis.get("reason"):
            reasons.append("")
            reasons.append(f"Primary reason: {risk_analysis['reason']}")

        return "\n".join(reasons)

    async def _answer_what_if(self, query: str, state: AnalysisState) -> str:
        """Answer '[?what-if]' using consequence_preview (hypothetical outcome)."""
        command = state.get("command") or "this command"
        consequence = state.get("consequence_preview") or {}
        risk_analysis = state.get("risk_analysis") or {}
        env_context = state.get("environment_context") or {}
        remediation = state.get("remediation") or {}

        what_happens = consequence.get("what_happens") or risk_analysis.get("reason")
        scope = consequence.get("scope")
        reversible = consequence.get("reversible")
        affected = consequence.get("affected_count")
        severity = consequence.get("severity") or risk_analysis.get("risk")
        suggested = consequence.get("suggested_fix")

        if not suggested:
            alternatives = remediation.get("alternatives") or []
            if alternatives:
                suggested = alternatives[0]

        lines = [f"If you run `{command}`:"]

        if what_happens:
            lines.append(f"• What happens: {what_happens}")
        else:
            lines.append("• What happens: Outcome is unclear from available analysis")

        if scope:
            lines.append(f"• Scope: {scope}")

        env_type = env_context.get("type")
        if env_type:
            lines.append(f"• Environment: {env_type}")

        if reversible is not None:
            lines.append(f"• Reversible: {'yes' if reversible else 'no'}")

        if affected is not None:
            lines.append(f"• Affected: {affected}")

        blast = env_context.get("blast_radius") or {}
        if blast.get("is_multi_user"):
            users = blast.get("active_users", 0)
            lines.append(f"• Active users impacted: {users}")

        if severity:
            lines.append(f"• Severity: {severity}")

        if suggested:
            lines.append(f"• Safer form: {suggested}")

        return "\n".join(lines)

    async def _answer_alternatives(self, query: str, state: AnalysisState) -> str:
        """Suggest safer alternatives."""
        remediation = state.get("remediation", {})
        alternatives = remediation.get("alternatives", [])

        if not alternatives:
            return "No safer alternatives identified."

        lines = ["Safer alternatives:"]
        for i, alt in enumerate(alternatives[:5], 1):
            lines.append(f"{i}. {alt}")

        return "\n".join(lines)

    async def _answer_history(self, query: str, state: AnalysisState) -> str:
        """Query command history."""
        command = state.get("command", "")
        command_chain = state.get("command_chain", [])

        # Check if command was run before
        matching = [c for c in command_chain if c.get("command") == command]

        if not matching:
            return "You haven't run this exact command in this session."

        last_run = matching[-1]
        timestamp = last_run.get("timestamp", "unknown")
        exit_code = last_run.get("exit_code", "unknown")
        risk = last_run.get("risk", "unknown")

        return (
            f"Last run: {timestamp}\n"
            f"Exit code: {exit_code}\n"
            f"Risk level: {risk}"
        )

    async def _answer_impact(self, query: str, state: AnalysisState) -> str:
        """Estimate blast radius and impact."""
        env_context = state.get("environment_context", {})
        blast = env_context.get("blast_radius", {})
        resources = env_context.get("resources", {})

        impact_lines = ["This command will affect:"]

        env_type = env_context.get("type", "unknown")
        impact_lines.append(f"• Environment: {env_type}")

        if blast.get("is_multi_user"):
            user_count = blast.get("active_users", 0)
            impact_lines.append(f"• {user_count} active users on this system")

        services = blast.get("critical_services", [])
        if services:
            impact_lines.append(f"• Critical services: {', '.join(services)}")

        if resources.get("disk_low"):
            impact_lines.append(
                f"• WARNING: Low disk space ({resources.get('disk_free_percent', 0)}% free)"
            )

        if resources.get("memory_high"):
            impact_lines.append(
                f"• WARNING: High memory usage ({resources.get('memory_used_percent', 0)}%)"
            )

        if resources.get("cpu_high"):
            impact_lines.append(
                f"• WARNING: High CPU load ({resources.get('cpu_load_percent', 0)}%)"
            )

        if len(impact_lines) == 1:
            impact_lines.append("• No significant impact factors detected")

        return "\n".join(impact_lines)

    async def _answer_did_i(self, query: str, state: AnalysisState) -> str:
        """Answer 'did I...' questions about command history."""
        command_chain = state.get("command_chain", [])

        if not command_chain:
            return "No command history available for this session."

        # Try to extract what they're asking about
        query_lower = query.lower()
        search_terms = []

        # Extract keywords after "did i"
        if "did i" in query_lower:
            after_did_i = query_lower.split("did i", 1)[1].strip()
            search_terms = after_did_i.split()

        if not search_terms:
            return "I couldn't understand what you're asking about."

        # Search history for matching commands
        matching = []
        for entry in command_chain:
            cmd = entry.get("command", "").lower()
            if any(term in cmd for term in search_terms):
                matching.append(entry)

        if not matching:
            return f"No, you haven't run commands matching: {' '.join(search_terms)}"

        # Return recent matches
        lines = [f"Yes, you ran {len(matching)} matching command(s):"]
        for entry in matching[-5:]:  # Last 5 matches
            timestamp = entry.get("timestamp", "unknown")
            command = entry.get("command", "unknown")
            lines.append(f"• {timestamp}: {command}")

        return "\n".join(lines)


    def _load_cache(self) -> dict:
        """Load query cache from session storage.
        
        Returns:
            dict: Cached query responses (command::query -> response)
        """
        try:
            from shellmate.daemon.session import get_query_cache_file
            cache_file = get_query_cache_file()

            if not cache_file.exists():
                return {}

            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            # Gracefully handle any cache loading errors
            return {}

    def _save_cache(self, cache: dict) -> None:
        """Save query cache to session storage.
        
        Args:
            cache: Dictionary of cached responses to save
        """
        try:
            from shellmate.daemon.session import get_query_cache_file
            cache_file = get_query_cache_file()

            # Ensure parent directory exists
            cache_file.parent.mkdir(parents=True, exist_ok=True)

            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2)

            # Set restrictive permissions on non-Windows
            import sys
            if sys.platform != "win32":
                import os
                os.chmod(cache_file, 0o600)
        except Exception:
            # Silently ignore cache save errors to not break query processing
            pass


# Singleton instance
_query_agent: Optional[QueryAgent] = None


def get_query_agent() -> QueryAgent:
    """Get the singleton QueryAgent instance."""
    global _query_agent
    if _query_agent is None:
        _query_agent = QueryAgent()
    return _query_agent
