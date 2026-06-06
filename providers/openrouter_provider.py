import os
import json
from typing import Optional
from openai import AsyncOpenAI
from .base import AIProvider, ProviderError


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

        prompt = (
            "You are a command safety advisor. A user typed a potentially dangerous command. "
            "Provide safe alternatives that preserve the original intent.\n\n"
            f"Command: {command}\n"
            f"Risk Level: {risk_level}\n"
            f"Reason: {reason}\n\n"
            "Respond ONLY with valid JSON in this exact format:\n"
            '{"explanation": "plain language explanation", "alternatives": ["alt1", "alt2", "alt3"]}\n'
            "Maximum 3 alternatives. Never alter the user's original intent."
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

        raise ProviderError(f"All models failed. Last error: {last_error}", "openrouter")

    def is_available(self) -> bool:
        return bool(self.api_key)