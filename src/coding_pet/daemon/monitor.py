from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from coding_pet.agents.base import AgentAdapter
from coding_pet.daemon.session_registry import SessionRegistry
from coding_pet.events import SessionEvent, SessionEventType
from coding_pet.models import INACTIVE_SESSION_ACTIONS, AttentionState, action_capabilities_for


class ProcessHandle(Protocol):
    async def wait(self) -> int: ...


async def _next_line(iterator: AsyncIterator[str]) -> str:
    return await anext(iterator)


@dataclass(slots=True)
class MonitorTask:
    session_id: str
    adapter: AgentAdapter
    registry: SessionRegistry
    workspace: str
    title: str | None
    output_lines: AsyncIterator[str]
    process: ProcessHandle
    stall_timeout: timedelta = timedelta(minutes=5)
    process_stop_timeout: timedelta = timedelta(seconds=2)
    pid: int | None = None

    async def run(self) -> None:
        now = datetime.now(UTC)
        status = self.adapter.build_initial_status(
            session_id=self.session_id,
            workspace=self.workspace,
            observed_at=now,
            pid=self.pid,
            title=self.title,
        )
        await self.registry.upsert(status)

        iterator = aiter(self.output_lines)
        next_line_task: asyncio.Task[str] = asyncio.create_task(_next_line(iterator))
        exit_task: asyncio.Task[int] = asyncio.create_task(self.process.wait())
        last_output_at = now
        stalled = False
        lines_finished = False
        cancelled = False

        try:
            while True:
                wait_set: list[asyncio.Task[object]] = [exit_task]
                if not lines_finished:
                    wait_set.append(next_line_task)

                if lines_finished and exit_task.done():
                    break

                timeout: float | None = None
                if not stalled:
                    elapsed = datetime.now(UTC) - last_output_at
                    remaining = self.stall_timeout - elapsed
                    timeout = max(remaining.total_seconds(), 0.0)

                done, _pending = await asyncio.wait(
                    wait_set,
                    timeout=timeout,
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if not done:
                    stall_event = self._classify_stall(last_output_at=last_output_at)
                    if stall_event is not None:
                        await self._apply_event(stall_event)
                        stalled = True
                    continue

                if next_line_task in done:
                    try:
                        line = next_line_task.result()
                    except StopAsyncIteration:
                        lines_finished = True
                    else:
                        observed_at = datetime.now(UTC)
                        last_output_at = observed_at
                        stalled = False
                        event = self.adapter.classify_line(line=line, observed_at=observed_at)
                        if event is not None:
                            await self._apply_event(event)
                    if not lines_finished:
                        next_line_task = asyncio.create_task(_next_line(iterator))

                if exit_task in done and lines_finished:
                    break
        except asyncio.CancelledError:
            cancelled = True
            next_line_task.cancel()
            await self._stop_process_after_cancel(exit_task)
            with suppress(asyncio.CancelledError):
                await next_line_task
            await self._mark_monitor_stopped()
            raise
        finally:
            if not cancelled:
                if not exit_task.done():
                    exit_code = await exit_task
                else:
                    exit_code = exit_task.result()
                exit_event = self.adapter.classifier.classify_exit(
                    exit_code=exit_code,
                    observed_at=datetime.now(UTC),
                )
                if exit_event is not None:
                    await self._apply_event(exit_event)

    def _classify_stall(self, *, last_output_at: datetime) -> SessionEvent | None:
        observed_at = datetime.now(UTC)
        if observed_at - last_output_at < self.stall_timeout:
            return None
        return SessionEvent(
            session_id=self.session_id,
            event_type=SessionEventType.STATE_CHANGED,
            occurred_at=observed_at,
            summary="Session appears stalled",
            state=AttentionState.STALLED,
        )

    async def _apply_event(self, event: SessionEvent) -> None:
        current = await self.registry.get(self.session_id)
        if current is None:
            return

        summary = self.adapter.extract_summary(event.summary)
        updates: dict[str, object] = {
            "state": event.state or current.state,
            "summary": summary,
            "last_event_at": event.occurred_at,
            "last_output_snippet": (
                summary
                if event.event_type is not SessionEventType.PROCESS_EXITED
                else current.last_output_snippet
            ),
            "unread": event.state not in {None, current.state},
            "live": False
            if event.event_type is SessionEventType.PROCESS_EXITED
            else current.live,
        }
        if event.event_type is SessionEventType.PROCESS_EXITED:
            updates["supported_actions"] = list(INACTIVE_SESSION_ACTIONS)
            updates["action_capabilities"] = action_capabilities_for(
                INACTIVE_SESSION_ACTIONS,
                source_kind=current.source_kind,
            )
        updated = current.model_copy(update=updates)
        await self.registry.upsert(updated)

    async def _stop_process_after_cancel(self, exit_task: asyncio.Task[int]) -> None:
        self._request_process_stop()
        await self._wait_for_process_exit(exit_task)
        if exit_task.done():
            return
        self._request_process_kill()
        await self._wait_for_process_exit(exit_task)
        if not exit_task.done():
            exit_task.cancel()
            with suppress(asyncio.CancelledError):
                await exit_task

    async def _wait_for_process_exit(self, exit_task: asyncio.Task[int]) -> None:
        if exit_task.done():
            return
        timeout = max(0.0, self.process_stop_timeout.total_seconds())
        try:
            await asyncio.wait_for(asyncio.shield(exit_task), timeout=timeout)
        except TimeoutError:
            return

    def _request_process_stop(self) -> None:
        terminate = getattr(self.process, "terminate", None)
        if callable(terminate):
            with suppress(ProcessLookupError):
                terminate()

    def _request_process_kill(self) -> None:
        kill = getattr(self.process, "kill", None)
        if callable(kill):
            with suppress(ProcessLookupError):
                kill()

    async def _mark_monitor_stopped(self) -> None:
        current = await self.registry.get(self.session_id)
        if current is None:
            return
        updated = current.model_copy(
            update={
                "live": False,
                "last_event_at": datetime.now(UTC),
                "state_reason": "monitor_stopped",
                "supported_actions": list(INACTIVE_SESSION_ACTIONS),
                "action_capabilities": action_capabilities_for(
                    INACTIVE_SESSION_ACTIONS,
                    source_kind=current.source_kind,
                ),
            }
        )
        await self.registry.upsert(updated)
