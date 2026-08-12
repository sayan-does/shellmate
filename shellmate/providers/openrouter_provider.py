import os
import json
from typing import Optional
from openai import AsyncOpenAI
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


class OpenRouterProvider(AIProvider):
    def __init__(self):
        self.api_key = os.environ.get("OPENROUTER_API_KEY")
        self.client = None
        self.base_url = "https://openrouter.ai/api/v1"
        self.primary_model = os.environ.get("OPENROUTER_PRIMARY_MODEL", "gpt-4o-mini")
        self.fallback_models = [
            "meta-llama/llama-3.3-70b-instruct",
            "qwen/qwen2.5-72b-instruct",
        ]

    def _ensure_client(self):
        if not self.api_key:
            raise ProviderError("OPENROUTER_API_KEY environment variable not set", "openrouter")
        if self.client is None:
            self.client = AsyncOpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
            )

    async def analyze_risk(self, command: str, context: Optional[dict] = None) -> dict:
        raise NotImplementedError("OpenRouter provider only handles remediation")

    async def generate_remediation(self, command: str, risk: dict, context: Optional[dict] = None) -> dict:
        self._ensure_client()

        risk_level = risk.get("risk", risk.get("severity", "UNKNOWN"))
        reason = risk.get("reason", risk.get("message", "No reason provided"))

        context_str = _format_context(context)
        risk_upper = str(risk_level).upper()
        if risk_upper in ("SAFE", "LOW"):
            advisor_role = (
                "You are a helpful shell command advisor. The user's command is low risk. "
                "They likely need usage help: explain what they might be trying to do, "
                "what each argument likely means, and suggest a corrected command using context."
            )
            alt_hint = (
                'Start alternatives with "Maybe you\'re trying to..." then parameter notes, '
                'then "Try: <corrected command>".'
            )
        else:
            advisor_role = (
                "You are a command safety advisor. A user typed a potentially dangerous command. "
                "Provide safe alternatives that preserve the original intent."
            )
            alt_hint = "Maximum 3 safer alternatives. Never alter the user's original intent."

        prompt = (
            f"{advisor_role}\n\n"
            f"Command: {command}\n"
            f"Risk Level: {risk_level}\n"
            f"Reason: {reason}"
            f"{context_str}\n\n"
            "Respond ONLY with valid JSON in this exact format:\n"
            '{"explanation": "plain language explanation", "alternatives": ["alt1", "alt2", "alt3"]}\n'
            f"{alt_hint}"
        )

        models_to_try = [self.primary_model] + self.fallback_models
        last_error = None

        for model in models_to_try:
            try:
                response = await self.client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=512,
                )

                content = response.choices[0].message.content.strip()
                if content.startswith("```"):
                    content = content.split("\n", 1)[1] if "\n" in content else content
                    if content.endswith("```"):
                        content = content[:-3]
                    content = content.strip()

                result = json.loads(content)
                result["provider"] = "openrouter"
                result["model"] = model
                return result

            except Exception as e:
                last_error = e
                continue

        from .base import wrap_provider_exception

        wrapped = wrap_provider_exception(last_error or Exception("unknown"), "openrouter")
        raise ProviderError(
            f"All models failed. Last error: {wrapped}",
            "openrouter",
            status_code=wrapped.status_code,
        )

    async def close(self):
        if self.client is not None:
            await self.client.aclose()
            self.client = None

    def is_available(self) -> bool:
        return bool(self.api_key)