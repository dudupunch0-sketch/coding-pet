from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from coding_pet.agents.base import AgentAdapter
from coding_pet.daemon.session_registry import SessionRegistry
from coding_pet.events import SessionEvent, SessionEventType
from coding_pet.models import AttentionState


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
        finally:
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
        updated = current.model_copy(
            update={
                "state": event.state or current.state,
                "summary": summary,
                "last_event_at": event.occurred_at,
                "last_output_snippet": (
                    summary
                    if event.event_type is not SessionEventType.PROCESS_EXITED
                    else current.last_output_snippet
                ),
                "unread": event.state not in {None, current.state},
            }
        )
        await self.registry.upsert(updated)
