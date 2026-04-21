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
from coding_pet.models import AttentionState, SessionStatus
from coding_pet.notifiers.base import Notification, Notifier
from coding_pet.notifiers.desktop import DesktopNotifier
from coding_pet.state_store import StateStore

ActionHandler = Callable[[SessionActionRequest], Awaitable[None]]


class MonitorManager:
    def __init__(
        self,
        *,
        registry: SessionRegistry,
        stall_timeout: timedelta = timedelta(minutes=5),
        notifier: Notifier | None = None,
        notification_cooldown: timedelta = timedelta(minutes=1),
        state_store: StateStore | None = None,
    ) -> None:
        self.registry = registry
        self.stall_timeout = stall_timeout
        self.notifier = notifier or DesktopNotifier()
        self.notification_cooldown = notification_cooldown
        self.state_store = state_store
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._action_handlers: dict[str, ActionHandler] = {}
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
            pid=pid,
        )
        self._tasks[session_id] = asyncio.create_task(monitor.run())
        if action_handler is not None:
            self._action_handlers[session_id] = action_handler

    async def stop_session(self, session_id: str) -> None:
        self._action_handlers.pop(session_id, None)
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

    def has_live_session(self, session_id: str) -> bool:
        task = self._tasks.get(session_id)
        return task is not None and not task.done()

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

        await handler(request)
        detail = (
            f"{request.reply_text} delivered"
            if request.action == "send_reply" and request.reply_text is not None
            else f"{request.action} delivered"
        )
        return {
            "type": "action_result",
            "session_id": request.session_id,
            "action": request.action,
            "ok": True,
            "reason": "delivered",
            "detail": detail,
        }

    async def restore_from_store(self) -> list[SessionStatus]:
        if self.state_store is None:
            return []
        restored = await self.state_store.restore_sessions()
        for status in restored:
            await self.registry.upsert(status)
        return restored

    async def persist_snapshot(self) -> None:
        if self.state_store is None:
            return
        await self.state_store.write_sessions(await self.registry.list_sessions())

    async def _handle_registry_message(self, message: dict[str, object]) -> None:
        if message.get("type") in {"session_updated", "session_removed"}:
            await self.persist_snapshot()
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
