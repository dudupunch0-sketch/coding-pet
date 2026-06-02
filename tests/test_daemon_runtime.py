from __future__ import annotations

import asyncio
import logging
import tempfile
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from coding_pet.agents.claude_code import ClaudeCodeAdapter
from coding_pet.agents.registry import AgentBackendRegistry, AgentBackendStatus
from coding_pet.daemon.action_router import ActionResult, SessionActionRequest, SessionActionRouter
from coding_pet.daemon.app import DaemonApp
from coding_pet.daemon.manager import MonitorManager
from coding_pet.daemon.runtime import (
    MAX_SOCKET_PATH_BYTES,
    DaemonRuntime,
    default_socket_path,
)
from coding_pet.daemon.session_registry import SessionRegistry
from coding_pet.ipc.client import IpcClient
from coding_pet.models import ActionCapability, AgentKind, AttentionState, SessionStatus
from coding_pet.state_store import StateStore
from coding_pet.transcripts.store import TranscriptStore


class FakeProcess:
    def __init__(self, *, exit_code: int = 0, exit_delay: float = 5.0) -> None:
        self.exit_code = exit_code
        self.exit_delay = exit_delay

    async def wait(self) -> int:
        await asyncio.sleep(self.exit_delay)
        return self.exit_code


class CapturingStdin:
    def __init__(self) -> None:
        self.chunks: list[bytes] = []
        self.drain_count = 0

    def write(self, data: bytes) -> None:
        self.chunks.append(data)

    async def drain(self) -> None:
        self.drain_count += 1


async def delayed_lines(*items: tuple[float, str]) -> AsyncIterator[str]:
    for delay, line in items:
        await asyncio.sleep(delay)
        yield line


def build_status(session_id: str, state: AttentionState) -> SessionStatus:
    return SessionStatus(
        session_id=session_id,
        agent_kind=AgentKind.CLAUDE_CODE,
        title=session_id,
        workspace=f"/tmp/{session_id}",
        state=state,
        summary=f"{session_id}:{state.value}",
        last_event_at=datetime(2026, 4, 18, tzinfo=UTC),
    )


def test_default_socket_path_uses_short_deterministic_fallback_for_long_runtime_dirs(
    tmp_path: Path,
) -> None:
    runtime_dir = tmp_path / ("nested-segment-" * 12)

    socket_path = default_socket_path(runtime_dir)

    assert socket_path == default_socket_path(runtime_dir)
    assert socket_path.parent == Path(tempfile.gettempdir())
    assert socket_path.name.startswith("coding-pet-")
    assert socket_path.suffix == ".sock"
    assert len(socket_path.as_posix().encode()) <= MAX_SOCKET_PATH_BYTES


def test_daemon_runtime_passes_process_stop_timeout_to_manager(tmp_path: Path) -> None:
    runtime = DaemonRuntime(
        runtime_dir=tmp_path / "run",
        state_store=StateStore(tmp_path / "state.json"),
        process_stop_timeout=timedelta(seconds=5),
    )

    assert runtime.manager is not None
    assert runtime.manager.process_stop_timeout == timedelta(seconds=5)


def test_session_action_request_requires_reply_text_for_send_reply() -> None:
    with pytest.raises(ValueError, match="reply_text"):
        SessionActionRequest.from_message(
            {
                "type": "action_request",
                "session_id": "live-1",
                "action": "send_reply",
            }
        )


@pytest.mark.asyncio
async def test_send_process_message_can_omit_enter() -> None:
    from coding_pet.daemon.app import _send_process_message

    stdin = CapturingStdin()

    await _send_process_message(stdin, "draft reply", press_enter=False)

    assert stdin.chunks == [b"draft reply"]
    assert stdin.drain_count == 1


@pytest.mark.asyncio
async def test_session_action_router_returns_reason_for_unsupported_action() -> None:
    registry = SessionRegistry()

    async def dispatch_action(_request: SessionActionRequest) -> ActionResult:
        return {
            "type": "action_result",
            "session_id": "unused",
            "action": "send_reply",
            "ok": True,
            "reason": "delivered",
            "detail": "unexpected",
        }

    router = SessionActionRouter(
        registry=registry,
        is_session_live=lambda _session_id: False,
        dispatch_action=dispatch_action,
    )

    result = await router.handle_message(
        {
            "type": "action_request",
            "session_id": "live-1",
            "action": "archive",
        }
    )

    assert result["ok"] is False
    assert result["reason"] == "unsupported_action"
    assert "unsupported action" in str(result["detail"])


def test_daemon_app_uses_registry_backed_adapter_lookup() -> None:
    backend = AgentBackendStatus(
        agent_kind=AgentKind.CLAUDE_CODE,
        adapter=ClaudeCodeAdapter(),
        binary_name="claude",
        available=True,
        reason="available",
        binary_path="/usr/bin/claude",
    )
    app = DaemonApp(
        backend_registry=AgentBackendRegistry({AgentKind.CLAUDE_CODE: backend})
    )

    adapter = app.adapter_for(AgentKind.CLAUDE_CODE)

    assert adapter is backend.adapter


def test_daemon_app_rejects_unavailable_registry_backend() -> None:
    backend = AgentBackendStatus(
        agent_kind=AgentKind.CLAUDE_CODE,
        adapter=ClaudeCodeAdapter(),
        binary_name="claude",
        available=False,
        reason="not installed (missing 'claude')",
        binary_path=None,
    )
    app = DaemonApp(
        backend_registry=AgentBackendRegistry({AgentKind.CLAUDE_CODE: backend})
    )

    with pytest.raises(RuntimeError, match="claude_code"):
        app.adapter_for(AgentKind.CLAUDE_CODE)


@pytest.mark.asyncio
async def test_session_action_router_rejects_missing_session_with_reason(
    caplog: pytest.LogCaptureFixture,
) -> None:
    registry = SessionRegistry()
    routed: list[SessionActionRequest] = []

    async def dispatch_action(request: SessionActionRequest) -> ActionResult:
        routed.append(request)
        return {
            "type": "action_result",
            "session_id": request.session_id,
            "action": request.action,
            "ok": True,
            "reason": "delivered",
            "detail": "unexpected",
        }

    router = SessionActionRouter(
        registry=registry,
        is_session_live=lambda session_id: session_id == "live-1",
        dispatch_action=dispatch_action,
    )

    with caplog.at_level(logging.WARNING):
        result = await router.handle_message(
            {
                "type": "action_request",
                "session_id": "ghost-1",
                "action": "send_reply",
                "reply_text": "keep going",
            }
        )

    assert routed == []
    assert result["ok"] is False
    assert result["reason"] == "session_not_found"
    assert result["detail"] == "session not found"
    assert "missing session" in caplog.text.lower()


@pytest.mark.asyncio
async def test_session_action_router_rejects_inactive_sessions(
    caplog: pytest.LogCaptureFixture,
) -> None:
    registry = SessionRegistry()
    await registry.upsert(build_status("restored-1", AttentionState.NEEDS_INPUT))
    routed: list[SessionActionRequest] = []

    async def dispatch_action(request: SessionActionRequest) -> ActionResult:
        routed.append(request)
        return {
            "type": "action_result",
            "session_id": request.session_id,
            "action": request.action,
            "ok": True,
            "detail": "unexpected",
        }

    router = SessionActionRouter(
        registry=registry,
        is_session_live=lambda session_id: session_id == "live-1",
        dispatch_action=dispatch_action,
    )

    with caplog.at_level(logging.WARNING):
        result = await router.handle_message(
            {
                "type": "action_request",
                "session_id": "restored-1",
                "action": "send_reply",
                "reply_text": "keep going",
            }
        )

    assert routed == []
    assert result["ok"] is False
    assert result["reason"] == "session_not_live"
    assert result["detail"] == "session is not live"
    assert "inactive session" in caplog.text.lower()


@pytest.mark.asyncio
async def test_session_action_router_rejects_actions_outside_session_capability() -> None:
    registry = SessionRegistry()
    await registry.upsert(
        build_status("live-1", AttentionState.NEEDS_PERMISSION).model_copy(
            update={"supported_actions": ["send_reply"]}
        )
    )
    routed: list[SessionActionRequest] = []

    async def dispatch_action(request: SessionActionRequest) -> ActionResult:
        routed.append(request)
        return {
            "type": "action_result",
            "session_id": request.session_id,
            "action": request.action,
            "ok": True,
            "detail": "unexpected",
        }

    router = SessionActionRouter(
        registry=registry,
        is_session_live=lambda session_id: session_id == "live-1",
        dispatch_action=dispatch_action,
    )

    result = await router.handle_message(
        {
            "type": "action_request",
            "session_id": "live-1",
            "action": "approve",
        }
    )

    assert routed == []
    assert result["ok"] is False
    assert result["reason"] == "action_not_supported"
    assert result["detail"] == "approve is not supported by this session"


@pytest.mark.asyncio
async def test_session_action_router_rejects_actions_outside_structured_capabilities() -> None:
    registry = SessionRegistry()
    await registry.upsert(
        build_status("live-1", AttentionState.NEEDS_PERMISSION).model_copy(
            update={
                "supported_actions": [],
                "action_capabilities": [
                    ActionCapability(
                        action="approve",
                        transport="tmux_buffer",
                        semantics="agent_control",
                    )
                ],
            }
        )
    )
    routed: list[SessionActionRequest] = []

    async def dispatch_action(request: SessionActionRequest) -> ActionResult:
        routed.append(request)
        return {
            "type": "action_result",
            "session_id": request.session_id,
            "action": request.action,
            "ok": True,
            "detail": "unexpected",
        }

    router = SessionActionRouter(
        registry=registry,
        is_session_live=lambda session_id: session_id == "live-1",
        dispatch_action=dispatch_action,
    )

    result = await router.handle_message(
        {
            "type": "action_request",
            "session_id": "live-1",
            "action": "reject",
        }
    )

    assert routed == []
    assert result["ok"] is False
    assert result["reason"] == "action_not_supported"
    assert result["detail"] == "reject is not supported by this session"


@pytest.mark.asyncio
async def test_session_action_router_preserves_backend_outcome_and_derives_ok() -> None:
    registry = SessionRegistry()
    await registry.upsert(build_status("live-1", AttentionState.NEEDS_INPUT))

    async def dispatch_action(request: SessionActionRequest) -> ActionResult:
        return {
            "type": "action_result",
            "session_id": request.session_id,
            "action": request.action,
            "outcome": "timed_out",
            "reason": "backend_timeout",
            "detail": "backend did not acknowledge the reply",
        }

    router = SessionActionRouter(
        registry=registry,
        is_session_live=lambda session_id: session_id == "live-1",
        dispatch_action=dispatch_action,
    )

    result = await router.handle_message(
        {
            "type": "action_request",
            "session_id": "live-1",
            "action": "send_reply",
            "reply_text": "keep going",
        }
    )

    assert result["ok"] is False
    assert result["outcome"] == "timed_out"
    assert result["reason"] == "backend_timeout"
    assert result["detail"] == "backend did not acknowledge the reply"


@pytest.mark.asyncio
async def test_session_action_router_marks_read_without_live_control_channel() -> None:
    registry = SessionRegistry()
    await registry.upsert(
        build_status("hook-1", AttentionState.NEEDS_PERMISSION).model_copy(
            update={"source_kind": "hook", "live": False, "unread": True}
        )
    )
    routed: list[SessionActionRequest] = []

    async def dispatch_action(request: SessionActionRequest) -> ActionResult:
        routed.append(request)
        return {
            "type": "action_result",
            "session_id": request.session_id,
            "action": request.action,
            "ok": True,
            "detail": "unexpected",
        }

    router = SessionActionRouter(
        registry=registry,
        is_session_live=lambda _session_id: False,
        dispatch_action=dispatch_action,
    )

    result = await router.handle_message(
        {
            "type": "action_request",
            "session_id": "hook-1",
            "action": "mark_read",
        }
    )
    status = await registry.get("hook-1")

    assert routed == []
    assert result["ok"] is True
    assert result["reason"] == "marked_read"
    assert status is not None
    assert status.unread is False


@pytest.mark.asyncio
async def test_session_action_router_overrides_state_without_live_control_channel() -> None:
    registry = SessionRegistry()
    await registry.upsert(
        build_status("hook-1", AttentionState.NEEDS_PERMISSION).model_copy(
            update={"source_kind": "hook", "live": False}
        )
    )
    routed: list[SessionActionRequest] = []

    async def dispatch_action(request: SessionActionRequest) -> ActionResult:
        routed.append(request)
        return {
            "type": "action_result",
            "session_id": request.session_id,
            "action": request.action,
            "ok": True,
            "detail": "unexpected",
        }

    router = SessionActionRouter(
        registry=registry,
        is_session_live=lambda _session_id: False,
        dispatch_action=dispatch_action,
    )

    result = await router.handle_message(
        {
            "type": "action_request",
            "session_id": "hook-1",
            "action": "manual_state_override",
            "state_override": "idle",
        }
    )
    status = await registry.get("hook-1")

    assert routed == []
    assert result["ok"] is True
    assert result["reason"] == "state_overridden"
    assert status is not None
    assert status.state is AttentionState.IDLE
    assert status.summary == "Manual state: idle"
    assert status.state_reason == "manual_state_override"
    assert status.attention_score == 0


@pytest.mark.asyncio
async def test_session_action_router_hides_inactive_sessions_without_live_control() -> None:
    registry = SessionRegistry()
    await registry.upsert(
        build_status("done-1", AttentionState.COMPLETED).model_copy(update={"live": False})
    )
    routed: list[SessionActionRequest] = []

    async def dispatch_action(request: SessionActionRequest) -> ActionResult:
        routed.append(request)
        return {
            "type": "action_result",
            "session_id": request.session_id,
            "action": request.action,
            "ok": True,
            "detail": "unexpected",
        }

    router = SessionActionRouter(
        registry=registry,
        is_session_live=lambda _session_id: False,
        dispatch_action=dispatch_action,
    )

    result = await router.handle_message(
        {
            "type": "action_request",
            "session_id": "done-1",
            "action": "hide_pet",
        }
    )

    assert routed == []
    assert result["ok"] is True
    assert result["reason"] == "hidden"
    assert await registry.get("done-1") is None


@pytest.mark.asyncio
async def test_session_action_router_refuses_to_hide_live_control_sessions() -> None:
    registry = SessionRegistry()
    await registry.upsert(build_status("live-1", AttentionState.RUNNING))

    async def dispatch_action(request: SessionActionRequest) -> ActionResult:
        return {
            "type": "action_result",
            "session_id": request.session_id,
            "action": request.action,
            "ok": True,
            "detail": "unexpected",
        }

    router = SessionActionRouter(
        registry=registry,
        is_session_live=lambda session_id: session_id == "live-1",
        dispatch_action=dispatch_action,
    )

    result = await router.handle_message(
        {
            "type": "action_request",
            "session_id": "live-1",
            "action": "hide_pet",
        }
    )

    assert result["ok"] is False
    assert result["reason"] == "session_live"
    assert await registry.get("live-1") is not None


@pytest.mark.asyncio
async def test_monitor_manager_returns_reason_when_no_live_control_channel() -> None:
    registry = SessionRegistry()
    manager = MonitorManager(registry=registry)

    result = await manager.route_action(
        SessionActionRequest(
            session_id="restored-1",
            action="approve",
        )
    )

    assert result["ok"] is False
    assert result["reason"] == "no_live_control_channel"
    assert result["detail"] == "session has no live control channel"


@pytest.mark.asyncio
async def test_monitor_manager_rejects_unhandled_live_action() -> None:
    registry = SessionRegistry()
    manager = MonitorManager(registry=registry)
    await registry.upsert(build_status("live-unhandled", AttentionState.NEEDS_INPUT))

    async def unhandled(_request: SessionActionRequest) -> ActionResult | None:
        return None

    manager.register_control_channel("live-unhandled", unhandled)

    result = await manager.route_action(
        SessionActionRequest(
            session_id="live-unhandled",
            action="attach",
        )
    )

    assert result["ok"] is False
    assert result["outcome"] == "unsupported"
    assert result["reason"] == "unsupported_action"
    assert result["detail"] == "attach is not supported by this session"


@pytest.mark.asyncio
async def test_daemon_runtime_routes_action_requests_through_router(tmp_path: Path) -> None:
    registry = SessionRegistry()
    state_store = StateStore(tmp_path / "state.json")
    routed: list[SessionActionRequest] = []
    routed_event = asyncio.Event()

    async def dispatch_action(request: SessionActionRequest) -> ActionResult:
        routed.append(request)
        routed_event.set()
        return {
            "type": "action_result",
            "session_id": request.session_id,
            "action": request.action,
            "ok": True,
            "detail": "routed",
        }

    router = SessionActionRouter(
        registry=registry,
        is_session_live=lambda session_id: session_id == "live-1",
        dispatch_action=dispatch_action,
    )
    runtime = DaemonRuntime(
        runtime_dir=tmp_path / ("deep-runtime-segment-" * 12),
        state_store=state_store,
        registry=registry,
        action_router=router,
    )
    await registry.upsert(build_status("live-1", AttentionState.NEEDS_INPUT))

    await runtime.start()
    client = IpcClient(runtime.socket_path)

    try:
        await client.connect()
        await client.read_message()
        await client.send(
            {
                "type": "action_request",
                "session_id": "live-1",
                "action": "send_reply",
                "reply_text": "keep going",
            }
        )
        await asyncio.wait_for(routed_event.wait(), timeout=1)
    finally:
        await client.close()
        await runtime.stop()

    assert routed == [
        SessionActionRequest(
            session_id="live-1",
            action="send_reply",
            reply_text="keep going",
        )
    ]


@pytest.mark.asyncio
async def test_daemon_runtime_accepts_hook_events_as_session_state(tmp_path: Path) -> None:
    registry = SessionRegistry()
    state_store = StateStore(tmp_path / "state.json")
    transcript_store = TranscriptStore(tmp_path / "transcripts.sqlite")
    runtime = DaemonRuntime(
        runtime_dir=tmp_path / ("deep-runtime-segment-" * 12),
        state_store=state_store,
        registry=registry,
        transcript_store=transcript_store,
    )
    await runtime.start()
    client = IpcClient(runtime.socket_path)
    transcript_appended: dict[str, object] | None = None
    mark_read_result: dict[str, object] | None = None
    hide_result: dict[str, object] | None = None
    stored_after_mark_read: SessionStatus | None = None

    try:
        await client.connect()
        await client.read_message()
        await client.send(
            {
                "type": "hook_event",
                "agent": "claude_code",
                "event": "PreToolUse",
                "session_id": "abc",
                "workspace": "/proj/ws",
                "title": "Claude Hook",
                "summary": "tool started",
            }
        )
        while True:
            message = await client.read_message()
            if message.get("type") == "transcript_appended":
                transcript_appended = message
            if message.get("type") == "hook_event_result":
                result = message
                break
        await client.send(
            {
                "type": "action_request",
                "session_id": "hook-claude_code-abc",
                "action": "mark_read",
            }
        )
        while True:
            message = await client.read_message()
            if message.get("type") == "action_result":
                mark_read_result = message
                break
        stored_after_mark_read = await registry.get("hook-claude_code-abc")
        await client.send(
            {
                "type": "action_request",
                "session_id": "hook-claude_code-abc",
                "action": "hide_pet",
            }
        )
        while True:
            message = await client.read_message()
            if message.get("type") == "action_result":
                hide_result = message
                break
    finally:
        await client.close()
        await runtime.stop()

    stored = await registry.get("hook-claude_code-abc")
    events = await transcript_store.list_recent_events("hook-claude_code-abc")
    assert result["ok"] is True
    assert result["state"] == "running"
    assert stored_after_mark_read is not None
    assert stored_after_mark_read.agent_kind is AgentKind.CLAUDE_CODE
    assert stored_after_mark_read.state is AttentionState.RUNNING
    assert stored_after_mark_read.source_kind == "hook"
    assert stored_after_mark_read.live is False
    assert stored_after_mark_read.unread is False
    assert stored is None
    assert len(events) == 1
    assert events[0].direction == "system"
    assert events[0].source == "hook_event"
    assert events[0].text == "PreToolUse: tool started"
    assert transcript_appended is not None
    assert transcript_appended["session_id"] == "hook-claude_code-abc"
    assert mark_read_result is not None
    assert mark_read_result["ok"] is True
    assert mark_read_result["reason"] == "marked_read"
    assert hide_result is not None
    assert hide_result["ok"] is True
    assert hide_result["reason"] == "hidden"


@pytest.mark.asyncio
async def test_daemon_runtime_merges_hook_events_into_matching_live_session(
    tmp_path: Path,
) -> None:
    registry = SessionRegistry()
    live = build_status("tmux-%3", AttentionState.RUNNING).model_copy(
        update={
            "agent_kind": AgentKind.CLAUDE_CODE,
            "workspace": "/proj/ws",
            "source_kind": "tmux",
            "tmux_pane_id": "%3",
            "tmux_session_name": "claude-work",
            "live": True,
        }
    )
    await registry.upsert(live)
    transcript_store = TranscriptStore(tmp_path / "transcripts.sqlite")
    runtime = DaemonRuntime(
        runtime_dir=tmp_path / "runtime",
        state_store=StateStore(tmp_path / "state.json"),
        registry=registry,
        transcript_store=transcript_store,
    )
    await runtime.start()
    try:
        result = await runtime.handle_hook_event(
            {
                "type": "hook_event",
                "agent": "claude_code",
                "event": "PermissionRequest",
                "session_id": "abc",
                "workspace": "/proj/ws",
                "title": "Claude Hook",
                "summary": "approval needed",
            }
        )
    finally:
        await runtime.stop()

    stored = await registry.get("tmux-%3")
    hook_session = await registry.get("hook-claude_code-abc")
    events = await transcript_store.list_recent_events("tmux-%3")

    assert result["ok"] is True
    assert result["session_id"] == "tmux-%3"
    assert result["state"] == "needs_permission"
    assert stored is not None
    assert stored.state is AttentionState.NEEDS_PERMISSION
    assert stored.summary == "approval needed"
    assert stored.live is True
    assert stored.source_kind == "tmux"
    assert stored.tmux_pane_id == "%3"
    assert stored.tmux_session_name == "claude-work"
    assert stored.state_reason == "hook:PermissionRequest"
    assert stored.unread is True
    assert hook_session is None
    assert len(events) == 1
    assert events[0].source == "hook_event"
    assert events[0].text == "PermissionRequest: approval needed"


@pytest.mark.asyncio
async def test_daemon_runtime_routes_reply_into_live_session_handler(tmp_path: Path) -> None:
    registry = SessionRegistry()
    state_store = StateStore(tmp_path / "state.json")
    runtime = DaemonRuntime(
        runtime_dir=tmp_path / ("deep-runtime-segment-" * 12),
        state_store=state_store,
        registry=registry,
    )
    delivered: list[str] = []
    delivered_event = asyncio.Event()

    async def action_handler(request: SessionActionRequest) -> ActionResult:
        assert request.reply_text is not None
        delivered.append(request.reply_text)
        delivered_event.set()
        return {
            "type": "action_result",
            "session_id": request.session_id,
            "action": request.action,
            "ok": True,
            "reason": "delivered",
            "detail": f"{request.reply_text} delivered",
        }

    await runtime.start()
    assert runtime.manager is not None
    await runtime.manager.start_session(
        session_id="live-2",
        adapter=ClaudeCodeAdapter(),
        workspace="/tmp/live-2",
        title="live-2",
        output_lines=delayed_lines((1.0, "waiting")),
        process=FakeProcess(),
        action_handler=action_handler,
    )
    client = IpcClient(runtime.socket_path)

    try:
        await client.connect()
        await client.read_message()
        await client.send(
            {
                "type": "action_request",
                "session_id": "live-2",
                "action": "send_reply",
                "reply_text": "summarize shortly",
            }
        )
        await asyncio.wait_for(delivered_event.wait(), timeout=1)
    finally:
        await client.close()
        await runtime.stop()

    assert delivered == ["summarize shortly"]


@pytest.mark.asyncio
async def test_daemon_runtime_routes_approve_into_live_session_handler(tmp_path: Path) -> None:
    registry = SessionRegistry()
    state_store = StateStore(tmp_path / "state.json")
    runtime = DaemonRuntime(
        runtime_dir=tmp_path / ("deep-runtime-segment-" * 12),
        state_store=state_store,
        registry=registry,
    )
    received: list[str] = []
    received_event = asyncio.Event()

    async def action_handler(request: SessionActionRequest) -> ActionResult:
        received.append(request.action)
        received_event.set()
        return {
            "type": "action_result",
            "session_id": request.session_id,
            "action": request.action,
            "ok": True,
            "reason": "delivered",
            "detail": f"{request.action} delivered",
        }

    await runtime.start()
    assert runtime.manager is not None
    await runtime.manager.start_session(
        session_id="live-approve",
        adapter=ClaudeCodeAdapter(),
        workspace="/tmp/live-approve",
        title="live-approve",
        output_lines=delayed_lines((1.0, "waiting")),
        process=FakeProcess(),
        action_handler=action_handler,
    )
    client = IpcClient(runtime.socket_path)

    try:
        await client.connect()
        await client.read_message()
        await client.send(
            {
                "type": "action_request",
                "session_id": "live-approve",
                "action": "approve",
            }
        )
        result = await client.read_message()
        await asyncio.wait_for(received_event.wait(), timeout=1)
    finally:
        await client.close()
        await runtime.stop()

    assert received == ["approve"]
    assert result["ok"] is True
    assert result["reason"] == "delivered"
    assert result["detail"] == "approve delivered"


@pytest.mark.asyncio
async def test_daemon_runtime_routes_reject_into_live_session_handler(tmp_path: Path) -> None:
    registry = SessionRegistry()
    state_store = StateStore(tmp_path / "state.json")
    runtime = DaemonRuntime(
        runtime_dir=tmp_path / ("deep-runtime-segment-" * 12),
        state_store=state_store,
        registry=registry,
    )
    received: list[str] = []
    received_event = asyncio.Event()

    async def action_handler(request: SessionActionRequest) -> ActionResult:
        received.append(request.action)
        received_event.set()
        return {
            "type": "action_result",
            "session_id": request.session_id,
            "action": request.action,
            "ok": True,
            "reason": "delivered",
            "detail": f"{request.action} delivered",
        }

    await runtime.start()
    assert runtime.manager is not None
    await runtime.manager.start_session(
        session_id="live-reject",
        adapter=ClaudeCodeAdapter(),
        workspace="/tmp/live-reject",
        title="live-reject",
        output_lines=delayed_lines((1.0, "waiting")),
        process=FakeProcess(),
        action_handler=action_handler,
    )
    client = IpcClient(runtime.socket_path)

    try:
        await client.connect()
        await client.read_message()
        await client.send(
            {
                "type": "action_request",
                "session_id": "live-reject",
                "action": "reject",
            }
        )
        result = await client.read_message()
        await asyncio.wait_for(received_event.wait(), timeout=1)
    finally:
        await client.close()
        await runtime.stop()

    assert received == ["reject"]
    assert result["ok"] is True
    assert result["reason"] == "delivered"
    assert result["detail"] == "reject delivered"
