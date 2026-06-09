"""E2E tests for ShellMate configuration flow with real API keys."""

import pytest
import subprocess
import json
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from config.paths import CREDENTIALS_FILE, CONFIG_FILE
from config.credentials import load_env, save_env, CREDENTIAL_KEYS, get_credential_status
from config.manager import get_config


TEST_CREDENTIALS = {
    "GROQ_API_KEY": os.environ.get("GROQ_API_KEY", "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"),
    "OPENROUTER_API_KEY": os.environ.get("OPENROUTER_API_KEY", "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"),
    "CONTEXT7_API_KEY": os.environ.get("CONTEXT7_API_KEY", "ctx7sk-b953fdd4-b260-4836-a7d9-f7a56da21104"),
}

VALID_GROQ_KEY = TEST_CREDENTIALS["GROQ_API_KEY"]
VALID_OPENROUTER_KEY = TEST_CREDENTIALS["OPENROUTER_API_KEY"]
VALID_CONTEXT7_KEY = TEST_CREDENTIALS["CONTEXT7_API_KEY"]


def run_cli(*args, timeout=30):
    """Helper to run CLI commands"""
    env = os.environ.copy()
    env["SM_NONINTERACTIVE"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "cli.main", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


@pytest.fixture(autouse=True)
def clean_credentials():
    """Save and restore credentials around each test."""
    old_creds = load_env()
    old_config = None
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r") as f:
            old_config = f.read()

    for key in list(os.environ.keys()):
        if key in CREDENTIAL_KEYS:
            os.environ.pop(key, None)

    save_env({})

    from config.manager import get_config_manager
    get_config_manager()._config = None

    import providers.router as pr
    pr._groq_provider = None
    pr._openrouter_provider = None

    yield

    save_env(old_creds)
    if old_config is not None:
        with open(CONFIG_FILE, "w") as f:
            f.write(old_config)

    for key in list(os.environ.keys()):
        if key in CREDENTIAL_KEYS:
            os.environ.pop(key, None)


class TestConfigDisplay:
    """Test config display command shows credentials correctly."""

    def test_config_displays_credential_keys(self):
        result = run_cli("config", timeout=10)
        assert result.returncode == 0
        assert "GROQ_API_KEY" in result.stdout
        assert "OPENROUTER_API_KEY" in result.stdout
        assert "CONTEXT7_API_KEY" in result.stdout
        assert "ShellMate Configuration" in result.stdout

    def test_config_shows_not_set_for_missing_keys(self):
        result = run_cli("config", timeout=10)
        assert result.returncode == 0
        assert "not set" in result.stdout or "False" in result.stdout

    def test_config_shows_configured_after_setting_keys(self):
        save_env({
            "GROQ_API_KEY": VALID_GROQ_KEY,
            "OPENROUTER_API_KEY": VALID_OPENROUTER_KEY,
            "CONTEXT7_API_KEY": VALID_CONTEXT7_KEY,
        })
        result = run_cli("config", timeout=10)
        assert result.returncode == 0
        assert "True" in result.stdout

    def test_config_show_command_masks_keys(self):
        save_env({
            "GROQ_API_KEY": VALID_GROQ_KEY,
            "OPENROUTER_API_KEY": VALID_OPENROUTER_KEY,
            "CONTEXT7_API_KEY": VALID_CONTEXT7_KEY,
        })
        result = run_cli("config", "--show", timeout=10)
        assert result.returncode == 0
        assert "GROQ_API_KEY" in result.stdout or "Groq" in result.stdout
        assert VALID_GROQ_KEY[:4] in result.stdout
        assert VALID_GROQ_KEY[4:-4] not in result.stdout

    def test_credentials_not_leaked_in_output(self):
        save_env({
            "GROQ_API_KEY": VALID_GROQ_KEY,
            "OPENROUTER_API_KEY": VALID_OPENROUTER_KEY,
            "CONTEXT7_API_KEY": VALID_CONTEXT7_KEY,
        })
        result = run_cli("config", timeout=10)
        assert VALID_GROQ_KEY not in result.stdout
        assert VALID_OPENROUTER_KEY not in result.stdout
        assert VALID_CONTEXT7_KEY not in result.stdout

    def test_config_displays_providers_section(self):
        result = run_cli("config", timeout=10)
        assert result.returncode == 0
        assert "risk_analysis" in result.stdout or "remediation" in result.stdout
        assert "groq" in result.stdout.lower() or "openrouter" in result.stdout.lower()

    def test_config_displays_settings(self):
        result = run_cli("config", timeout=10)
        assert result.returncode == 0
        assert "daemon" in result.stdout
        assert "cache" in result.stdout
        assert "Settings" in result.stdout or "daemon:" in result.stdout


class TestConfigCredentialManagement:
    """Test credential management via CLI."""

    def test_set_credential_via_cli(self):
        result = run_cli("config", "GROQ_API_KEY", VALID_GROQ_KEY, timeout=10)
        assert result.returncode == 0
        assert "Updated GROQ_API_KEY" in result.stdout

        creds = load_env()
        assert creds.get("GROQ_API_KEY") == VALID_GROQ_KEY

    def test_set_all_credentials_via_cli(self):
        for key, value in TEST_CREDENTIALS.items():
            result = run_cli("config", key, value, timeout=10)
            assert result.returncode == 0
            assert f"Updated {key}" in result.stdout

        creds = load_env()
        for key, value in TEST_CREDENTIALS.items():
            assert creds.get(key) == value

    def test_credentials_persist_in_env_file(self):
        save_env(TEST_CREDENTIALS)
        assert CREDENTIALS_FILE.exists()
        content = CREDENTIALS_FILE.read_text()
        for key in TEST_CREDENTIALS:
            assert key in content

    def test_credential_status_reflects_configuration(self):
        status_before = get_credential_status()
        assert all(not v["configured"] for v in status_before.values())

        save_env(TEST_CREDENTIALS)
        status_after = get_credential_status()
        assert all(v["configured"] for v in status_after.values())

    def test_get_api_key_returns_correct_value(self):
        from config.credentials import get_api_key
        save_env(TEST_CREDENTIALS)
        assert get_api_key("GROQ_API_KEY") == VALID_GROQ_KEY
        assert get_api_key("OPENROUTER_API_KEY") == VALID_OPENROUTER_KEY
        assert get_api_key("CONTEXT7_API_KEY") == VALID_CONTEXT7_KEY

    def test_masked_key_format(self):
        from config.credentials import _mask_key
        masked = _mask_key(VALID_GROQ_KEY)
        assert masked.startswith(VALID_GROQ_KEY[:4])
        assert masked.endswith(VALID_GROQ_KEY[-4:])
        assert "*" in masked
        assert VALID_GROQ_KEY[4:-4] not in masked

    def test_unknown_config_key_shows_error(self):
        result = run_cli("config", "UNKNOWN_KEY", "value", timeout=10)
        assert result.returncode == 0
        assert "Unknown config key" in result.stdout

    def test_dotted_notation_config_set(self):
        result = run_cli("config", "cache.similarity_threshold", "0.95", timeout=10)
        assert result.returncode == 0
        assert "CACHE.SIMILARITY_THRESHOLD" in result.stdout or "cache.similarity_threshold" in result.stdout


class TestCredentialsFilePermissions:
    """Test credentials file permissions (Unix-only)."""

    @pytest.mark.skipif(sys.platform == "win32", reason="Permission tests Unix-only")
    def test_credentials_file_restrictive_permissions(self):
        save_env(TEST_CREDENTIALS)
        import stat
        mode = os.stat(CREDENTIALS_FILE).st_mode
        assert mode & (stat.S_IRWXG | stat.S_IRWXO) == 0

    def test_credentials_file_exists_after_save(self):
        save_env(TEST_CREDENTIALS)
        assert CREDENTIALS_FILE.exists()
        assert CREDENTIALS_FILE.stat().st_size > 0


class TestConfigDottedNotation:
    """Test reading/writing config with dotted notation."""

    def test_read_config_value_dotted(self):
        from config.manager import get_config_value, get_config_manager
        if CONFIG_FILE.exists():
            CONFIG_FILE.unlink()
        get_config_manager()._config = None
        val = get_config_value("daemon.port")
        assert val == 9823

    def test_set_and_read_config_value(self):
        from config.manager import set_config_value, get_config_value
        set_config_value("daemon.port", 9999)
        assert get_config_value("daemon.port") == 9999

    def test_default_config_values_present(self):
        cfg = get_config()
        assert cfg["cache"]["similarity_threshold"] == 0.92
        assert cfg["cache"]["max_entries"] == 10000
        assert cfg["latency_targets"]["ai_analysis_ms"] == 5000
        assert cfg["latency_targets"]["cache_hit_ms"] == 200

    def test_config_file_persists_setting(self):
        from config.manager import set_config_value, get_config_manager
        set_config_value("cache.similarity_threshold", 0.99)
        get_config_manager()._config = None
        cfg = get_config()
        assert cfg["cache"]["similarity_threshold"] == 0.99


class TestProviderConfig:
    """Test provider configuration via config system."""

    def test_default_provider_config(self):
        cfg = get_config()
        providers = cfg.get("providers", {})
        ra = providers.get("risk_analysis", {})
        rem = providers.get("remediation", {})
        assert ra.get("primary") == "groq"
        assert rem.get("primary") == "openrouter"

    def test_provider_status_with_keys(self):
        import providers.router as pr
        pr._groq_provider = None
        pr._openrouter_provider = None
        save_env(TEST_CREDENTIALS)
        status = pr.get_provider_status()
        assert "groq" in status
        assert "openrouter" in status
        assert status["groq"]["configured"]
        assert status["openrouter"]["configured"]

    def test_provider_status_without_keys(self):
        import providers.router as pr
        pr._groq_provider = None
        pr._openrouter_provider = None
        save_env({})
        status = pr.get_provider_status()
        assert not status["groq"]["configured"]
        assert not status["openrouter"]["configured"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
