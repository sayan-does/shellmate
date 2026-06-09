import os
from config.paths import get_cache_dir, get_log_dir, get_session_dir, get_state_dir

SHELLMATE_DIR = str(get_state_dir())


def get_default_config():
    return {
        "daemon": {
            "host": "127.0.0.1",
            "port": 9823,
            "socket_path": str(get_session_dir() / "shellmate.sock"),
            "pipe_name": r"\\.\pipe\shellmate",
        },
        "cache": {
            "enabled": True,
            "backend": "faiss",
            "model": "all-MiniLM-L6-v2",
            "similarity_threshold": 0.92,
            "expiration_days": 30,
            "max_entries": 10000,
            "directory": str(get_cache_dir()),
        },
        "providers": {
            "risk_analysis": {
                "primary": "groq",
                "model": "llama-3.3-70b-versatile",
                "fallback": None,
            },
            "remediation": {
                "primary": "openrouter",
                "model": "gpt-4o-mini",
                "fallbacks": [
                    "meta-llama/llama-3.3-70b-instruct",
                    "qwen/qwen2.5-72b-instruct",
                ],
            },
        },
        "latency_targets": {
            "cache_hit_ms": 200,
            "rule_match_ms": 50,
            "ai_analysis_ms": 5000,
        },
        "logging": {
            "level": "INFO",
            "directory": str(get_log_dir()),
            "max_bytes": 10485760,
            "backup_count": 5,
        },
        "supervisor": {
            "model": os.environ.get("GROQ_SUPERVISOR_MODEL", "llama-3.1-8b-instant"),
            "timeout_ms": 500,
        },
        "command_guide": {
            "model": os.environ.get("GROQ_COMMAND_GUIDE_MODEL", "llama-3.1-8b-instant"),
            "timeout_ms": int(os.environ.get("GROQ_COMMAND_GUIDE_TIMEOUT_MS", "2000")),
        },
        "plugins": {
            "directory": str(get_session_dir() / "plugins"),
            "enabled": True,
        },
        "overrides_file": str(get_session_dir() / "overrides.json"),
        "metrics_file": str(get_session_dir() / "metrics.json"),
    }