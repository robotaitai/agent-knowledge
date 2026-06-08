"""Install-health checks: legacy/shadowed package detection."""

from __future__ import annotations

from agent_knowledge.runtime import health


def test_detect_install_method_returns_known_value():
    assert health.detect_install_method() in {"pip", "pipx", "uv"}


def test_find_legacy_installs_shape():
    # Whatever is installed in the test env, the records are well-formed.
    for rec in health.find_legacy_installs():
        assert set(rec) == {"name", "version"}
        assert rec["name"] in health.LEGACY_DIST_NAMES


def test_legacy_install_is_flagged(monkeypatch):
    monkeypatch.setattr(
        health, "find_legacy_installs",
        lambda: [{"name": "agent-knowledge-cli", "version": "0.2.9"}],
    )
    monkeypatch.setattr(health, "_agent_knowledge_locations", lambda: ["/x/agent_knowledge"])
    issues = health.check_install_health()
    assert any("agent-knowledge-cli" in i and "0.2.9" in i for i in issues)
    assert any("uninstall" in i for i in issues)


def test_shadowed_copy_is_flagged(monkeypatch):
    monkeypatch.setattr(health, "find_legacy_installs", lambda: [])
    monkeypatch.setattr(
        health, "_agent_knowledge_locations",
        lambda: ["/venv/site-packages/agent_knowledge", "/repo/src/agent_knowledge"],
    )
    issues = health.check_install_health()
    assert any("Multiple" in i or "shadow" in i for i in issues)


def test_clean_install_has_no_issues(monkeypatch):
    monkeypatch.setattr(health, "find_legacy_installs", lambda: [])
    monkeypatch.setattr(health, "_agent_knowledge_locations", lambda: ["/repo/src/agent_knowledge"])
    assert health.check_install_health() == []
