from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from coding_pet.daemon.manager import MonitorManager
from coding_pet.daemon.session_registry import SessionRegistry
from coding_pet.models import AgentKind, AttentionState, SessionStatus
from coding_pet.notifiers.base import Notification
from coding_pet.state_store import StateStore


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


@pytest.mark.asyncio
async def test_inactive_completed_sessions_are_removed_after_retention() -> None:
    registry = SessionRegistry()
    MonitorManager(
        registry=registry,
        notifier=RecordingNotifier(),
        completed_retention=timedelta(milliseconds=10),
    )

    await registry.upsert(build_status("done", AttentionState.RUNNING))
    await registry.upsert(
        build_status("done", AttentionState.COMPLETED).model_copy(update={"live": False})
    )
    await asyncio.sleep(0.05)

    assert await registry.get("done") is None


@pytest.mark.asyncio
async def test_completed_retention_does_not_remove_live_or_reopened_sessions() -> None:
    registry = SessionRegistry()
    MonitorManager(
        registry=registry,
        notifier=RecordingNotifier(),
        completed_retention=timedelta(milliseconds=10),
    )

    await registry.upsert(build_status("live-done", AttentionState.COMPLETED))
    await registry.upsert(
        build_status("reopened", AttentionState.COMPLETED).model_copy(update={"live": False})
    )
    await registry.upsert(build_status("reopened", AttentionState.RUNNING))
    await asyncio.sleep(0.05)

    assert await registry.get("live-done") is not None
    reopened = await registry.get("reopened")
    assert reopened is not None
    assert reopened.state is AttentionState.RUNNING


@pytest.mark.asyncio
async def test_restore_skips_completed_sessions_older_than_retention(
    tmp_path: Path,
) -> None:
    store = StateStore(tmp_path / "state.json")
    old_completed = build_status("old-done", AttentionState.COMPLETED).model_copy(
        update={
            "live": False,
            "last_event_at": datetime.now(UTC) - timedelta(seconds=60),
        }
    )
    old_failed = build_status("old-failed", AttentionState.FAILED).model_copy(
        update={
            "live": False,
            "last_event_at": datetime.now(UTC) - timedelta(seconds=60),
        }
    )
    await store.write_sessions([old_completed, old_failed])
    registry = SessionRegistry()
    manager = MonitorManager(
        registry=registry,
        notifier=RecordingNotifier(),
        state_store=store,
        completed_retention=timedelta(seconds=10),
    )

    restored = await manager.restore_from_store()

    assert [status.session_id for status in restored] == ["old-failed"]
    assert await registry.get("old-done") is None
    assert await registry.get("old-failed") is not None


@pytest.mark.asyncio
async def test_restored_completed_sessions_use_remaining_retention(
    tmp_path: Path,
) -> None:
    store = StateStore(tmp_path / "state.json")
    recent_completed = build_status("recent-done", AttentionState.COMPLETED).model_copy(
        update={
            "live": False,
            "last_event_at": datetime.now(UTC) - timedelta(milliseconds=150),
        }
    )
    await store.write_sessions([recent_completed])
    registry = SessionRegistry()
    manager = MonitorManager(
        registry=registry,
        notifier=RecordingNotifier(),
        state_store=store,
        completed_retention=timedelta(milliseconds=200),
    )

    restored = await manager.restore_from_store()
    assert [status.session_id for status in restored] == ["recent-done"]
    assert await registry.get("recent-done") is not None
    await asyncio.sleep(0.08)

    assert await registry.get("recent-done") is None
