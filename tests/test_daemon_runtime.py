from __future__ import annotations

import asyncio
import logging
import tempfile
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from coding_pet.agents.claude_code import ClaudeCodeAdapter
from coding_pet.agents.registry import AgentBackendRegistry, AgentBackendStatus
from coding_pet.daemon.action_router import ActionResult, SessionActionRequest, SessionActionRouter
from coding_pet.daemon.app import DaemonApp
from coding_pet.daemon.runtime import (
    MAX_SOCKET_PATH_BYTES,
    DaemonRuntime,
    default_socket_path,
)
from coding_pet.daemon.session_registry import SessionRegistry
from coding_pet.ipc.client import IpcClient
from coding_pet.models import AgentKind, AttentionState, SessionStatus
from coding_pet.state_store import StateStore


class FakeProcess:
    def __init__(self, *, exit_code: int = 0, exit_delay: float = 5.0) -> None:
        self.exit_code = exit_code
        self.exit_delay = exit_delay

    async def wait(self) -> int:
        await asyncio.sleep(self.exit_delay)
        return self.exit_code


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


def test_session_action_request_requires_reply_text_for_send_reply() -> None:
    with pytest.raises(ValueError, match="reply_text"):
        SessionActionRequest.from_message(
            {
                "type": "action_request",
                "session_id": "live-1",
                "action": "send_reply",
            }
        )


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
    assert result["detail"] == "session is not live"
    assert "inactive session" in caplog.text.lower()


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

    async def action_handler(request: SessionActionRequest) -> None:
        assert request.reply_text is not None
        delivered.append(request.reply_text)
        delivered_event.set()

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

    async def action_handler(request: SessionActionRequest) -> None:
        received.append(request.action)
        received_event.set()

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

    async def action_handler(request: SessionActionRequest) -> None:
        received.append(request.action)
        received_event.set()

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
    assert result["detail"] == "reject delivered"
