import os
import sys
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from config.paths import get_config_dir, get_state_dir, get_cache_dir, get_log_dir, get_session_dir
from config.manager import ConfigManager, get_config, get_config_value, set_config_value
from config.credentials import load_env, save_env, get_credential_status, get_api_key, CREDENTIAL_KEYS
from config.secrets import redact_secrets, redact_dict, sanitize_for_logging, sanitize_prompt


class TestConfigPaths:
    def test_get_config_dir(self):
        config_dir = get_config_dir()
        assert isinstance(config_dir, Path)
        assert config_dir.name == "shellmate" or config_dir.name == "ShellMate"

    def test_get_state_dir(self):
        state_dir = get_state_dir()
        assert isinstance(state_dir, Path)

    def test_get_cache_dir(self):
        cache_dir = get_cache_dir()
        assert isinstance(cache_dir, Path)

    def test_get_log_dir(self):
        log_dir = get_log_dir()
        assert isinstance(log_dir, Path)

    def test_get_session_dir(self):
        session_dir = get_session_dir()
        assert isinstance(session_dir, Path)


class TestConfigManager:
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_file = Path(self.temp_dir) / "config.yaml"
        self.orig_config_file = os.environ.get("SHELLMATE_CONFIG_FILE")

    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        if self.orig_config_file:
            os.environ["SHELLMATE_CONFIG_FILE"] = self.orig_config_file

    def test_load_default_config(self):
        manager = ConfigManager()
        config = manager.load()
        assert "daemon" in config
        assert "cache" in config
        assert "providers" in config
        assert "latency_targets" in config

    def test_deep_merge(self):
        manager = ConfigManager()
        base = {"a": {"b": 1, "c": 2}, "d": 3}
        override = {"a": {"b": 10}, "e": 4}
        result = manager._deep_merge(base, override)
        assert result["a"]["b"] == 10
        assert result["a"]["c"] == 2
        assert result["d"] == 3
        assert result["e"] == 4

    def test_get_config_value(self):
        manager = ConfigManager()
        manager._config = {"daemon": {"port": 9823}, "cache": {"enabled": True}}
        assert manager.get("daemon.port") == 9823
        assert manager.get("cache.enabled") is True
        assert manager.get("nonexistent.key", "default") == "default"

    def test_set_config_value(self):
        manager = ConfigManager()
        manager._config = {"daemon": {"port": 9823}}
        manager.set("daemon.port", 9999)
        assert manager.get("daemon.port") == 9999
        manager.set("new.key", "value")
        assert manager.get("new.key") == "value"


class TestCredentials:
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.env_file = Path(self.temp_dir) / ".env"
        self.orig_env_file = os.environ.get("SHELLMATE_ENV_FILE")
        # Clear any existing env file
        import config.credentials
        config.credentials.CREDENTIALS_FILE = self.env_file

    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        for key in CREDENTIAL_KEYS:
            if key in os.environ:
                del os.environ[key]
        import config.credentials
        from config.paths import CREDENTIALS_FILE as DEFAULT_CREDS_FILE
        config.credentials.CREDENTIALS_FILE = DEFAULT_CREDS_FILE

    def test_load_env_empty(self):
        import config.credentials
        config.credentials.CREDENTIALS_FILE = self.env_file
        env = load_env()
        assert env == {}

    def test_save_and_load_env(self):
        import config.credentials
        config.credentials.CREDENTIALS_FILE = self.env_file
        test_env = {"GROQ_API_KEY": "test-key-123", "OPENROUTER_API_KEY": "test-key-456"}
        save_env(test_env)
        loaded = load_env()
        assert loaded["GROQ_API_KEY"] == "test-key-123"
        assert loaded["OPENROUTER_API_KEY"] == "test-key-456"

    def test_get_credential_status(self):
        import config.credentials
        config.credentials.CREDENTIALS_FILE = self.env_file
        os.environ["GROQ_API_KEY"] = "env-key"
        save_env({"OPENROUTER_API_KEY": "file-key"})
        status = get_credential_status()
        assert status["GROQ_API_KEY"]["configured"] is True
        assert status["OPENROUTER_API_KEY"]["configured"] is True
        assert status["CONTEXT7_API_KEY"]["configured"] is False
        assert status["GROQ_API_KEY"]["masked"] is not None
        assert "*" in status["GROQ_API_KEY"]["masked"]

    def test_get_api_key_priority(self):
        save_env({"GROQ_API_KEY": "file-key"})
        os.environ["GROQ_API_KEY"] = "env-key"
        assert get_api_key("GROQ_API_KEY") == "env-key"
        del os.environ["GROQ_API_KEY"]
        assert get_api_key("GROQ_API_KEY") == "file-key"


class TestSecretsRedaction:
    def test_redact_api_key(self):
        text = 'api_key = "sk-1234567890abcdef"'
        result = redact_secrets(text)
        assert "****" in result
        assert "sk-1234567890abcdef" not in result

    def test_redact_bearer_token(self):
        text = 'Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9'
        result = redact_secrets(text)
        assert "****" in result
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result

    def test_redact_ssh_key(self):
        text = 'ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC...'
        result = redact_secrets(text)
        assert "****" in result

    def test_redact_email(self):
        text = 'user@example.com'
        result = redact_secrets(text)
        assert "****@****" == result

    def test_redact_dict(self):
        data = {
            "api_key": "secret123",
            "normal_key": "value",
            "nested": {"token": "secret456", "other": "data"},
            "list": [{"password": "pass123"}, "plain"]
        }
        result = redact_dict(data)
        assert result["api_key"] == "****"
        assert result["normal_key"] == "value"
        assert result["nested"]["token"] == "****"
        assert result["nested"]["other"] == "data"
        assert result["list"][0]["password"] == "****"
        assert result["list"][1] == "plain"

    def test_sanitize_for_logging(self):
        data = {
            "command": "curl -H 'Authorization: Bearer token123' example.com",
            "api_key": "sk-secret",
            "normal": "value"
        }
        result = sanitize_for_logging(data)
        assert "****" in result["command"]
        assert result["api_key"] == "****"
        assert result["normal"] == "value"

    def test_sanitize_prompt(self):
        prompt = "API key is sk-1234567890abcdef and token is ghp_1234567890abcdef"
        result = sanitize_prompt(prompt)
        assert "****" in result
        assert "sk-1234567890abcdef" not in result
        assert "ghp_1234567890abcdef" not in result


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])