from __future__ import annotations

import asyncio
import logging
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from coding_pet.daemon.action_router import SessionActionRequest, SessionActionRouter
from coding_pet.daemon.runtime import (
    MAX_SOCKET_PATH_BYTES,
    DaemonRuntime,
    default_socket_path,
)
from coding_pet.daemon.session_registry import SessionRegistry
from coding_pet.ipc.client import IpcClient
from coding_pet.models import AgentKind, AttentionState, SessionStatus
from coding_pet.state_store import StateStore


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


@pytest.mark.asyncio
async def test_session_action_router_rejects_inactive_sessions(
    caplog: pytest.LogCaptureFixture,
) -> None:
    registry = SessionRegistry()
    await registry.upsert(build_status("restored-1", AttentionState.NEEDS_INPUT))
    routed: list[SessionActionRequest] = []

    async def dispatch_action(request: SessionActionRequest) -> None:
        routed.append(request)

    router = SessionActionRouter(
        registry=registry,
        is_session_live=lambda session_id: session_id == "live-1",
        dispatch_action=dispatch_action,
    )

    with caplog.at_level(logging.WARNING):
        await router.handle_message(
            {
                "type": "action_request",
                "session_id": "restored-1",
                "action": "send_reply",
                "reply_text": "keep going",
            }
        )

    assert routed == []
    assert "inactive session" in caplog.text.lower()


@pytest.mark.asyncio
async def test_daemon_runtime_routes_action_requests_through_router(tmp_path: Path) -> None:
    registry = SessionRegistry()
    state_store = StateStore(tmp_path / "state.json")
    routed: list[SessionActionRequest] = []
    routed_event = asyncio.Event()

    async def dispatch_action(request: SessionActionRequest) -> None:
        routed.append(request)
        routed_event.set()

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
