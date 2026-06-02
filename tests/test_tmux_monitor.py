from __future__ import annotations

import asyncio
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
from coding_pet.transcripts.model import TranscriptEvent
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
    broadcasted: list[tuple[str, str]] = []

    async def on_transcript_event(event: TranscriptEvent) -> None:
        broadcasted.append((event.direction, event.text))

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
        on_transcript_event=on_transcript_event,
    )

    await service.poll_once()

    status = await registry.get("tmux-%3")
    assert status is not None
    assert status.source_kind == "tmux"
    assert status.tmux_pane_id == "%3"
    assert status.state is AttentionState.NEEDS_INPUT
    assert status.agent_waiting_message == "Need clarification: which env?"
    send_reply = status.capability_for("send_reply")
    attach = status.capability_for("attach")
    assert send_reply is not None
    assert send_reply.transport == "tmux_buffer"
    assert attach is not None
    assert attach.transport == "tmux_attach"
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
    assert broadcasted == [
        ("out", "Need clarification: which env?"),
        ("in", "  stage 환경  "),
    ]


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
async def test_tmux_monitor_removes_disappeared_completed_pane_after_retention(
    tmp_path: Path,
) -> None:
    runner = FakeRunner()
    registry = SessionRegistry()
    manager = MonitorManager(
        registry=registry,
        completed_retention=timedelta(milliseconds=10),
    )
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

    disappeared = await registry.get("tmux-%3")
    assert disappeared is not None
    assert disappeared.live is False
    assert disappeared.state is AttentionState.COMPLETED
    assert disappeared.summary == "tmux pane ended"
    await asyncio.sleep(0.05)

    assert await registry.get("tmux-%3") is None


@pytest.mark.asyncio
async def test_tmux_monitor_preserves_failed_state_when_pane_disappears(
    tmp_path: Path,
) -> None:
    runner = FakeRunner()
    registry = SessionRegistry()
    manager = MonitorManager(
        registry=registry,
        completed_retention=timedelta(milliseconds=10),
    )
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
    current = await registry.get("tmux-%3")
    assert current is not None
    await registry.upsert(
        current.model_copy(
            update={
                "state": AttentionState.FAILED,
                "summary": "agent failed",
                "state_reason": "process_failed",
            }
        )
    )
    runner.panes_text = ""
    await service.poll_once()
    await asyncio.sleep(0.05)

    disappeared = await registry.get("tmux-%3")
    assert disappeared is not None
    assert disappeared.live is False
    assert disappeared.state is AttentionState.FAILED
    assert disappeared.summary == "agent failed"


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
        SessionActionRequest(session_id="tmux-%3", action="hide_pet")
    )

    assert result["ok"] is False
    assert result["reason"] == "unsupported_action"
    assert result["detail"] == "hide_pet is not supported for tmux sessions"


@pytest.mark.asyncio
async def test_tmux_monitor_routes_claude_approval_through_agent_control_message(
    tmp_path: Path,
) -> None:
    runner = FakeRunner()
    runner.capture_text = "Approval required before deleting files."
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
    status = await registry.get("tmux-%3")
    assert status is not None
    assert status.agent_kind is AgentKind.CLAUDE_CODE
    assert status.state is AttentionState.NEEDS_PERMISSION

    result = await manager.route_action(
        SessionActionRequest(session_id="tmux-%3", action="approve")
    )

    assert result["ok"] is True
    assert runner.loaded_texts == ["approve"]
    assert "send-keys" in [call[1] for call in runner.calls]
    updated = await registry.get("tmux-%3")
    assert updated is not None
    assert updated.state is AttentionState.RUNNING
    assert updated.last_dashboard_input == "approve"
    events = await store.list_recent_events("tmux-%3", 10)
    assert [(event.direction, event.text) for event in events] == [
        ("out", "Approval required before deleting files."),
        ("in", "approve"),
    ]


@pytest.mark.asyncio
async def test_tmux_monitor_routes_opencode_rejection_through_agent_control_message(
    tmp_path: Path,
) -> None:
    runner = FakeRunner()
    runner.capture_text = "Approval required before deleting files."
    runner.panes_text = "%4|opencode-build|0.0|opencode|/proj/ws/build|opencode-build\n"
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
    status = await registry.get("tmux-%4")
    assert status is not None
    assert status.agent_kind is AgentKind.OPENCODE
    assert status.state is AttentionState.NEEDS_PERMISSION

    result = await manager.route_action(
        SessionActionRequest(session_id="tmux-%4", action="reject")
    )

    assert result["ok"] is True
    assert runner.loaded_texts == ["reject"]
    updated = await registry.get("tmux-%4")
    assert updated is not None
    assert updated.state is AttentionState.RUNNING
    assert updated.last_dashboard_input == "reject"


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
