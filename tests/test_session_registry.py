from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coding_pet.daemon.session_registry import SessionRegistry
from coding_pet.models import AgentKind, AttentionState, SessionStatus


def build_status(
    session_id: str,
    *,
    agent_kind: AgentKind,
    state: AttentionState,
    title: str,
) -> SessionStatus:
    return SessionStatus(
        session_id=session_id,
        agent_kind=agent_kind,
        title=title,
        workspace=f"/tmp/{session_id}",
        state=state,
        summary=title,
        last_event_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_registry_tracks_independent_sessions() -> None:
    registry = SessionRegistry()
    left = build_status(
        "s1",
        agent_kind=AgentKind.CLAUDE_CODE,
        state=AttentionState.RUNNING,
        title="left",
    )
    right = build_status(
        "s2",
        agent_kind=AgentKind.OPENCODE,
        state=AttentionState.NEEDS_INPUT,
        title="right",
    )

    await registry.upsert(left)
    await registry.upsert(right)

    assert await registry.get("s1") == left
    assert await registry.get("s2") == right


@pytest.mark.asyncio
async def test_registry_updates_one_session_without_touching_others() -> None:
    registry = SessionRegistry()
    original = build_status(
        "s1",
        agent_kind=AgentKind.CLAUDE_CODE,
        state=AttentionState.RUNNING,
        title="original",
    )
    untouched = build_status(
        "s2",
        agent_kind=AgentKind.OPENCODE,
        state=AttentionState.COMPLETED,
        title="untouched",
    )

    await registry.upsert(original)
    await registry.upsert(untouched)
    await registry.upsert(
        build_status(
            "s1",
            agent_kind=AgentKind.CLAUDE_CODE,
            state=AttentionState.NEEDS_PERMISSION,
            title="updated",
        )
    )
    left = await registry.get("s1")
    right = await registry.get("s2")

    assert left is not None
    assert right is not None
    assert left.title == "updated"
    assert right.title == "untouched"


@pytest.mark.asyncio
async def test_registry_lists_attention_order_descending() -> None:
    registry = SessionRegistry()
    await registry.upsert(
        build_status(
            "s1",
            agent_kind=AgentKind.CLAUDE_CODE,
            state=AttentionState.RUNNING,
            title="run",
        )
    )
    await registry.upsert(
        build_status("s2", agent_kind=AgentKind.OPENCODE, state=AttentionState.FAILED, title="fail")
    )
    await registry.upsert(
        build_status(
            "s3",
            agent_kind=AgentKind.OPENCODE,
            state=AttentionState.NEEDS_INPUT,
            title="input",
        )
    )

    ordered_ids = [status.session_id for status in await registry.list_sessions()]

    assert ordered_ids == ["s2", "s3", "s1"]


@pytest.mark.asyncio
async def test_registry_exposes_stable_pet_layout_order() -> None:
    registry = SessionRegistry()
    await registry.upsert(
        build_status(
            "s2",
            agent_kind=AgentKind.OPENCODE,
            state=AttentionState.RUNNING,
            title="second",
        )
    )
    await registry.upsert(
        build_status(
            "s1",
            agent_kind=AgentKind.CLAUDE_CODE,
            state=AttentionState.RUNNING,
            title="first",
        )
    )

    assert await registry.pet_layout_order() == ["s1", "s2"]


@pytest.mark.asyncio
async def test_registry_marks_sessions_read_and_removes_them() -> None:
    registry = SessionRegistry()
    unread = build_status(
        "s1",
        agent_kind=AgentKind.CLAUDE_CODE,
        state=AttentionState.NEEDS_INPUT,
        title="needs attention",
    ).model_copy(update={"unread": True})

    messages: list[dict[str, object]] = []

    async def subscriber(message: dict[str, object]) -> None:
        messages.append(message)

    registry.subscribe(subscriber)
    await registry.upsert(unread)
    marked_result = await registry.mark_read("s1")
    marked = await registry.get("s1")
    assert marked_result is True
    assert marked is not None
    assert marked.unread is False
    assert messages[-1]["type"] == "session_updated"
    session_payload = messages[-1]["session"]
    assert isinstance(session_payload, dict)
    assert session_payload["unread"] is False

    removed = await registry.remove("s1")
    assert removed is True
    assert await registry.get("s1") is None
