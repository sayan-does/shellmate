import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from sanitizer.typo_detector import sanitize, normalize_whitespace, detect_trailing_char, detect_duplicate_flags, validate_syntax


class TestSanitizer:
    def test_normalize_whitespace(self):
        assert normalize_whitespace("  echo   hello  ") == "echo hello"
        assert normalize_whitespace("ls   -la") == "ls -la"

    def test_trailing_char_detection(self):
        result = detect_trailing_char("git push origin main,")
        assert result["detected"] is True
        assert result["trailing"] == ","
        assert result["suggestion"] == "git push origin main"

        result = detect_trailing_char("rm -rf /tmp")
        assert result["detected"] is False

    def test_duplicate_flags(self):
        result = detect_duplicate_flags(["rm", "-rf", "-rf", "/"])
        assert result["detected"] is True
        assert "-rf" in result["duplicates"]

        result = detect_duplicate_flags(["ls", "-la"])
        assert result["detected"] is False

    def test_syntax_validation(self):
        result = validate_syntax('echo "hello')
        assert result["valid"] is False
        assert len(result["errors"]) > 0

        result = validate_syntax("echo hello")
        assert result["valid"] is True

        result = validate_syntax("git commit -m 'message'")
        assert result["valid"] is True

    def test_sanitize_full(self):
        result = sanitize("  git push origin main,  ")
        assert result["normalized"] == "git push origin main,"
        assert result["trailing_char"]["detected"] is True
        assert result["correction"] == "git push origin main"
        assert result["syntax"]["valid"] is True

    def test_sanitize_no_issues(self):
        result = sanitize("ls -la")
        assert result["trailing_char"] is None or result["trailing_char"]["detected"] is False
        assert result["correction"] is None
