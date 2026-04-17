from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta

from coding_pet.agents.base import AgentAdapter
from coding_pet.daemon.monitor import MonitorTask, ProcessHandle
from coding_pet.daemon.session_registry import SessionRegistry
from coding_pet.models import AttentionState, SessionStatus
from coding_pet.notifiers.base import Notification, Notifier
from coding_pet.notifiers.desktop import DesktopNotifier


class MonitorManager:
    def __init__(
        self,
        *,
        registry: SessionRegistry,
        stall_timeout: timedelta = timedelta(minutes=5),
        notifier: Notifier | None = None,
        notification_cooldown: timedelta = timedelta(minutes=1),
    ) -> None:
        self.registry = registry
        self.stall_timeout = stall_timeout
        self.notifier = notifier or DesktopNotifier()
        self.notification_cooldown = notification_cooldown
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._last_seen_states: dict[str, AttentionState] = {}
        self._last_notified_at: dict[tuple[str, AttentionState], datetime] = {}
        self._completed_notified: set[str] = set()
        self._unsubscribe: Callable[[], None] | None = None
        self._unsubscribe = self.registry.subscribe(self._handle_registry_message)

    async def start_session(
        self,
        *,
        session_id: str,
        adapter: AgentAdapter,
        workspace: str,
        output_lines: AsyncIterator[str],
        process: ProcessHandle,
        title: str | None = None,
        pid: int | None = None,
    ) -> None:
        await self.stop_session(session_id)
        monitor = MonitorTask(
            session_id=session_id,
            adapter=adapter,
            registry=self.registry,
            workspace=workspace,
            title=title,
            output_lines=output_lines,
            process=process,
            stall_timeout=self.stall_timeout,
            pid=pid,
        )
        self._tasks[session_id] = asyncio.create_task(monitor.run())

    async def stop_session(self, session_id: str) -> None:
        task = self._tasks.pop(session_id, None)
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def wait_for_all(self) -> None:
        if not self._tasks:
            return
        await asyncio.gather(*self._tasks.values())

    async def _handle_registry_message(self, message: dict[str, object]) -> None:
        if message.get("type") != "session_updated":
            return
        session_data = message.get("session")
        if not isinstance(session_data, dict):
            return
        status = SessionStatus.model_validate(session_data)
        previous_state = self._last_seen_states.get(status.session_id)
        self._last_seen_states[status.session_id] = status.state
        if previous_state is None or previous_state is status.state:
            return
        if status.state not in {
            AttentionState.NEEDS_PERMISSION,
            AttentionState.NEEDS_INPUT,
            AttentionState.REVIEW_NEEDED,
            AttentionState.COMPLETED,
            AttentionState.FAILED,
        }:
            return
        if (
            status.state is AttentionState.COMPLETED
            and status.session_id in self._completed_notified
        ):
            return

        key = (status.session_id, status.state)
        now = datetime.now(UTC)
        previous_notification = self._last_notified_at.get(key)
        if (
            previous_notification is not None
            and now - previous_notification < self.notification_cooldown
        ):
            return

        await self.notifier.notify(self._build_notification(status))
        self._last_notified_at[key] = now
        if status.state is AttentionState.COMPLETED:
            self._completed_notified.add(status.session_id)

    def _build_notification(self, status: SessionStatus) -> Notification:
        return Notification(
            session_id=status.session_id,
            title=f"Coding Pet: {status.title}",
            body=f"{status.agent_kind.value}: {status.summary}",
            state=status.state,
        )
