from __future__ import annotations

from datetime import UTC, datetime

from coding_pet import __version__
from coding_pet.events import SessionEvent, SessionEventType
from coding_pet.models import AgentKind, AttentionState, SessionStatus, attention_priority


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
