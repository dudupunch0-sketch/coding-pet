from __future__ import annotations

from datetime import UTC, datetime

from coding_pet import __version__
from coding_pet.events import SessionEvent, SessionEventType
from coding_pet.models import (
    ActionCapability,
    ActionOutcome,
    AgentKind,
    AttentionState,
    SessionStatus,
    action_outcome_ok,
    attention_priority,
    normalize_action_result_message,
)


def test_package_exposes_version() -> None:
    assert __version__


def test_session_status_defaults() -> None:
    status = SessionStatus(
        session_id="s1",
        agent_kind=AgentKind.CLAUDE_CODE,
        title="build task",
        workspace="/tmp/repo",
        state=AttentionState.RUNNING,
        summary="Working",
        last_event_at=datetime.now(UTC),
    )

    assert status.unread is False
    assert status.last_output_snippet == ""
    assert status.supported_actions == []
    assert status.attention_score == attention_priority(AttentionState.RUNNING)


def test_attention_priority_orders_states() -> None:
    assert attention_priority(AttentionState.FAILED) > attention_priority(AttentionState.RUNNING)
    assert attention_priority(AttentionState.NEEDS_PERMISSION) > attention_priority(
        AttentionState.REVIEW_NEEDED
    )
    assert attention_priority(AttentionState.IDLE) == 0


def test_session_status_round_trip_dump_and_validate() -> None:
    original = SessionStatus(
        session_id="s2",
        agent_kind=AgentKind.OPENCODE,
        title="review task",
        workspace="/tmp/repo2",
        state=AttentionState.NEEDS_INPUT,
        summary="Waiting for input",
        last_event_at=datetime.now(UTC),
        unread=True,
    )

    reloaded = SessionStatus.model_validate(original.model_dump(mode="json"))

    assert reloaded == original


def test_session_status_derives_structured_action_capabilities() -> None:
    status = SessionStatus(
        session_id="cap-1",
        agent_kind=AgentKind.CLAUDE_CODE,
        title="build task",
        workspace="/tmp/repo",
        state=AttentionState.NEEDS_PERMISSION,
        summary="Approval required",
        last_event_at=datetime.now(UTC),
        supported_actions=["send_reply", "approve", "send_reply"],
    )

    assert status.supported_actions == ["send_reply", "approve"]
    assert [capability.action for capability in status.action_capabilities] == [
        "send_reply",
        "approve",
    ]
    reply = status.capability_for("send_reply")
    approve = status.capability_for("approve")
    assert reply is not None
    assert reply.transport == "process_stdin"
    assert reply.requires_text is True
    assert reply.semantics == "agent_reply"
    assert approve is not None
    assert approve.transport == "process_stdin"
    assert approve.requires_text is False
    assert approve.semantics == "agent_control"
    assert status.supports_action("approve") is True
    assert status.supports_action("reject") is False


def test_session_status_accepts_structured_capabilities_from_new_snapshots() -> None:
    status = SessionStatus(
        session_id="cap-2",
        agent_kind=AgentKind.OPENCODE,
        title="review task",
        workspace="/tmp/repo2",
        state=AttentionState.NEEDS_INPUT,
        summary="Waiting for input",
        last_event_at=datetime.now(UTC),
        action_capabilities=[
            ActionCapability(
                action="send_reply",
                transport="tmux_buffer",
                requires_text=True,
                semantics="agent_reply",
            ),
            ActionCapability(
                action="attach",
                transport="tmux_attach",
                semantics="operator_attach",
            ),
        ],
    )

    assert status.supported_actions == ["send_reply", "attach"]
    assert status.supports_action("send_reply") is True
    assert status.supports_action("approve") is False
    attach = status.capability_for("attach")
    assert attach is not None
    assert attach.transport == "tmux_attach"


def test_action_outcome_contract_normalizes_legacy_and_future_results() -> None:
    accepted = normalize_action_result_message(
        {
            "type": "action_result",
            "session_id": "s1",
            "action": "send_reply",
            "outcome": "accepted",
            "detail": "backend accepted reply",
        }
    )
    timed_out = normalize_action_result_message(
        {
            "type": "action_result",
            "session_id": "s1",
            "action": "approve",
            "outcome": "timed_out",
            "reason": "backend_timeout",
            "detail": "backend did not confirm approval",
        }
    )
    legacy_unsupported = normalize_action_result_message(
        {
            "type": "action_result",
            "session_id": "s1",
            "action": "reject",
            "ok": False,
            "reason": "unsupported_action",
            "detail": "reject is not supported",
        }
    )

    assert accepted["ok"] is True
    assert accepted["outcome"] == ActionOutcome.ACCEPTED.value
    assert timed_out["ok"] is False
    assert timed_out["outcome"] == ActionOutcome.TIMED_OUT.value
    assert legacy_unsupported["outcome"] == ActionOutcome.UNSUPPORTED.value
    assert action_outcome_ok(ActionOutcome.LOCAL_UPDATED) is True
    assert action_outcome_ok("backend_failed") is False


def test_session_event_defaults() -> None:
    event = SessionEvent(
        session_id="s3",
        event_type=SessionEventType.STATE_CHANGED,
        state=AttentionState.COMPLETED,
        summary="Done",
        occurred_at=datetime.now(UTC),
    )

    assert event.metadata == {}
    assert event.state is AttentionState.COMPLETED
