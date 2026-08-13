import os
import json
import asyncio
from typing import Optional
from openai import AsyncOpenAI
from .base import AIProvider, ProviderError
from .groq_provider import _format_context


class XaiProvider(AIProvider):
    """Grok (xAI) provider — OpenAI-compatible API for risk and remediation."""

    def __init__(self):
        self.api_key = os.environ.get("XAI_API_KEY")
        self.client = None
        self.base_url = "https://api.x.ai/v1"
        self.model = os.environ.get("XAI_MODEL", "grok-3-mini")

    def _ensure_client(self):
        if not self.api_key:
            raise ProviderError("XAI_API_KEY environment variable not set", "xai")
        if self.client is None:
            self.client = AsyncOpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
            )

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
            result["provider"] = "xai"
            result["model"] = self.model
            return result

        except json.JSONDecodeError as e:
            raise ProviderError(f"Invalid JSON response: {e}", "xai")
        except ProviderError:
            raise
        except Exception as e:
            from .base import wrap_provider_exception
            raise wrap_provider_exception(e, "xai")

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

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
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
            result["provider"] = "xai"
            result["model"] = self.model
            return result

        except json.JSONDecodeError as e:
            raise ProviderError(f"Invalid JSON response: {e}", "xai")
        except ProviderError:
            raise
        except Exception as e:
            from .base import wrap_provider_exception
            raise wrap_provider_exception(e, "xai")

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
