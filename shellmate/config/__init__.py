from shellmate.config.defaults import get_default_config, SHELLMATE_DIR
from shellmate.config.credentials import (
    CREDENTIAL_KEYS,
    load_env,
    save_env,
    get_credential_status,
    get_api_key,
    export_script,
)
from shellmate.config.manager import get_config, get_config_value, set_config_value, get_config_manager
from shellmate.config.secrets import redact_secrets, redact_dict, sanitize_for_logging, sanitize_prompt, sanitize_response

__all__ = [
    "get_default_config",
    "SHELLMATE_DIR",
    "CREDENTIAL_KEYS",
    "load_env",
    "save_env",
    "get_credential_status",
    "get_api_key",
    "export_script",
    "get_config",
    "get_config_value",
    "set_config_value",
    "get_config_manager",
    "redact_secrets",
    "redact_dict",
    "sanitize_for_logging",
    "sanitize_prompt",
    "sanitize_response",
]