from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coding_pet.agents.codex import CodexAdapter
from coding_pet.models import AgentKind, AttentionState


def test_codex_adapter_builds_initial_status() -> None:
    adapter = CodexAdapter()
    status = adapter.build_initial_status(
        session_id="codex-1",
        workspace="/tmp/project",
        observed_at=datetime(2026, 6, 1, tzinfo=UTC),
        pid=1234,
        title="Refactor parser",
    )

    assert status.session_id == "codex-1"
    assert status.agent_kind is AgentKind.CODEX
    assert status.workspace == "/tmp/project"
    assert status.pid == 1234
    assert status.title == "Refactor parser"
    assert status.state is AttentionState.RUNNING


def test_codex_adapter_exposes_optional_launch_metadata() -> None:
    adapter = CodexAdapter()

    assert adapter.agent_kind() is AgentKind.CODEX
    assert adapter.binary_name() == "codex"
    assert adapter.launch_command(prompt="Fix lint", workspace="/tmp/project") == [
        "codex",
        "Fix lint",
    ]
    assert adapter.launch_command(prompt="", workspace="/tmp/project") == ["codex"]


def test_codex_adapter_control_messages_are_safe_text_inputs() -> None:
    adapter = CodexAdapter()

    assert adapter.control_message(action="send_reply", reply_text="keep going") == "keep going"
    assert adapter.control_message(action="send_without_enter", reply_text="draft") == "draft"
    assert adapter.control_message(action="approve") == "y"
    assert adapter.control_message(action="reject") == "n"


def test_codex_adapter_control_messages_can_be_overridden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODING_PET_CODEX_APPROVE_TEXT", "approve")
    monkeypatch.setenv("CODING_PET_CODEX_REJECT_TEXT", "reject")
    adapter = CodexAdapter()

    assert adapter.control_message(action="approve") == "approve"
    assert adapter.control_message(action="reject") == "reject"
