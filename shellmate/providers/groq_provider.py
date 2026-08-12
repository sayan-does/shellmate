import os
import json
import asyncio
from typing import Optional
from groq import AsyncGroq
from .base import AIProvider, ProviderError


def _format_context(context: Optional[dict]) -> str:
    if not context:
        return ""
    parts = []
    watcher = context.get("watcher", {})
    if watcher:
        parts.append("System Context:")
        if watcher.get("os"):
            parts.append(f"  OS: {watcher['os']}")
        if watcher.get("shell"):
            parts.append(f"  Shell: {watcher['shell']}")
        if watcher.get("current_directory"):
            parts.append(f"  Directory: {watcher['current_directory']}")
        git = watcher.get("git_context")
        if git:
            git_parts = []
            if git.get("branch"):
                git_parts.append(f"branch={git['branch']}")
            if git.get("staged"):
                git_parts.append(f"staged={git['staged']}")
            if git.get("unstaged"):
                git_parts.append(f"unstaged={git['unstaged']}")
            if git_parts:
                parts.append(f"  Git: {', '.join(git_parts)}")
        stack = watcher.get("tech_stack")
        if stack:
            parts.append(f"  Tech stack: {', '.join(stack[:5])}")
    librarian = context.get("librarian", {})
    if librarian and librarian.get("matches"):
        parts.append("\nRelevant project files:")
        for m in librarian["matches"][:3]:
            path = m.get("file", m.get("path", "?"))
            snippet = m.get("content", m.get("snippet", ""))[:200]
            parts.append(f"  - {path}: {snippet}")
    if not parts:
        return ""
    return "\n" + "\n".join(parts)


class GroqProvider(AIProvider):
    def __init__(self):
        self.api_key = os.environ.get("GROQ_API_KEY")
        self.client = None
        self.model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

    def _ensure_client(self):
        if not self.api_key:
            raise ProviderError("GROQ_API_KEY environment variable not set", "groq")
        if self.client is None:
            self.client = AsyncGroq(api_key=self.api_key)

    async def analyze_risk(self, command: str, context: Optional[dict] = None) -> dict:
        self._ensure_client()

        context_str = _format_context(context)
        prompt = (
            "You are a command safety analyzer. Analyze the following shell command and classify its risk level. "
            "Respond ONLY with valid JSON in this exact format:\n"
            '{"risk": "SAFE|LOW|MEDIUM|HIGH|CRITICAL", "confidence": 0.0-1.0, "reason": "brief explanation"}\n\n'
            f"Command: {command}"
            f"{context_str}"
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=256,
            )

            content = response.choices[0].message.content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1] if "\n" in content else content
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()

            result = json.loads(content)
            result["provider"] = "groq"
            result["model"] = self.model
            return result

        except json.JSONDecodeError as e:
            raise ProviderError(f"Invalid JSON response: {e}", "groq")
        except ProviderError:
            raise
        except Exception as e:
            from .base import wrap_provider_exception
            raise wrap_provider_exception(e, "groq")

    async def generate_remediation(self, command: str, risk: dict, context: Optional[dict] = None) -> dict:
        raise NotImplementedError("Groq provider only handles risk analysis")

    async def close(self):
        if self.client is not None:
            close = getattr(self.client, "aclose", None) or getattr(self.client, "close", None)
            if close:
                result = close()
                if asyncio.iscoroutine(result):
                    await result
            self.client = None

    def is_available(self) -> bool:
        return bool(self.api_key)