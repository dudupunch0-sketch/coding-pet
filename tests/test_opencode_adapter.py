from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coding_pet.agents.opencode import OpenCodeAdapter
from coding_pet.models import AgentKind, AttentionState


def test_opencode_adapter_builds_initial_status_with_workspace_name_title() -> None:
    adapter = OpenCodeAdapter()
    status = adapter.build_initial_status(
        session_id="open-1",
        workspace="/tmp/sample-repo",
        observed_at=datetime(2026, 4, 17, tzinfo=UTC),
        pid=None,
        title=None,
    )

    assert status.session_id == "open-1"
    assert status.agent_kind is AgentKind.OPENCODE
    assert status.workspace == "/tmp/sample-repo"
    assert status.pid is None
    assert status.title == "sample-repo"
    assert status.state is AttentionState.RUNNING


def test_opencode_adapter_classifies_line_and_extracts_summary() -> None:
    adapter = OpenCodeAdapter()
    observed_at = datetime(2026, 4, 17, tzinfo=UTC)

    event = adapter.classify_line(
        line="Need approval before deleting files.",
        observed_at=observed_at,
    )

    assert event is not None
    assert event.state is AttentionState.NEEDS_PERMISSION
    assert adapter.extract_summary("  Please review the generated patch.  ") == (
        "Please review the generated patch."
    )


def test_opencode_adapter_exposes_launch_metadata() -> None:
    adapter = OpenCodeAdapter()

    assert adapter.agent_kind() is AgentKind.OPENCODE
    assert adapter.launch_command(prompt="Review tests", workspace="/tmp/project") == [
        "opencode",
        "run",
        "Review tests",
    ]


def test_opencode_adapter_control_messages_cover_reply_and_approval_actions() -> None:
    adapter = OpenCodeAdapter()

    assert adapter.control_message(action="send_reply", reply_text="summarize shortly") == (
        "summarize shortly"
    )
    assert adapter.control_message(action="send_without_enter", reply_text="draft") == "draft"
    assert adapter.control_message(action="approve") == "approve"
    assert adapter.control_message(action="reject") == "reject"


def test_opencode_adapter_control_messages_can_be_overridden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CODING_PET_OPENCODE_APPROVE_TEXT", "accept")
    monkeypatch.setenv("CODING_PET_OPENCODE_REJECT_TEXT", "deny")
    adapter = OpenCodeAdapter()

    assert adapter.control_message(action="approve") == "accept"
    assert adapter.control_message(action="reject") == "deny"
