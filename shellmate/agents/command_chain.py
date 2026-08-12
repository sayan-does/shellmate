"""
CommandChainAgent: Tracks command history and detects workflow patterns.

Maintains a persistent JSONL history of commands and analyzes patterns
to detect expected workflows, broken workflows, and dangerous escalations.
"""

import asyncio
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from shellmate.agents.base import Agent, AgentRequest, AgentResponse
from shellmate.config.defaults import get_default_config
from shellmate.daemon.session import get_command_history_file


class CommandChainAgent(Agent):
    """Tracks command history and detects workflow patterns."""

    def __init__(self):
        super().__init__(name="command_chain")
        self.history_file = get_command_history_file()
        self.patterns = []
        self.patterns_file = Path(__file__).parent / "chain_patterns.yaml"

    async def initialize(self) -> None:
        """Initialize the agent and load pattern definitions."""
        self._load_patterns()

    async def shutdown(self) -> None:
        """Shutdown the agent."""
        pass

    async def process(self, request: AgentRequest) -> AgentResponse:
        """Process agent requests by dispatching to appropriate methods."""
        start_time = time.time()
        
        try:
            if request.command == "append_command":
                data = request.data
                await self.append_command(
                    data.get("command", ""),
                    data.get("risk", "MEDIUM"),
                    data.get("exit_code")
                )
                latency = (time.time() - start_time) * 1000
                return AgentResponse(
                    request.request_id,
                    self.name,
                    status="ok",
                    data={"success": True},
                    latency_ms=latency,
                )
            elif request.command == "get_chain_patterns":
                data = request.data
                recent_commands = await self.get_recent_commands(
                    count=data.get("count", 10),
                    minutes=data.get("minutes", 30)
                )
                current_command = data.get("command", "")
                patterns = await self.detect_patterns(recent_commands, current_command)
                latency = (time.time() - start_time) * 1000
                return AgentResponse(
                    request.request_id,
                    self.name,
                    status="ok",
                    data={
                        "command_chain": recent_commands,
                        "chain_patterns": patterns,
                    },
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

    def _load_patterns(self) -> None:
        """Load workflow patterns from YAML file."""
        if not self.patterns_file.exists():
            self.patterns = []
            return

        try:
            with open(self.patterns_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                self.patterns = data.get("patterns", [])
        except Exception:
            self.patterns = []

    def _redact_secrets(self, command: str) -> str:
        """Redact secrets from command before storage."""
        config = get_default_config()
        secret_patterns = (
            config.get("v3", {})
            .get("command_history", {})
            .get("secret_patterns", [])
        )

        redacted = command
        for pattern in secret_patterns:
            try:
                redacted = re.sub(pattern, r"\1***", redacted)
            except Exception:
                pass

        return redacted

    async def append_command(
        self, command: str, risk: str, exit_code: Optional[int] = None
    ) -> None:
        """
        Append command to history file (JSONL format).

        Args:
            command: The command that was executed
            risk: Risk level (SAFE, LOW, MEDIUM, HIGH, CRITICAL)
            exit_code: Command exit code (optional)
        """
        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "command": self._redact_secrets(command),
            "risk": risk,
            "exit_code": exit_code,
            "directory": str(Path.cwd()),
        }

        # Append to JSONL file
        try:
            with open(self.history_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            # Fail silently if we can't write to history
            pass

    async def get_recent_commands(
        self, count: int = 10, minutes: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Query recent commands from history.

        Args:
            count: Maximum number of commands to return
            minutes: Optional time window in minutes

        Returns:
            List of command entries
        """
        if not self.history_file.exists():
            return []

        commands = []
        cutoff = None
        if minutes:
            cutoff = datetime.utcnow() - timedelta(minutes=minutes)

        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        timestamp = datetime.fromisoformat(
                            entry["timestamp"].replace("Z", "")
                        )

                        if cutoff and timestamp < cutoff:
                            continue

                        commands.append(entry)
                    except (json.JSONDecodeError, KeyError, ValueError):
                        continue
        except OSError:
            return []

        # Return last N commands
        return commands[-count:]

    async def detect_patterns(
        self, recent_commands: List[Dict[str, Any]], current_command: str
    ) -> Dict[str, Any]:
        """
        Detect workflow patterns in command chain.

        Args:
            recent_commands: List of recent command entries
            current_command: The command being analyzed

        Returns:
            Dictionary with detected, broken, and dangerous_escalations lists
        """
        detected_patterns = {
            "detected": [],
            "broken": [],
            "dangerous_escalations": [],
        }

        for pattern_def in self.patterns:
            match_result = self._match_pattern(
                pattern_def, recent_commands, current_command
            )

            if match_result["type"] == "expected_workflow":
                detected_patterns["detected"].append(
                    {
                        "name": pattern_def["name"],
                        "description": pattern_def["description"],
                        "risk_adjustment": -1,  # Lower risk
                    }
                )
            elif match_result["type"] == "broken_workflow":
                detected_patterns["broken"].append(
                    {
                        "name": pattern_def["name"],
                        "description": pattern_def["description"],
                        "risk_adjustment": +1,  # Higher risk
                        "missing_step": match_result["missing_step"],
                    }
                )
            elif match_result["type"] == "dangerous_escalation":
                detected_patterns["dangerous_escalations"].append(
                    {
                        "name": pattern_def["name"],
                        "description": pattern_def["description"],
                        "risk_adjustment": +2,  # Much higher risk
                        "previous_command": match_result.get("previous_command"),
                    }
                )

        return detected_patterns

    def _match_pattern(
        self,
        pattern_def: Dict[str, Any],
        history: List[Dict[str, Any]],
        current: str,
    ) -> Dict[str, str]:
        """
        Match a single pattern definition against history.

        Args:
            pattern_def: Pattern definition from YAML
            history: List of recent commands
            current: Current command being analyzed

        Returns:
            Dictionary with match type and additional info
        """
        sequence = pattern_def.get("sequence", [])
        if not sequence:
            return {"type": "no_match"}

        matched_steps = []

        # Check if current command matches final step
        final_step = sequence[-1]
        try:
            if not re.search(final_step["pattern"], current):
                return {"type": "no_match"}
        except re.error:
            return {"type": "no_match"}

        # Check if required prior steps are in history
        for step in sequence[:-1]:
            if not step.get("required", False):
                continue

            found = False
            for entry in reversed(history):
                try:
                    if re.search(step["pattern"], entry["command"]):
                        matched_steps.append(entry)
                        found = True
                        break
                except re.error:
                    pass

            if not found:
                return {
                    "type": "broken_workflow",
                    "missing_step": step["pattern"],
                }

        # Check for dangerous escalations
        if pattern_def.get("risk_if_detected") == "CRITICAL":
            return {
                "type": "dangerous_escalation",
                "previous_command": (
                    matched_steps[0]["command"] if matched_steps else None
                ),
            }

        return {"type": "expected_workflow"}


# Singleton instance
_command_chain_agent: Optional[CommandChainAgent] = None


def get_command_chain_agent() -> CommandChainAgent:
    """Get the singleton CommandChainAgent instance."""
    global _command_chain_agent
    if _command_chain_agent is None:
        _command_chain_agent = CommandChainAgent()
    return _command_chain_agent
