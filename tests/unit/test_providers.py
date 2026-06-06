import sys
import os
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from providers.base import AIProvider, ProviderError
from providers.groq_provider import GroqProvider
from providers.openrouter_provider import OpenRouterProvider
from providers.router import get_provider_status, analyze_risk, generate_remediation


class TestProviderBase:
    def test_ai_provider_abstract(self):
        import inspect
        assert inspect.isabstract(AIProvider)

    def test_provider_error(self):
        err = ProviderError("test error", "test_provider", 500)
        assert str(err) == "test error"
        assert err.provider == "test_provider"
        assert err.status_code == 500


class TestGroqProvider:
    def test_not_configured_without_key(self):
        if "GROQ_API_KEY" in os.environ:
            del os.environ["GROQ_API_KEY"]
        provider = GroqProvider()
        assert provider.is_available() is False

    @pytest.mark.asyncio
    async def test_not_configured_raises_error(self):
        if "GROQ_API_KEY" in os.environ:
            del os.environ["GROQ_API_KEY"]
        provider = GroqProvider()
        try:
            await provider.analyze_risk("test")
            assert False, "Should have raised ProviderError"
        except ProviderError as e:
            assert "GROQ_API_KEY" in str(e)


class TestOpenRouterProvider:
    def test_not_configured_without_key(self):
        if "OPENROUTER_API_KEY" in os.environ:
            del os.environ["OPENROUTER_API_KEY"]
        provider = OpenRouterProvider()
        assert provider.is_available() is False

    def test_fallback_models_configured(self):
        provider = OpenRouterProvider()
        assert len(provider.fallback_models) > 0


class TestRouter:
    def setup_method(self):
        self._orig_groq = os.environ.pop("GROQ_API_KEY", None)
        self._orig_openrouter = os.environ.pop("OPENROUTER_API_KEY", None)
        self._orig_context7 = os.environ.pop("CONTEXT7_API_KEY", None)

    def teardown_method(self):
        if self._orig_groq:
            os.environ["GROQ_API_KEY"] = self._orig_groq
        if self._orig_openrouter:
            os.environ["OPENROUTER_API_KEY"] = self._orig_openrouter
        if self._orig_context7:
            os.environ["CONTEXT7_API_KEY"] = self._orig_context7

    def test_provider_status(self):
        from config.credentials import load_env
        env = load_env()
        groq_configured = bool(env.get("GROQ_API_KEY"))
        status = get_provider_status()
        assert "groq" in status
        assert "openrouter" in status
        assert status["groq"]["configured"] is groq_configured

    @pytest.mark.asyncio
    async def test_fallback_risk_analysis(self):
        result = await analyze_risk("echo hello")
        assert result["provider"] == "fallback"
        assert "risk" in result
        assert "confidence" in result

    @pytest.mark.asyncio
    async def test_fallback_remediation(self):
        risk = {"risk": "HIGH", "message": "Test risk", "confidence": 0.9}
        result = await generate_remediation("rm -rf /", risk)
        assert "explanation" in result
        assert "alternatives" in result