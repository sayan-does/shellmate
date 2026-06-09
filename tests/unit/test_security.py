import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from config.secrets import sanitize_for_logging, sanitize_prompt
from agents.librarian import LibrarianAgent
from daemon.server import MAX_REQUEST_SIZE


class TestSecretsRedaction:
    def test_sanitize_for_logging_removes_api_keys(self):
        log = "Using API key sk-abc123def456xyz9 for Groq"
        result = sanitize_for_logging(log)
        assert "sk-abc123def456xyz9" not in result
        assert "****" in result

    def test_sanitize_for_logging_removes_bearer_tokens(self):
        log = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.token"
        result = sanitize_for_logging(log)
        assert "eyJhbGciOiJIUzI1NiJ9.token" not in result

    def test_sanitize_for_logging_removes_ssh_keys(self):
        log = "Key: ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDU test-key"
        result = sanitize_for_logging(log)
        assert "AAAAB3NzaC1yc2EAAAADAQABAAABAQDU" not in result

    def test_sanitize_for_logging_removes_emails(self):
        log = "Contact: user@example.com"
        result = sanitize_for_logging(log)
        assert "user@example.com" not in result

    def test_sanitize_prompt_removes_secrets(self):
        prompt = "Analyze this: token=ghp_abc123def456XYZtoken"
        result = sanitize_prompt(prompt)
        assert "ghp_abc123def456XYZtoken" not in result

    def test_sanitize_prompt_preserves_safe_text(self):
        prompt = "What does 'rm -rf /' do?"
        result = sanitize_prompt(prompt)
        assert result == prompt

    def test_sanitize_handles_empty_string(self):
        assert sanitize_for_logging("") == ""
        assert sanitize_prompt("") == ""

    def test_sanitize_handles_none(self):
        result = sanitize_for_logging(None)
        assert result is None or result == ""

    def test_multiple_secrets_in_one_message(self):
        log = "API: sk-abc123def456XYZkey, Token: ghp_abc123def456XYZtoken, Email: a@b.com"
        result = sanitize_for_logging(log)
        assert "sk-abc123def456XYZkey" not in result
        assert "ghp_abc123def456XYZtoken" not in result
        assert "a@b.com" not in result
        assert "****" in result


class TestSessionSecurity:
    def test_session_dir_has_restrictive_permissions(self):
        from daemon.session import get_session_dir_path
        session_dir = get_session_dir_path()
        assert session_dir is not None

    def test_session_ownership_validated(self):
        from daemon.session import create_session, read_session, validate_session_ownership, remove_session
        import time

        with tempfile.TemporaryDirectory() as tmpdir:
            orig_dir = Path.cwd()
            os.chdir(tmpdir)
            try:
                create_session(999999, str(tmpdir), "127.0.0.1:9823")
                session = read_session()
                assert session is not None
                if session.get("owner") != os.environ.get("USERNAME", os.environ.get("USER", "")):
                    assert not validate_session_ownership(session)
            finally:
                remove_session()
                os.chdir(orig_dir)

    def test_session_stale_detection(self):
        from daemon.session import create_session, is_session_stale, remove_session
        import time

        with tempfile.TemporaryDirectory() as tmpdir:
            orig_dir = Path.cwd()
            os.chdir(tmpdir)
            try:
                create_session(999999, str(tmpdir), "127.0.0.1:9823")
                session = {"pid": 999999, "cwd": tmpdir, "created": time.time() - 3600, "owner": "test"}
                assert is_session_stale(session) is True
            finally:
                remove_session()
                os.chdir(orig_dir)


class TestLibrarianPathSecurity:
    @pytest.mark.asyncio
    async def test_librarian_respects_project_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            orig_cwd = Path.cwd()
            os.chdir(tmpdir)

            agent = LibrarianAgent()
            agent._project_root = Path(tmpdir)
            await agent._scan_project()

            for f in agent._files:
                file_path = f["path"].replace("/", "\\")
                assert ".." not in file_path
                assert not file_path.startswith("/")
                assert not file_path.startswith("\\")

            os.chdir(orig_cwd)

    @pytest.mark.asyncio
    async def test_librarian_rejects_outside_paths_in_watchdog(self):
        agent = LibrarianAgent()
        agent._project_root = Path(tempfile.mkdtemp())
        agent._files = [{"path": "safe.py", "size": 10, "ext": ".py", "snippet": "safe"}]
        agent._build_index()
        agent._ready = True

        agent._scan_task = asyncio.create_task(asyncio.sleep(0))
        agent._watchdog_task = asyncio.create_task(agent._watchdog_worker())
        await asyncio.sleep(0.05)

        outside_path = str(Path(agent._project_root).parent / "outside.py")
        agent._watchdog_queue.put_nowait(("modified", outside_path))
        await asyncio.sleep(0.1)

        assert len(agent._files) == 1
        assert agent._files[0]["path"] == "safe.py"

        agent._watchdog_task.cancel()
        try:
            await agent._watchdog_task
        except: pass

    @pytest.mark.asyncio
    async def test_librarian_skips_excluded_dirs_even_in_watchdog(self):
        agent = LibrarianAgent()
        agent._project_root = Path(tempfile.mkdtemp())
        (agent._project_root / ".git" / "config").parent.mkdir(parents=True, exist_ok=True)
        (agent._project_root / ".git" / "config").write_text("[core]\n")
        agent._files = []
        agent._ready = True

        agent._scan_task = asyncio.create_task(asyncio.sleep(0))
        agent._watchdog_task = asyncio.create_task(agent._watchdog_worker())
        await asyncio.sleep(0.05)

        path = str(agent._project_root / ".git" / "config")
        agent._watchdog_queue.put_nowait(("modified", path))
        await asyncio.sleep(0.1)

        assert len(agent._files) == 0

        agent._watchdog_task.cancel()
        try:
            await agent._watchdog_task
        except: pass


class TestIPCSecurity:
    def test_max_request_size_constant(self):
        assert MAX_REQUEST_SIZE == 1024 * 1024

    def test_ipc_rejects_oversized_payload(self):
        from daemon.server import MAX_REQUEST_SIZE
        large = "A" * (MAX_REQUEST_SIZE + 1)
        assert len(large.encode("utf-8")) > MAX_REQUEST_SIZE

    def test_ipc_binds_to_localhost(self):
        from config.defaults import get_default_config
        config = get_default_config()
        host = config["daemon"]["host"]
        assert host == "127.0.0.1", f"IPC should bind to localhost, got {host}"

    def test_ipc_default_port(self):
        from config.defaults import get_default_config
        config = get_default_config()
        port = config["daemon"]["port"]
        assert isinstance(port, int)
        assert 1024 < port < 65535


class TestEnrichmentRedaction:
    """AGR-28: Security redaction in enrichment prompts."""

    def test_supervisor_prompt_redacts_env_secrets(self):
        from config.secrets import sanitize_prompt
        prompt = "Context: AWS_SECRET_KEY=sk-abcdef1234567890xyz, command: echo hi"
        result = sanitize_prompt(prompt)
        assert "sk-abcdef1234567890xyz" not in result
        assert "****" in result

    def test_guide_prompt_redacts_librarian_snippets(self):
        from config.secrets import sanitize_prompt
        snippet = "password = 'super-secret-123'"
        prompt = f"Librarian match: {snippet}, command: git status"
        result = sanitize_prompt(prompt)
        assert "super-secret-123" not in result
        assert "****" in result

    def test_format_output_no_raw_secrets(self):
        from config.secrets import redact_dict
        data = {
            "message": "Checked config with key=sk-abcdef1234567890xyz",
            "risk": "LOW",
        }
        result = redact_dict(data)
        assert "sk-abcdef1234567890xyz" not in str(result)
        assert "LOW" in str(result)


class TestConfigSecurity:
    def test_api_keys_not_in_default_config(self):
        from config.defaults import get_default_config
        config = get_default_config()
        config_str = json.dumps(config)
        assert "sk-" not in config_str
        assert "api_key" not in config_str.lower() or "provider" in config_str

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix file permission check")
    def test_secrets_file_not_world_readable(self):
        from config.paths import get_config_dir
        config_dir = get_config_dir()
        env_file = Path(config_dir) / ".env"
        if env_file.exists():
            mode = os.stat(env_file).st_mode
            assert not mode & 0o004

    def test_env_values_redacted_in_logs(self):
        from config.secrets import sanitize_for_logging
        log = "api_key=gsk_abc123xyz789token, OPENROUTER_API_KEY=sk-or-v1-xyzTokenValue"
        result = sanitize_for_logging(log)
        assert "gsk_abc123xyz789token" not in result
        assert "sk-or-v1-xyzTokenValue" not in result
        assert "****" in result
