from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import timedelta

from coding_pet.agents.base import AgentAdapter
from coding_pet.daemon.monitor import MonitorTask, ProcessHandle
from coding_pet.daemon.session_registry import SessionRegistry


class MonitorManager:
    def __init__(
        self,
        *,
        registry: SessionRegistry,
        stall_timeout: timedelta = timedelta(minutes=5),
    ) -> None:
        self.registry = registry
        self.stall_timeout = stall_timeout
        self._tasks: dict[str, asyncio.Task[None]] = {}

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
