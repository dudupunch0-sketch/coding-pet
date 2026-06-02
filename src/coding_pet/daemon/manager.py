from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta

from coding_pet.agents.base import AgentAdapter
from coding_pet.daemon.action_router import (
    ActionResult,
    SessionActionRequest,
    failure_result,
)
from coding_pet.daemon.monitor import MonitorTask, ProcessHandle
from coding_pet.daemon.session_registry import SessionRegistry
from coding_pet.logging import ContextAdapter, get_logger
from coding_pet.models import AttentionState, SessionStatus, normalize_action_result_message
from coding_pet.notifiers.base import Notification, Notifier
from coding_pet.notifiers.desktop import DesktopNotifier
from coding_pet.state_store import StateStore

ActionHandler = Callable[[SessionActionRequest], Awaitable[ActionResult | None]]


class MonitorManager:
    def __init__(
        self,
        *,
        registry: SessionRegistry,
        stall_timeout: timedelta = timedelta(minutes=5),
        notifier: Notifier | None = None,
        notification_cooldown: timedelta = timedelta(minutes=1),
        completed_retention: timedelta | None = None,
        process_stop_timeout: timedelta = timedelta(seconds=2),
        state_store: StateStore | None = None,
    ) -> None:
        self.registry = registry
        self.stall_timeout = stall_timeout
        self.notifier = notifier or DesktopNotifier()
        self.notification_cooldown = notification_cooldown
        self.completed_retention = completed_retention
        self.process_stop_timeout = process_stop_timeout
        self.state_store = state_store
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._action_handlers: dict[str, ActionHandler] = {}
        self._completed_cleanup_tasks: dict[str, asyncio.Task[None]] = {}
        self._last_seen_states: dict[str, AttentionState] = {}
        self._last_notified_at: dict[tuple[str, AttentionState], datetime] = {}
        self._completed_notified: set[str] = set()
        self._unsubscribe: Callable[[], None] | None = None
        self._logger: ContextAdapter = get_logger("daemon.manager")
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
        action_handler: ActionHandler | None = None,
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
            process_stop_timeout=self.process_stop_timeout,
            pid=pid,
        )
        self._tasks[session_id] = asyncio.create_task(monitor.run())
        if action_handler is not None:
            self.register_control_channel(session_id, action_handler)

    def register_control_channel(self, session_id: str, handler: ActionHandler) -> None:
        self._action_handlers[session_id] = handler

    def unregister_control_channel(self, session_id: str) -> None:
        self._action_handlers.pop(session_id, None)

    async def stop_session(self, session_id: str) -> None:
        self.unregister_control_channel(session_id)
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

    async def stop_all_sessions(self) -> None:
        for session_id in list(self._tasks):
            await self.stop_session(session_id)
        for session_id in list(self._action_handlers):
            self.unregister_control_channel(session_id)
        await self._cancel_all_completed_cleanup_tasks()

    def has_live_session(self, session_id: str) -> bool:
        task = self._tasks.get(session_id)
        return (task is not None and not task.done()) or session_id in self._action_handlers

    async def route_action(self, request: SessionActionRequest) -> ActionResult:
        handler = self._action_handlers.get(request.session_id)
        if handler is None:
            self._logger.warning(
                "Session action requested without live control channel",
                extra={"session_id": request.session_id, "action": request.action},
            )
            return failure_result(
                session_id=request.session_id,
                action=request.action,
                reason="no_live_control_channel",
                detail="session has no live control channel",
            )

        result = await handler(request)
        if result is not None:
            return normalize_action_result_message(result)
        return failure_result(
            session_id=request.session_id,
            action=request.action,
            reason="unsupported_action",
            detail=f"{request.action} is not supported by this session",
        )

    async def restore_from_store(self) -> list[SessionStatus]:
        if self.state_store is None:
            return []
        restored = await self.state_store.restore_sessions()
        active_restored: list[SessionStatus] = []
        skipped_stale_completed = False
        for status in restored:
            if self._completed_retention_expired(status):
                skipped_stale_completed = True
                continue
            if await self.registry.get(status.session_id) is not None:
                continue
            await self.registry.upsert(status)
            active_restored.append(status)
        if skipped_stale_completed:
            await self.persist_snapshot()
        return active_restored

    async def persist_snapshot(self) -> None:
        if self.state_store is None:
            return
        await self.state_store.write_sessions(await self.registry.list_sessions())

    async def _handle_registry_message(self, message: dict[str, object]) -> None:
        message_type = message.get("type")
        if message_type == "session_removed":
            session_id = message.get("session_id")
            if isinstance(session_id, str):
                self._cancel_completed_cleanup(session_id)
                self._last_seen_states.pop(session_id, None)
                self._completed_notified.discard(session_id)
        if message.get("type") in {"session_updated", "session_removed"}:
            await self.persist_snapshot()
        if message_type != "session_updated":
            return
        session_data = message.get("session")
        if not isinstance(session_data, dict):
            return
        status = SessionStatus.model_validate(session_data)
        self._update_completed_cleanup(status)
        previous_state = self._last_seen_states.get(status.session_id)
        self._last_seen_states[status.session_id] = status.state
        if previous_state is None or previous_state is status.state:
            return
        if status.state not in {
            AttentionState.NEEDS_PERMISSION,
            AttentionState.NEEDS_CHOICE,
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

    def _update_completed_cleanup(self, status: SessionStatus) -> None:
        if (
            self.completed_retention is None
            or status.state is not AttentionState.COMPLETED
            or status.live
        ):
            self._cancel_completed_cleanup(status.session_id)
            return
        existing = self._completed_cleanup_tasks.get(status.session_id)
        if existing is not None and not existing.done():
            return
        self._completed_cleanup_tasks[status.session_id] = asyncio.create_task(
            self._remove_completed_after_retention(
                session_id=status.session_id,
                completed_at=status.last_event_at,
            )
        )

    async def _remove_completed_after_retention(
        self,
        *,
        session_id: str,
        completed_at: datetime,
    ) -> None:
        task = asyncio.current_task()
        try:
            delay = self._completed_cleanup_delay(completed_at)
            if delay:
                await asyncio.sleep(delay)
            current = await self.registry.get(session_id)
            if (
                current is not None
                and current.state is AttentionState.COMPLETED
                and not current.live
                and current.last_event_at == completed_at
            ):
                await self.registry.remove(session_id)
        except asyncio.CancelledError:
            raise
        finally:
            if self._completed_cleanup_tasks.get(session_id) is task:
                self._completed_cleanup_tasks.pop(session_id, None)

    def _cancel_completed_cleanup(self, session_id: str) -> None:
        task = self._completed_cleanup_tasks.pop(session_id, None)
        if task is not None and not task.done():
            task.cancel()

    async def _cancel_all_completed_cleanup_tasks(self) -> None:
        tasks = list(self._completed_cleanup_tasks.values())
        self._completed_cleanup_tasks.clear()
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _completed_retention_expired(self, status: SessionStatus) -> bool:
        if self.completed_retention is None:
            return False
        if status.state is not AttentionState.COMPLETED or status.live:
            return False
        return self._completed_cleanup_delay(status.last_event_at) <= 0.0

    def _completed_cleanup_delay(self, completed_at: datetime) -> float:
        if self.completed_retention is None:
            return 0.0
        elapsed = datetime.now(UTC) - completed_at
        return max(0.0, self.completed_retention.total_seconds() - elapsed.total_seconds())

    def _build_notification(self, status: SessionStatus) -> Notification:
        return Notification(
            session_id=status.session_id,
            title=f"Coding Pet: {status.title}",
            body=f"{status.agent_kind.value}: {status.summary}",
            state=status.state,
        )
