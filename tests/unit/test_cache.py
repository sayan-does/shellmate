import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from cache.semantic_cache import generate_embedding, cache_lookup, cache_store, clear_cache


class TestCache:
    def setup_method(self):
        clear_cache()

    def test_embedding_generation(self):
        embedding = generate_embedding("rm -rf /tmp/test")
        assert len(embedding) == 384

    def test_cache_store_and_lookup(self):
        result = {"risk": "HIGH", "confidence": 0.97, "message": "Test", "alternatives": []}
        cache_store("rm -rf /tmp/test", result)
        cached = cache_lookup("rm -rf /tmp/test")
        assert cached is not None
        assert cached["risk"] == "HIGH"
        assert cached["cached"] is True

    def test_cache_miss_for_new_command(self):
        clear_cache()
        result = {"risk": "HIGH", "confidence": 0.97, "message": "Test", "alternatives": []}
        cache_store("ls -la", result)
        cached = cache_lookup("some_other_command")
        assert cached is None

    def test_cache_clear(self):
        result = {"risk": "LOW", "confidence": 0.5, "message": "Test", "alternatives": []}
        cache_store("echo hello", result)
        clear_cache()
        cached = cache_lookup("echo hello")
        assert cached is None
