from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import timedelta

import pytest

from coding_pet.agents.claude_code import ClaudeCodeAdapter
from coding_pet.agents.opencode import OpenCodeAdapter
from coding_pet.daemon.manager import MonitorManager
from coding_pet.daemon.monitor import MonitorTask
from coding_pet.daemon.session_registry import SessionRegistry
from coding_pet.models import AttentionState


class FakeProcess:
    def __init__(self, *, exit_code: int, exit_delay: float = 0.0) -> None:
        self.exit_code = exit_code
        self.exit_delay = exit_delay

    async def wait(self) -> int:
        await asyncio.sleep(self.exit_delay)
        return self.exit_code


async def delayed_lines(*items: tuple[float, str]) -> AsyncIterator[str]:
    for delay, line in items:
        await asyncio.sleep(delay)
        yield line


@pytest.mark.asyncio
async def test_monitor_manager_tracks_two_sessions_independently() -> None:
    registry = SessionRegistry()
    manager = MonitorManager(registry=registry)

    await manager.start_session(
        session_id="claude-1",
        adapter=ClaudeCodeAdapter(),
        workspace="/tmp/claude",
        title="Claude job",
        output_lines=delayed_lines((0.0, "editing file"), (0.05, "Task completed successfully")),
        process=FakeProcess(exit_code=0, exit_delay=0.06),
    )
    await manager.start_session(
        session_id="open-1",
        adapter=OpenCodeAdapter(),
        workspace="/tmp/open",
        title="Open job",
        output_lines=delayed_lines((0.0, "Need approval before deleting files.")),
        process=FakeProcess(exit_code=0, exit_delay=0.2),
    )

    await asyncio.sleep(0.1)
    claude_status = await registry.get("claude-1")
    open_status = await registry.get("open-1")

    assert claude_status is not None
    assert open_status is not None
    assert claude_status.state is AttentionState.COMPLETED
    assert open_status.state is AttentionState.NEEDS_PERMISSION

    await manager.wait_for_all()


@pytest.mark.asyncio
async def test_one_completion_does_not_stop_other_sessions() -> None:
    registry = SessionRegistry()
    manager = MonitorManager(registry=registry)

    await manager.start_session(
        session_id="fast",
        adapter=ClaudeCodeAdapter(),
        workspace="/tmp/fast",
        title="fast",
        output_lines=delayed_lines((0.0, "Task completed successfully")),
        process=FakeProcess(exit_code=0, exit_delay=0.01),
    )
    await manager.start_session(
        session_id="slow",
        adapter=OpenCodeAdapter(),
        workspace="/tmp/slow",
        title="slow",
        output_lines=delayed_lines((0.15, "editing..."), (0.15, "Task completed successfully")),
        process=FakeProcess(exit_code=0, exit_delay=0.35),
    )

    await asyncio.sleep(0.05)
    fast_status = await registry.get("fast")
    slow_status = await registry.get("slow")
    assert fast_status is not None
    assert slow_status is not None
    assert fast_status.state is AttentionState.COMPLETED
    assert slow_status.state is AttentionState.RUNNING

    await manager.wait_for_all()
    slow_status = await registry.get("slow")
    assert slow_status is not None
    assert slow_status.state is AttentionState.COMPLETED


@pytest.mark.asyncio
async def test_monitor_task_marks_stalled_after_timeout() -> None:
    registry = SessionRegistry()
    task = MonitorTask(
        session_id="stalling",
        adapter=ClaudeCodeAdapter(),
        registry=registry,
        workspace="/tmp/stalling",
        title="stalling",
        output_lines=delayed_lines((0.0, "working"), (0.08, "still working")),
        process=FakeProcess(exit_code=0, exit_delay=0.09),
        stall_timeout=timedelta(seconds=0.03),
    )

    await task.run()

    status = await registry.get("stalling")
    assert status is not None
    assert status.state is AttentionState.COMPLETED
    assert status.last_output_snippet == "still working"


@pytest.mark.asyncio
async def test_stall_detection_is_independent_per_session() -> None:
    registry = SessionRegistry()
    manager = MonitorManager(registry=registry, stall_timeout=timedelta(seconds=0.03))

    await manager.start_session(
        session_id="stalling",
        adapter=ClaudeCodeAdapter(),
        workspace="/tmp/stalling",
        title="stalling",
        output_lines=delayed_lines((0.0, "working"), (0.2, "still working")),
        process=FakeProcess(exit_code=0, exit_delay=0.22),
    )
    await manager.start_session(
        session_id="busy",
        adapter=OpenCodeAdapter(),
        workspace="/tmp/busy",
        title="busy",
        output_lines=delayed_lines((0.0, "editing"), (0.01, "editing more"), (0.01, "done")),
        process=FakeProcess(exit_code=0, exit_delay=0.05),
    )

    await asyncio.sleep(0.15)
    stalling_status = await registry.get("stalling")
    busy_status = await registry.get("busy")
    assert stalling_status is not None
    assert busy_status is not None
    assert stalling_status.state is AttentionState.STALLED
    assert busy_status.state in {AttentionState.RUNNING, AttentionState.COMPLETED}

    await manager.wait_for_all()


@pytest.mark.asyncio
async def test_non_zero_exit_emits_failed_state() -> None:
    registry = SessionRegistry()
    task = MonitorTask(
        session_id="failed",
        adapter=OpenCodeAdapter(),
        registry=registry,
        workspace="/tmp/failed",
        title="failed",
        output_lines=delayed_lines((0.0, "editing")),
        process=FakeProcess(exit_code=2, exit_delay=0.01),
        stall_timeout=timedelta(seconds=1),
    )

    await task.run()

    status = await registry.get("failed")
    assert status is not None
    assert status.state is AttentionState.FAILED
    assert "code 2" in status.summary.lower()
