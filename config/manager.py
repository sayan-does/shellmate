import os
import yaml
from pathlib import Path
from typing import Any, Dict, Optional
from config.paths import CONFIG_FILE, CREDENTIALS_FILE, ensure_dirs, get_cache_dir, get_log_dir, get_session_dir
from config.defaults import get_default_config


class ConfigManager:
    def __init__(self):
        self._config: Optional[Dict[str, Any]] = None

    def load(self) -> Dict[str, Any]:
        if self._config is not None:
            return self._config

        ensure_dirs()
        config = get_default_config()

        config["cache"]["directory"] = str(get_cache_dir())
        config["logging"]["directory"] = str(get_log_dir())
        config["session_dir"] = str(get_session_dir())

        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r") as f:
                    user_config = yaml.safe_load(f) or {}
                config = self._deep_merge(config, user_config)
            except (yaml.YAMLError, OSError):
                pass

        self._config = config
        return config

    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def save(self, config: Dict[str, Any]) -> None:
        ensure_dirs()
        with open(CONFIG_FILE, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        self._config = config

    def get(self, key: str, default=None) -> Any:
        config = self.load()
        keys = key.split(".")
        value = config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value

    def set(self, key: str, value: Any) -> None:
        config = self.load()
        keys = key.split(".")
        target = config
        for k in keys[:-1]:
            if k not in target:
                target[k] = {}
            target = target[k]
        target[keys[-1]] = value
        self.save(config)


_config_manager = None


def get_config_manager() -> ConfigManager:
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


def get_config() -> Dict[str, Any]:
    return get_config_manager().load()


def get_config_value(key: str, default=None) -> Any:
    return get_config_manager().get(key, default)


def set_config_value(key: str, value: Any) -> None:
    get_config_manager().set(key, value)