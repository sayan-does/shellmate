"""Tests for the semantic color module and its annotation integration."""

import importlib

import pytest

from shellmate.ui import colors
from shellmate.ui import annotations


def test_roles_map_to_expected_ansi():
    assert colors.ROLE_SGR["caution"] == 91      # red
    assert colors.ROLE_SGR["warning"] == 93      # yellow
    assert colors.ROLE_SGR["suggestion"] == 92   # green
    assert colors.ROLE_SGR["safe"] == 92         # green


@pytest.mark.parametrize("sev,role", [
    ("CRITICAL", "caution"), ("HIGH", "caution"), ("blocking", "caution"),
    ("MEDIUM", "warning"), ("LOW", "safe"), ("SAFE", "safe"),
    ("", "warning"), (None, "warning"),
])
def test_severity_role_mapping(sev, role):
    assert colors.role_for_severity(sev) == role


def test_colorize_wraps_and_resets():
    out = colors.suggestion("Safe alt: git push --force-with-lease", no_color=False)
    assert out.startswith("\033[92m")
    assert out.endswith("\033[0m")
    assert "Safe alt" in out


def test_caution_is_red_warning_is_yellow():
    assert colors.caution("boom", no_color=False).startswith("\033[91m")
    assert colors.warning("careful", no_color=False).startswith("\033[91m") is False
    assert colors.warning("careful", no_color=False).startswith("\033[93m")


def test_no_color_param_disables():
    assert colors.caution("x", no_color=True) == "x"


def test_empty_and_unknown_role_passthrough():
    assert colors.colorize("", "caution", no_color=False) == ""
    assert colors.colorize("hi", "no-such-role", no_color=False) == "hi"


def test_no_color_env(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    assert colors.color_enabled() is False
    assert colors.suggestion("x") == "x"
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert colors.color_enabled() is True


def test_annotation_color_flag_colorizes_suggestion_path_green():
    # A low/safe consequence should carry the green (92) role when color=True.
    consequence = {"what_happens": "Lists files", "reversible": True, "severity": "info"}
    plain = annotations.format_consequence_annotation(consequence, risk="SAFE")
    colored = annotations.format_consequence_annotation(consequence, risk="SAFE", color=True)
    assert "\033[" not in plain                 # default path unchanged (adapters color)
    assert colored.startswith("\033[") and colored.endswith("\033[0m")


def test_annotation_default_is_plain_for_adapters():
    # Adapters add their own ANSI, so the default (color=False) must stay plain.
    result = {"risk": "HIGH", "risk_analysis": {"reason": "rewrites history"}}
    assert "\033[" not in annotations.format_pipeline_annotation(result)
