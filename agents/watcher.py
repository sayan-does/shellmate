import asyncio
import os
import platform
import subprocess
import sys
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from agents.base import Agent, AgentRequest, AgentResponse
from config.secrets import redact_secrets

logger = logging.getLogger("shellmate.agents.watcher")


class WatcherAgent(Agent):
    def __init__(self):
        super().__init__("watcher")
        self._cached_context: Optional[Dict[str, Any]] = None
        self._cache_valid = False

    async def initialize(self) -> None:
        self._cached_context = await self._gather_context()
        self._cache_valid = True
        logger.info("Watcher agent initialized with cached context")

    async def shutdown(self) -> None:
        self._cached_context = None
        self._cache_valid = False

    async def process(self, request: AgentRequest) -> AgentResponse:
        if not self._cache_valid:
            self._cached_context = await self._gather_context()
            self._cache_valid = True

        return AgentResponse(
            request_id=request.request_id,
            agent_name=self.name,
            status="ok",
            data=self._cached_context or {},
            latency_ms=0.0,
        )

    async def _gather_context(self) -> Dict[str, Any]:
        context = {}

        context["os"] = self._detect_os()
        context["shell"] = self._detect_shell()
        context["terminal"] = self._detect_terminal()
        context["environment"] = self._detect_environment()
        context["interactive"] = self._detect_interactive()
        context["tech_stack"] = await self._detect_tech_stack()
        context["git"] = await self._detect_git_context()

        return self._redact_context(context)

    def _detect_os(self) -> Dict[str, Any]:
        return {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
        }

    def _detect_shell(self) -> Optional[str]:
        shell = os.environ.get("SHELL")
        if shell:
            return Path(shell).name
        if sys.platform == "win32":
            return os.environ.get("COMSPEC", "cmd.exe").split("\\")[-1]
        return None

    def _detect_terminal(self) -> Optional[str]:
        term = os.environ.get("TERM")
        term_program = os.environ.get("TERM_PROGRAM")
        if term_program:
            return term_program
        if term:
            return term
        if sys.platform == "win32":
            return "windows_console"
        return None

    def _detect_environment(self) -> Dict[str, bool]:
        env = {}
        env["wsl"] = "WSL_DISTRO_NAME" in os.environ or "WSL_INTEROP" in os.environ
        env["container"] = Path("/.dockerenv").exists() or os.environ.get("CONTAINER") == "true"
        env["ssh"] = "SSH_CONNECTION" in os.environ or "SSH_CLIENT" in os.environ
        env["ci"] = any(k in os.environ for k in ["CI", "GITHUB_ACTIONS", "GITLAB_CI", "BUILDKITE"])
        return env

    def _detect_interactive(self) -> bool:
        if sys.stdin.isatty():
            return True
        if sys.platform == "win32":
            try:
                import msvcrt
                return msvcrt.kbhit() or True
            except ImportError:
                pass
        return False

    async def _detect_tech_stack(self) -> List[str]:
        cwd = Path.cwd()
        indicators = []

        checks = [
            ("package.json", "nodejs"),
            ("pyproject.toml", "python"),
            ("requirements.txt", "python"),
            ("setup.py", "python"),
            ("Cargo.toml", "rust"),
            ("go.mod", "go"),
            ("pom.xml", "java"),
            ("build.gradle", "java"),
            ("composer.json", "php"),
            ("Gemfile", "ruby"),
            ("mix.exs", "elixir"),
            ("rebar.config", "erlang"),
            ("vite.config.ts", "nodejs"),
            ("vite.config.js", "nodejs"),
            ("vite.config.mjs", "nodejs"),
            ("vite.config.cjs", "nodejs"),
            ("tsconfig.json", "typescript"),
            ("Makefile", "make"),
            ("CMakeLists.txt", "cmake"),
            ("Dockerfile", "docker"),
            ("docker-compose.yml", "docker"),
            (".github/workflows", "github_actions"),
            (".gitlab-ci.yml", "gitlab_ci"),
        ]

        for path, label in checks:
            if (cwd / path).exists():
                indicators.append(label)

        return indicators

    async def _detect_git_context(self) -> Dict[str, Any]:
        git_info = {
            "available": False,
            "is_repo": False,
            "branch": None,
            "commit": None,
            "staged": 0,
            "unstaged": 0,
            "remote_url": None,
            "root": None,
        }

        try:
            result = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    "git", "rev-parse", "--git-dir",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                ),
                timeout=2.0,
            )
            stdout, _ = await result.communicate()
            if result.returncode != 0:
                return git_info

            git_info["available"] = True
            git_info["is_repo"] = True

            root_result = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    "git", "rev-parse", "--show-toplevel",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                ),
                timeout=2.0,
            )
            stdout, _ = await root_result.communicate()
            if root_result.returncode == 0:
                git_info["root"] = stdout.decode().strip()

            branch_result = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    "git", "branch", "--show-current",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                ),
                timeout=2.0,
            )
            stdout, _ = await branch_result.communicate()
            if branch_result.returncode == 0:
                branch = stdout.decode().strip()
                if branch:
                    git_info["branch"] = branch
                else:
                    commit_result = await asyncio.wait_for(
                        asyncio.create_subprocess_exec(
                            "git", "rev-parse", "HEAD",
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                        ),
                        timeout=2.0,
                    )
                    stdout, _ = await commit_result.communicate()
                    if commit_result.returncode == 0:
                        git_info["commit"] = stdout.decode().strip()[:12]
                        git_info["branch"] = f"detached@{git_info['commit']}"

            status_result = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    "git", "status", "--porcelain",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                ),
                timeout=2.0,
            )
            stdout, _ = await status_result.communicate()
            if status_result.returncode == 0:
                lines = stdout.decode().strip().split("\n") if stdout.decode().strip() else []
                staged = 0
                unstaged = 0
                for line in lines:
                    if len(line) < 3:
                        continue
                    staged_flag = line[0]
                    unstaged_flag = line[1]
                    if staged_flag in ("M", "A", "D", "R", "C"):
                        staged += 1
                    if unstaged_flag in ("M", "A", "D", "?", "U"):
                        unstaged += 1
                git_info["staged"] = staged
                git_info["unstaged"] = unstaged

            remote_result = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    "git", "config", "--get", "remote.origin.url",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                ),
                timeout=2.0,
            )
            stdout, _ = await remote_result.communicate()
            if remote_result.returncode == 0:
                git_info["remote_url"] = stdout.decode().strip()

        except (asyncio.TimeoutError, FileNotFoundError, OSError):
            pass

        return git_info

    def _redact_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        git = context.get("git", {})
        if git.get("remote_url"):
            git["remote_url"] = redact_secrets(git["remote_url"])
            context["git"] = git

        if context.get("shell"):
            context["shell"] = redact_secrets(context["shell"])

        return context


_watcher_agent: Optional[WatcherAgent] = None


def get_watcher_agent() -> WatcherAgent:
    global _watcher_agent
    if _watcher_agent is None:
        _watcher_agent = WatcherAgent()
    return _watcher_agent