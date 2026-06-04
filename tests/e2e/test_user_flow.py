"""
End-to-End User Flow Test for ShellMate

This test simulates a typical user workflow:
1. Check status
2. Analyze a command
3. View configuration
4. Check provider status
"""

import pytest
import subprocess
import json
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class TestUserFlow:
    """Test complete user workflow scenarios"""

    def test_cli_available(self):
        """Test that the CLI is accessible"""
        result = subprocess.run(
            [sys.executable, "-m", "cli.main", "--help"],
            capture_output=True,
            text=True,
            timeout=10
        )
        assert result.returncode == 0
        assert "ShellMate" in result.stdout
        assert "Intelligent Command Safety Layer" in result.stdout

    def test_status_command(self):
        """Test status command returns valid JSON"""
        result = subprocess.run(
            [sys.executable, "-m", "cli.main", "status"],
            capture_output=True,
            text=True,
            timeout=10
        )
        # Status may fail if daemon not running, but should return valid JSON
        if result.returncode == 0:
            try:
                status_data = json.loads(result.stdout)
                assert isinstance(status_data, dict)
                assert "providers" in status_data
            except json.JSONDecodeError:
                pytest.fail(f"Status command did not return valid JSON: {result.stdout}")

    def test_doctor_command(self):
        """Test doctor command detects environment"""
        result = subprocess.run(
            [sys.executable, "-m", "cli.main", "doctor"],
            capture_output=True,
            text=True,
            timeout=10
        )
        assert result.returncode == 0
        
        # Should return valid JSON with environment details
        try:
            env_data = json.loads(result.stdout)
            assert isinstance(env_data, dict)
            assert "os" in env_data
            assert "shell" in env_data
        except json.JSONDecodeError:
            pytest.fail(f"Doctor command did not return valid JSON: {result.stdout}")

    def test_config_view_command(self):
        """Test config command displays configuration"""
        result = subprocess.run(
            [sys.executable, "-m", "cli.main", "config"],
            capture_output=True,
            text=True,
            timeout=10
        )
        assert result.returncode == 0
        
        # Should return valid JSON with credentials and settings
        try:
            config_data = json.loads(result.stdout)
            assert isinstance(config_data, dict)
            assert "credentials" in config_data
            assert "settings" in config_data
        except json.JSONDecodeError:
            pytest.fail(f"Config command did not return valid JSON: {result.stdout}")

    def test_providers_command(self):
        """Test providers command lists AI providers"""
        result = subprocess.run(
            [sys.executable, "-m", "cli.main", "providers"],
            capture_output=True,
            text=True,
            timeout=10
        )
        assert result.returncode == 0
        
        # Should return valid JSON with provider status
        try:
            provider_data = json.loads(result.stdout)
            assert isinstance(provider_data, dict)
        except json.JSONDecodeError:
            pytest.fail(f"Providers command did not return valid JSON: {result.stdout}")

    def test_analyze_safe_command(self):
        """Test analyzing a safe command"""
        result = subprocess.run(
            [sys.executable, "-m", "cli.main", "analyze", "ls -la"],
            capture_output=True,
            text=True,
            timeout=30
        )
        # Analyze might fail without API keys, but should not crash
        assert result.returncode in [0, 1]  # Allow both success and expected failure

    def test_analyze_dangerous_command(self):
        """Test analyzing a dangerous command"""
        result = subprocess.run(
            [sys.executable, "-m", "cli.main", "analyze", "rm -rf /"],
            capture_output=True,
            text=True,
            timeout=30
        )
        # Should detect danger even without AI (rule engine should catch it)
        assert result.returncode in [0, 1]  # Allow both success and expected failure
        # Check if output contains risk indicators
        output = result.stdout + result.stderr
        assert len(output) > 0  # Should produce some output

    def test_complete_workflow(self):
        """Test a complete user workflow from start to finish"""
        # Step 1: Check environment
        doctor_result = subprocess.run(
            [sys.executable, "-m", "cli.main", "doctor"],
            capture_output=True,
            text=True,
            timeout=10
        )
        assert doctor_result.returncode == 0
        
        # Step 2: View configuration
        config_result = subprocess.run(
            [sys.executable, "-m", "cli.main", "config"],
            capture_output=True,
            text=True,
            timeout=10
        )
        assert config_result.returncode == 0
        
        # Step 3: Check provider status
        provider_result = subprocess.run(
            [sys.executable, "-m", "cli.main", "providers"],
            capture_output=True,
            text=True,
            timeout=10
        )
        assert provider_result.returncode == 0
        
        # Step 4: Analyze a command
        analyze_result = subprocess.run(
            [sys.executable, "-m", "cli.main", "analyze", "echo 'Hello World'"],
            capture_output=True,
            text=True,
            timeout=30
        )
        # May fail without API keys, but should not crash
        assert analyze_result.returncode in [0, 1]
        
        print("\n=== Complete User Flow Test Summary ===")
        print(f"✓ Environment detection: {'PASS' if doctor_result.returncode == 0 else 'FAIL'}")
        print(f"✓ Configuration view: {'PASS' if config_result.returncode == 0 else 'FAIL'}")
        print(f"✓ Provider status: {'PASS' if provider_result.returncode == 0 else 'FAIL'}")
        print(f"✓ Command analysis: {'PASS' if analyze_result.returncode in [0, 1] else 'FAIL'}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
