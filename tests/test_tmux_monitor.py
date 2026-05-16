from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from coding_pet.config import TmuxConfig
from coding_pet.daemon.action_router import SessionActionRequest
from coding_pet.daemon.manager import MonitorManager
from coding_pet.daemon.session_registry import SessionRegistry
from coding_pet.daemon.tmux_monitor import TmuxMonitorService
from coding_pet.models import AgentKind, AttentionState, SessionStatus
from coding_pet.tmux.capture import snapshot_hash
from coding_pet.tmux.client import TmuxClient, TmuxCommandResult
from coding_pet.transcripts.store import TranscriptStore


class FakeRunner:
    def __init__(self) -> None:
        self.capture_text = "Need clarification: which env?"
        self.calls: list[list[str]] = []
        self.panes_text = "%3|claude-auth|0.0|claude|/proj/ws/auth|claude-auth\n"
        self.loaded_texts: list[str] = []

    def run(self, argv: list[str]) -> TmuxCommandResult:
        self.calls.append(argv)
        if argv[1] == "list-panes":
            return TmuxCommandResult(stdout=self.panes_text)
        if argv[1] == "capture-pane":
            return TmuxCommandResult(stdout=self.capture_text)
        if argv[1] == "load-buffer":
            self.loaded_texts.append(Path(argv[-1]).read_text(encoding="utf-8"))
        return TmuxCommandResult()


@pytest.mark.asyncio
async def test_tmux_monitor_poll_discovers_captures_classifies_and_routes_input(
    tmp_path: Path,
) -> None:
    runner = FakeRunner()
    registry = SessionRegistry()
    manager = MonitorManager(registry=registry)
    transcript_store = TranscriptStore(tmp_path / "transcripts.sqlite")
    await transcript_store.initialize()
    service = TmuxMonitorService(
        registry=registry,
        manager=manager,
        client=TmuxClient(runner=runner),
        transcript_store=transcript_store,
        config=TmuxConfig(enabled=True, poll_interval_ms=10),
        stalled_after=timedelta(seconds=300),
    )

    await service.poll_once()

    status = await registry.get("tmux-%3")
    assert status is not None
    assert status.source_kind == "tmux"
    assert status.tmux_pane_id == "%3"
    assert status.state is AttentionState.NEEDS_INPUT
    assert status.agent_waiting_message == "Need clarification: which env?"
    assert manager.has_live_session("tmux-%3") is True

    result = await manager.route_action(
        service.build_action_request(
            "tmux-%3",
            "send_without_enter",
            "  stage 환경  ",
            press_enter=False,
        )
    )

    assert result["ok"] is True
    assert runner.loaded_texts == ["  stage 환경  "]
    assert "send-keys" not in [call[1] for call in runner.calls]
    updated = await registry.get("tmux-%3")
    assert updated is not None
    assert updated.last_dashboard_input == "  stage 환경  "
    events = await transcript_store.list_recent_events("tmux-%3", 10)
    assert [event.direction for event in events] == ["out", "in"]


@pytest.mark.asyncio
async def test_tmux_monitor_marks_missing_pane_not_live(tmp_path: Path) -> None:
    runner = FakeRunner()
    registry = SessionRegistry()
    manager = MonitorManager(registry=registry)
    store = TranscriptStore(tmp_path / "transcripts.sqlite")
    await store.initialize()
    service = TmuxMonitorService(
        registry=registry,
        manager=manager,
        client=TmuxClient(runner=runner),
        transcript_store=store,
        config=TmuxConfig(enabled=True),
    )

    await service.poll_once()
    runner.panes_text = ""
    await service.poll_once()

    status = await registry.get("tmux-%3")
    assert status is not None
    assert status.live is False
    assert manager.has_live_session("tmux-%3") is False


@pytest.mark.asyncio
async def test_tmux_monitor_preserves_unread_until_mark_read(tmp_path: Path) -> None:
    runner = FakeRunner()
    registry = SessionRegistry()
    manager = MonitorManager(registry=registry)
    store = TranscriptStore(tmp_path / "transcripts.sqlite")
    await store.initialize()
    service = TmuxMonitorService(
        registry=registry,
        manager=manager,
        client=TmuxClient(runner=runner),
        transcript_store=store,
        config=TmuxConfig(enabled=True),
    )

    await service.poll_once()
    runner.capture_text = "Need clarification: which env?\nNeed clarification: which branch?"
    await service.poll_once()
    changed = await registry.get("tmux-%3")
    assert changed is not None
    assert changed.unread is True

    await service.poll_once()
    unchanged = await registry.get("tmux-%3")
    assert unchanged is not None
    assert unchanged.unread is True

    result = await manager.route_action(
        SessionActionRequest(session_id="tmux-%3", action="mark_read")
    )
    marked = await registry.get("tmux-%3")
    assert result["ok"] is True
    assert marked is not None
    assert marked.unread is False


@pytest.mark.asyncio
async def test_tmux_monitor_rejects_unsupported_tmux_action(tmp_path: Path) -> None:
    runner = FakeRunner()
    registry = SessionRegistry()
    manager = MonitorManager(registry=registry)
    store = TranscriptStore(tmp_path / "transcripts.sqlite")
    await store.initialize()
    service = TmuxMonitorService(
        registry=registry,
        manager=manager,
        client=TmuxClient(runner=runner),
        transcript_store=store,
        config=TmuxConfig(enabled=True),
    )

    await service.poll_once()
    result = await manager.route_action(
        SessionActionRequest(session_id="tmux-%3", action="approve")
    )

    assert result["ok"] is False
    assert result["reason"] == "unsupported_action"
    assert result["detail"] == "approve is not supported for tmux sessions"


@pytest.mark.asyncio
async def test_tmux_monitor_does_not_duplicate_restored_snapshot_transcript(
    tmp_path: Path,
) -> None:
    runner = FakeRunner()
    registry = SessionRegistry()
    manager = MonitorManager(registry=registry)
    store = TranscriptStore(tmp_path / "transcripts.sqlite")
    await store.initialize()
    await registry.upsert(
        SessionStatus(
            session_id="tmux-%3",
            agent_kind=AgentKind.CLAUDE_CODE,
            title="claude-auth",
            workspace="/proj/ws/auth",
            state=AttentionState.NEEDS_INPUT,
            summary="입력 필요",
            last_event_at=datetime.now(UTC),
            source_kind="tmux",
            tmux_pane_id="%3",
            output_hash=snapshot_hash(runner.capture_text),
        )
    )
    service = TmuxMonitorService(
        registry=registry,
        manager=manager,
        client=TmuxClient(runner=runner),
        transcript_store=store,
        config=TmuxConfig(enabled=True),
    )

    await service.poll_once()

    assert await store.list_recent_events("tmux-%3", 10) == []
