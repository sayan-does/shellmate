import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from unittest.mock import patch

from daemon import lifecycle


class TestShellmateDetection:
    def test_is_shellmate_status_true_when_startup_stage_present(self):
        assert lifecycle._is_shellmate_status({"startup_stage": "ready"}) is True

    def test_is_shellmate_status_false_for_empty_or_foreign(self):
        assert lifecycle._is_shellmate_status(None) is False
        assert lifecycle._is_shellmate_status({}) is False
        assert lifecycle._is_shellmate_status({"healthy": True}) is False


class TestResolveDaemonPid:
    def test_prefers_daemon_pid_from_status(self):
        pid = lifecycle._resolve_daemon_pid("127.0.0.1", 9823, {"daemon_pid": 42})
        assert pid == 42

    @patch("daemon.lifecycle._find_pid_listening_on_port", return_value=25660)
    def test_falls_back_to_port_lookup_for_legacy_daemon(self, mock_find):
        status = {"startup_stage": "ready"}
        pid = lifecycle._resolve_daemon_pid("127.0.0.1", 9823, status)
        assert pid == 25660
        mock_find.assert_called_once_with("127.0.0.1", 9823)


class TestStartDaemonOrphanRecovery:
    @patch("daemon.lifecycle.create_session")
    @patch("daemon.lifecycle._resolve_daemon_pid", return_value=25660)
    @patch("daemon.lifecycle._query_daemon_status", return_value={"startup_stage": "ready"})
    @patch("daemon.lifecycle._check_port_in_use", return_value=True)
    @patch("daemon.lifecycle.read_session", return_value=None)
    @patch("daemon.lifecycle.cleanup_stale_sessions")
    def test_adopts_orphaned_daemon_without_daemon_pid(
        self, _cleanup, _read, _port, _status, _resolve, create_session
    ):
        assert lifecycle.start_daemon() is True
        create_session.assert_called_once()


class TestStopDaemonOrphanRecovery:
    @patch("daemon.lifecycle.remove_session")
    @patch("daemon.lifecycle.is_process_alive", return_value=False)
    @patch("daemon.lifecycle.subprocess.run")
    @patch("daemon.lifecycle._send_daemon_shutdown", return_value=True)
    @patch("daemon.lifecycle._resolve_daemon_pid", return_value=25660)
    @patch("daemon.lifecycle._query_daemon_status", return_value={"startup_stage": "ready"})
    @patch("daemon.lifecycle._check_port_in_use", return_value=True)
    @patch("daemon.lifecycle.read_session", return_value=None)
    def test_stops_daemon_discovered_on_port_without_session(
        self,
        _read,
        _port,
        _status,
        resolve_pid,
        _shutdown,
        taskkill,
        _alive,
        _remove,
    ):
        lifecycle.stop_daemon()
        resolve_pid.assert_called_once()
        taskkill.assert_called_once()
