from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coding_pet.agents.claude_code import ClaudeCodeAdapter
from coding_pet.models import AgentKind, AttentionState


def test_claude_adapter_builds_initial_status() -> None:
    adapter = ClaudeCodeAdapter()
    status = adapter.build_initial_status(
        session_id="claude-1",
        workspace="/tmp/project",
        observed_at=datetime(2026, 4, 17, tzinfo=UTC),
        pid=1234,
        title="Refactor parser",
    )

    assert status.session_id == "claude-1"
    assert status.agent_kind is AgentKind.CLAUDE_CODE
    assert status.workspace == "/tmp/project"
    assert status.pid == 1234
    assert status.title == "Refactor parser"
    assert status.state is AttentionState.RUNNING


def test_claude_adapter_classifies_line_and_extracts_summary() -> None:
    adapter = ClaudeCodeAdapter()
    observed_at = datetime(2026, 4, 17, tzinfo=UTC)

    event = adapter.classify_line(
        line="Waiting for your input before applying changes.",
        observed_at=observed_at,
    )

    assert event is not None
    assert event.state is AttentionState.NEEDS_INPUT
    assert adapter.extract_summary("  Waiting for your input before applying changes.  ") == (
        "Waiting for your input before applying changes."
    )


def test_claude_adapter_exposes_launch_metadata() -> None:
    adapter = ClaudeCodeAdapter()

    assert adapter.agent_kind() is AgentKind.CLAUDE_CODE
    assert adapter.launch_command(prompt="Fix lint", workspace="/tmp/project") == [
        "claude",
        "code",
        "Fix lint",
    ]


def test_claude_adapter_control_messages_cover_reply_and_approval_actions() -> None:
    adapter = ClaudeCodeAdapter()

    assert adapter.control_message(action="send_reply", reply_text="keep going") == "keep going"
    assert adapter.control_message(action="send_without_enter", reply_text="draft") == "draft"
    assert adapter.control_message(action="approve") == "approve"
    assert adapter.control_message(action="reject") == "reject"


def test_claude_adapter_control_messages_can_be_overridden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODING_PET_CLAUDE_CODE_APPROVE_TEXT", "yes")
    monkeypatch.setenv("CODING_PET_CLAUDE_REJECT_TEXT", "no")
    adapter = ClaudeCodeAdapter()

    assert adapter.control_message(action="approve") == "yes"
    assert adapter.control_message(action="reject") == "no"
