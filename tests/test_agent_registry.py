from __future__ import annotations

import pytest

from coding_pet.agents.claude_code import ClaudeCodeAdapter
from coding_pet.agents.codex import CodexAdapter
from coding_pet.agents.opencode import OpenCodeAdapter
from coding_pet.models import AgentKind


def test_backend_registry_reports_missing_binaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from coding_pet.agents.registry import AgentBackendRegistry

    monkeypatch.setattr("coding_pet.agents.registry.shutil.which", lambda _name: None)

    registry = AgentBackendRegistry.default()

    claude = registry.describe(AgentKind.CLAUDE_CODE)
    codex = registry.describe(AgentKind.CODEX)
    opencode = registry.describe(AgentKind.OPENCODE)

    assert claude.available is False
    assert claude.binary_name == "claude"
    assert "not installed" in claude.reason
    assert codex.available is False
    assert codex.binary_name == "codex"
    assert "not installed" in codex.reason
    assert opencode.available is False
    assert opencode.binary_name == "opencode"
    assert "not installed" in opencode.reason


def test_backend_registry_reports_available_binaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from coding_pet.agents.registry import AgentBackendRegistry

    def fake_which(name: str) -> str | None:
        if name == "claude":
            return "/usr/local/bin/claude"
        if name == "opencode":
            return "/usr/local/bin/opencode"
        if name == "codex":
            return "/usr/local/bin/codex"
        return None

    monkeypatch.setattr("coding_pet.agents.registry.shutil.which", fake_which)

    registry = AgentBackendRegistry.default()

    claude = registry.describe(AgentKind.CLAUDE_CODE)
    codex = registry.describe(AgentKind.CODEX)
    opencode = registry.describe(AgentKind.OPENCODE)

    assert claude.available is True
    assert claude.binary_path == "/usr/local/bin/claude"
    assert isinstance(claude.adapter, ClaudeCodeAdapter)
    assert opencode.available is True
    assert opencode.binary_path == "/usr/local/bin/opencode"
    assert isinstance(opencode.adapter, OpenCodeAdapter)
    assert codex.available is True
    assert codex.binary_path == "/usr/local/bin/codex"
    assert isinstance(codex.adapter, CodexAdapter)
