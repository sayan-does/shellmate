import os
import json
from typing import Optional
from groq import Groq
from .base import AIProvider, ProviderError


class GroqProvider(AIProvider):
    def __init__(self):
        self.api_key = os.environ.get("GROQ_API_KEY")
        self.client = None
        self.model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

    def _ensure_client(self):
        if not self.api_key:
            raise ProviderError("GROQ_API_KEY environment variable not set", "groq")
        if self.client is None:
            self.client = Groq(api_key=self.api_key)

    def analyze_risk(self, command: str, context: Optional[dict] = None) -> dict:
        self._ensure_client()

        prompt = (
            "You are a command safety analyzer. Analyze the following shell command and classify its risk level. "
            "Respond ONLY with valid JSON in this exact format:\n"
            '{"risk": "SAFE|LOW|MEDIUM|HIGH|CRITICAL", "confidence": 0.0-1.0, "reason": "brief explanation"}\n\n'
            f"Command: {command}"
        )

        try:
            response = self.client.chat.completions.create(
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
        except Exception as e:
            raise ProviderError(str(e), "groq")

    def generate_remediation(self, command: str, risk: dict, context: Optional[dict] = None) -> dict:
        raise NotImplementedError("Groq provider only handles risk analysis")

    def is_available(self) -> bool:
        return bool(self.api_key)
