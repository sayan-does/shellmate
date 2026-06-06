import os
import sys
import json
import tempfile
import time
import shutil
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from daemon.session import (
    create_session, read_session, remove_session,
    cleanup_stale_sessions, validate_session_ownership,
    get_session_dir_path, is_process_alive, write_session_atomic,
    get_owner_identity, is_session_stale, SESSION_FILE
)


class TestSession:
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.orig_session_dir = os.environ.get("SHELLMATE_SESSION_DIR")
        os.environ["SHELLMATE_SESSION_DIR"] = self.temp_dir

    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        if self.orig_session_dir:
            os.environ["SHELLMATE_SESSION_DIR"] = self.orig_session_dir
        else:
            os.environ.pop("SHELLMATE_SESSION_DIR", None)

    def test_get_session_dir(self):
        session_dir = get_session_dir_path()
        assert isinstance(session_dir, Path)

    def test_get_owner_identity(self):
        owner = get_owner_identity()
        assert isinstance(owner, str)
        assert len(owner) > 0

    def test_create_and_read_session(self):
        session = create_session(12345, "/home/user", "127.0.0.1:9823")
        assert session["pid"] == 12345
        assert session["cwd"] == "/home/user"
        assert session["ipc_address"] == "127.0.0.1:9823"
        assert "created" in session
        assert "owner" in session
        assert "version" in session

        read = read_session()
        assert read["pid"] == 12345
        assert read["cwd"] == "/home/user"

    def test_write_session_atomic(self):
        session = {"pid": 123, "cwd": "/test", "created": time.time(), "owner": "test", "ipc_address": "127.0.0.1:9823"}
        write_session_atomic(session)

        assert SESSION_FILE.exists()
        with open(SESSION_FILE) as f:
            data = json.load(f)
        assert data["pid"] == 123

    def test_remove_session(self):
        create_session(12345, "/home/user", "127.0.0.1:9823")
        assert SESSION_FILE.exists()

        remove_session()
        assert not SESSION_FILE.exists()

    def test_is_process_alive_current(self):
        assert is_process_alive(os.getpid()) is True

    def test_is_process_alive_fake(self):
        assert is_process_alive(999999) is False

    def test_is_session_stale(self):
        session = {"pid": 999999}
        assert is_session_stale(session) is True

        session = {"pid": os.getpid()}
        assert is_session_stale(session) is False

        assert is_session_stale(None) is True
        assert is_session_stale({}) is True

    def test_validate_session_ownership(self):
        session = {"owner": get_owner_identity()}
        assert validate_session_ownership(session) is True

        session = {"owner": "different_user_that_does_not_exist"}
        assert validate_session_ownership(session) is False

        assert validate_session_ownership(None) is False

    def test_cleanup_stale_sessions(self):
        create_session(999999, "/tmp", "127.0.0.1:9823")
        count = cleanup_stale_sessions()
        assert count == 1
        assert not SESSION_FILE.exists()

        create_session(os.getpid(), "/tmp", "127.0.0.1:9823")
        count = cleanup_stale_sessions()
        assert count == 0
        assert SESSION_FILE.exists()


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])