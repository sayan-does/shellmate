import os

SHELLMATE_DIR = os.path.expanduser("~/.shellmate")


def get_default_config():
    return {
        "daemon": {
            "host": "127.0.0.1",
            "port": 9823,
            "socket_path": os.path.join(SHELLMATE_DIR, "shellmate.sock"),
            "pipe_name": r"\\.\pipe\shellmate",
        },
        "cache": {
            "enabled": True,
            "backend": "faiss",
            "model": "all-MiniLM-L6-v2",
            "similarity_threshold": 0.92,
            "expiration_days": 30,
            "max_entries": 10000,
            "directory": os.path.join(SHELLMATE_DIR, "cache"),
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
            "directory": os.path.join(SHELLMATE_DIR, "logs"),
            "max_bytes": 10485760,
            "backup_count": 5,
        },
        "plugins": {
            "directory": os.path.join(SHELLMATE_DIR, "plugins"),
            "enabled": True,
        },
        "overrides_file": os.path.join(SHELLMATE_DIR, "overrides.json"),
        "metrics_file": os.path.join(SHELLMATE_DIR, "metrics.json"),
    }
