"""
EnvironmentAgent: Detects execution environment context for risk assessment.

Provides environment type, time context, blast radius, and resource constraints
to inform risk calculations.
"""

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from shellmate.agents.base import Agent, AgentRequest, AgentResponse
from shellmate.config.defaults import get_default_config
from shellmate.daemon.session import get_environment_cache_file


class EnvironmentAgent(Agent):
    """Detects execution environment context for risk assessment."""

    def __init__(self):
        super().__init__(name="environment")
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_time: Optional[float] = None
        self._cache_file = get_environment_cache_file()

    async def initialize(self) -> None:
        """Initialize the agent and load cache if available."""
        if self._cache_file.exists():
            try:
                with open(self._cache_file, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                    self._cache = cached_data.get("context")
                    self._cache_time = cached_data.get("time")
            except (json.JSONDecodeError, OSError):
                pass

    async def shutdown(self) -> None:
        """Shutdown the agent and save cache."""
        if self._cache and self._cache_time:
            try:
                with open(self._cache_file, "w", encoding="utf-8") as f:
                    json.dump({"context": self._cache, "time": self._cache_time}, f)
            except OSError:
                pass

    async def process(self, request: AgentRequest) -> AgentResponse:
        """Process agent requests by dispatching to appropriate methods."""
        if request.command == "detect_context":
            start_time = time.time()
            try:
                data = await self.detect_context(request.data.get("overrides", {}))
                latency = (time.time() - start_time) * 1000
                return AgentResponse(
                    request.request_id,
                    self.name,
                    status="ok",
                    data=data,
                    latency_ms=latency,
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
        return AgentResponse(
            request.request_id,
            self.name,
            status="error",
            error=f"Unknown command: {request.command}",
        )

    async def detect_context(
        self, overrides: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Detect environment context with caching.

        Args:
            overrides: User-provided override values (e.g., [@env=production])

        Returns:
            Dictionary containing environment type, time context, blast radius,
            and resource constraints.
        """
        # Check cache validity
        if self._is_cache_valid():
            context = self._cache.copy()
        else:
            # Detect all context factors
            context = {
                "type": await self._detect_environment_type(),
                "time": await self._detect_time_context(),
                "blast_radius": await self._detect_blast_radius(),
                "resources": await self._detect_resource_constraints(),
            }
            # Cache results
            self._cache_context(context)

        # Apply user overrides
        if overrides:
            context = self._apply_overrides(context, overrides)

        return context

    def _is_cache_valid(self) -> bool:
        """Check if cached context is still valid based on TTL."""
        if not self._cache or not self._cache_time:
            return False

        config = get_default_config()
        ttl_minutes = (
            config.get("v3", {}).get("environment", {}).get("cache_ttl_minutes", 5)
        )
        ttl_seconds = ttl_minutes * 60

        return (time.time() - self._cache_time) < ttl_seconds

    def _cache_context(self, context: Dict[str, Any]) -> None:
        """Cache the detected context with timestamp."""
        self._cache = context
        self._cache_time = time.time()

    def _apply_overrides(
        self, context: Dict[str, Any], overrides: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Apply user overrides to the detected context."""
        if "env" in overrides:
            context["type"] = overrides["env"]
        if "time" in overrides:
            # Allow overriding time context
            context["time"].update(overrides["time"])
        return context

    async def _detect_environment_type(self) -> str:
        """
        Detect environment type using multiple heuristics.

        Returns one of: production, staging, development, ci, container, kubernetes
        """
        # Check file markers
        if Path("/etc/production").exists():
            return "production"
        if Path("/.dockerenv").exists():
            return "container"

        # Check environment variables
        env_vars = os.environ
        explicit = (
            env_vars.get("SHELLMATE_ENV")
            or env_vars.get("SM_ENV_TYPE")
            or env_vars.get("SM_ENV")
        )
        if explicit:
            normalized = explicit.strip().lower()
            if normalized in {
                "production",
                "staging",
                "development",
                "ci",
                "container",
                "kubernetes",
            }:
                return normalized

        if "CI" in env_vars or "GITHUB_ACTIONS" in env_vars:
            return "ci"
        if "KUBERNETES_SERVICE_HOST" in env_vars:
            return "kubernetes"
        if "STAGING" in env_vars:
            return "staging"

        # Check hostname patterns
        try:
            hostname = socket.gethostname().lower()
            if any(pattern in hostname for pattern in ["prod", "-prd", "production"]):
                return "production"
            if "staging" in hostname or "stg" in hostname:
                return "staging"
        except Exception:
            pass

        # Default to development
        return "development"

    async def _detect_time_context(self) -> Dict[str, Any]:
        """
        Detect time-related context factors.

        Returns:
            Dictionary with current_time, hour, is_business_hours, is_weekend, timezone
        """
        config = get_default_config()
        env_cfg = config.get("v3", {}).get("environment", {})
        tz_name = env_cfg.get("timezone", "UTC")
        biz_start = env_cfg.get("business_hours_start", 9)
        biz_end = env_cfg.get("business_hours_end", 17)

        # Get current time in configured timezone
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("UTC")

        now = datetime.now(tz)
        hour = now.hour

        is_business_hours = biz_start <= hour < biz_end and now.weekday() < 5
        return {
            "current_time": now.isoformat(),
            "hour": hour,
            "is_business_hours": is_business_hours,
            "after_hours": not is_business_hours,
            "is_weekend": now.weekday() >= 5,
            "timezone": tz_name,
        }

    async def _detect_blast_radius(self) -> Dict[str, Any]:
        """
        Detect factors affecting command blast radius.

        Returns:
            Dictionary with is_multi_user, active_users, critical_services
        """
        blast_radius = {
            "is_multi_user": False,
            "active_users": 0,
            "critical_services": [],
        }

        try:
            if sys.platform == "win32":
                # Windows detection
                result = subprocess.run(
                    ["query", "user"],
                    capture_output=True,
                    text=True,
                    timeout=1,
                )
                if result.returncode == 0:
                    # Count lines (users) in output
                    lines = [line for line in result.stdout.split("\n") if line.strip()]
                    blast_radius["active_users"] = max(0, len(lines) - 1)
            else:
                # Linux/Unix detection
                result = subprocess.run(
                    ["who"], capture_output=True, text=True, timeout=1
                )
                if result.returncode == 0:
                    blast_radius["active_users"] = len(
                        result.stdout.strip().split("\n")
                    )

            blast_radius["is_multi_user"] = blast_radius["active_users"] > 1

            # Detect critical services (platform-specific)
            blast_radius["critical_services"] = await self._detect_services()

        except Exception:
            # Fallback to safe defaults
            pass

        return blast_radius

    async def _detect_services(self) -> list:
        """Detect critical running services."""
        services = []
        try:
            if sys.platform == "win32":
                # Check for common Windows services
                result = subprocess.run(
                    ["sc", "query", "state=", "running"],
                    capture_output=True,
                    text=True,
                    timeout=1,
                )
                if result.returncode == 0:
                    # Look for critical service names
                    for service in ["Docker", "PostgreSQL", "MySQL", "nginx"]:
                        if service.lower() in result.stdout.lower():
                            services.append(service.lower())
            else:
                # Check for common Linux/Unix services
                for service in ["nginx", "postgres", "docker", "mysql"]:
                    result = subprocess.run(
                        ["systemctl", "is-active", service],
                        capture_output=True,
                        text=True,
                        timeout=0.5,
                    )
                    if result.returncode == 0 and "active" in result.stdout:
                        services.append(service)
        except Exception:
            pass

        return services

    async def _detect_resource_constraints(self) -> Dict[str, Any]:
        """
        Detect system resource constraints.

        Returns:
            Dictionary with disk_free_percent, disk_low, memory_used_percent,
            memory_high, cpu_load_percent, cpu_high
        """
        try:
            import psutil

            # Disk space
            if sys.platform == "win32":
                disk = psutil.disk_usage("C:\\")
            else:
                disk = psutil.disk_usage("/")
            disk_free_percent = (disk.free / disk.total) * 100

            # Memory
            memory = psutil.virtual_memory()
            memory_used_percent = memory.percent

            # CPU load (1-minute average)
            cpu_load = psutil.cpu_percent(interval=0.1)

            return {
                "disk_free_percent": round(disk_free_percent, 1),
                "disk_low": disk_free_percent < 10,
                "memory_used_percent": round(memory_used_percent, 1),
                "memory_high": memory_used_percent > 80,
                "cpu_load_percent": round(cpu_load, 1),
                "cpu_high": cpu_load > 90,
            }
        except Exception:
            # Fallback to safe defaults (no constraints detected)
            return {
                "disk_free_percent": 50.0,
                "disk_low": False,
                "memory_used_percent": 50.0,
                "memory_high": False,
                "cpu_load_percent": 50.0,
                "cpu_high": False,
            }


# Singleton instance
_environment_agent: Optional[EnvironmentAgent] = None


def get_environment_agent() -> EnvironmentAgent:
    """Get the singleton EnvironmentAgent instance."""
    global _environment_agent
    if _environment_agent is None:
        _environment_agent = EnvironmentAgent()
    return _environment_agent
