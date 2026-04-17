from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from coding_pet.daemon.manager import MonitorManager
from coding_pet.daemon.session_registry import SessionRegistry
from coding_pet.models import AgentKind, AttentionState, SessionStatus
from coding_pet.notifiers.base import Notification


@dataclass
class RecordingNotifier:
    sent: list[Notification] = field(default_factory=list)

    async def notify(self, notification: Notification) -> None:
        self.sent.append(notification)


def build_status(session_id: str, state: AttentionState, *, title: str = "job") -> SessionStatus:
    return SessionStatus(
        session_id=session_id,
        agent_kind=AgentKind.CLAUDE_CODE,
        title=title,
        workspace=f"/tmp/{session_id}",
        state=state,
        summary=f"{title} -> {state.value}",
        last_event_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_notification_fires_on_first_transition_into_needs_permission() -> None:
    registry = SessionRegistry()
    notifier = RecordingNotifier()
    MonitorManager(registry=registry, notifier=notifier, notification_cooldown=timedelta(minutes=1))

    await registry.upsert(build_status("s1", AttentionState.RUNNING, title="review"))
    await registry.upsert(build_status("s1", AttentionState.NEEDS_PERMISSION, title="review"))

    assert len(notifier.sent) == 1
    assert notifier.sent[0].session_id == "s1"
    assert notifier.sent[0].state is AttentionState.NEEDS_PERMISSION


@pytest.mark.asyncio
async def test_repeated_identical_events_within_cooldown_do_not_spam() -> None:
    registry = SessionRegistry()
    notifier = RecordingNotifier()
    MonitorManager(registry=registry, notifier=notifier, notification_cooldown=timedelta(hours=1))

    await registry.upsert(build_status("s1", AttentionState.RUNNING))
    await registry.upsert(build_status("s1", AttentionState.NEEDS_PERMISSION))
    await registry.upsert(build_status("s1", AttentionState.NEEDS_PERMISSION))
    await registry.upsert(build_status("s1", AttentionState.NEEDS_PERMISSION))

    assert [item.state for item in notifier.sent] == [AttentionState.NEEDS_PERMISSION]


@pytest.mark.asyncio
async def test_completed_events_notify_once_per_session() -> None:
    registry = SessionRegistry()
    notifier = RecordingNotifier()
    MonitorManager(registry=registry, notifier=notifier, notification_cooldown=timedelta(minutes=1))

    await registry.upsert(build_status("done-1", AttentionState.RUNNING, title="done-1"))
    await registry.upsert(build_status("done-1", AttentionState.COMPLETED, title="done-1"))
    await registry.upsert(build_status("done-1", AttentionState.COMPLETED, title="done-1"))
    await registry.upsert(build_status("done-2", AttentionState.RUNNING, title="done-2"))
    await registry.upsert(build_status("done-2", AttentionState.COMPLETED, title="done-2"))

    completed_ids = [
        item.session_id
        for item in notifier.sent
        if item.state is AttentionState.COMPLETED
    ]
    assert completed_ids == ["done-1", "done-2"]
