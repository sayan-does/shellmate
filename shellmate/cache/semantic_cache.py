"""Exact-match command cache. Replaces FAISS semantic cache."""

import threading
from datetime import datetime, timedelta

_lock = threading.Lock()
_store: dict = {}
_EXPIRY_DAYS = 7
_MAX_ENTRIES = 500


def cache_lookup(command: str):
    with _lock:
        entry = _store.get(command)
        if entry is None:
            return None
        if datetime.now() - entry["ts"] > timedelta(days=_EXPIRY_DAYS):
            del _store[command]
            return None
        return {**entry["result"], "cached": True}


def cache_store(command: str, result: dict):
    with _lock:
        if len(_store) >= _MAX_ENTRIES:
            oldest = min(_store, key=lambda k: _store[k]["ts"])
            del _store[oldest]
        _store[command] = {"result": result, "ts": datetime.now()}


def preload_embedder_async():
    pass


def clear_cache():
    with _lock:
        _store.clear()
